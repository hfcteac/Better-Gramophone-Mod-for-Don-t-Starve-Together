#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""饥荒留声机 · 专属播放器

    * 只有游戏里的留声机响着的时候才有声音；留声机一停就静音，但进度继续走
    * 声音大小跟着你离留声机的距离走，左右声道跟着留声机在屏幕上的位置走
    * 游戏没开的时候，它就是一个普通播放器

音频引擎跑在独立子进程里，界面永远不会被它拖死。
带参数 --audio-worker 时是子进程模式，正常启动就是界面。
"""

import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

BLOCK = 1024
CHANNELS = 2
AUDIO_EXTS = (".mp3", ".m4a", ".flac", ".wav", ".ogg", ".aac", ".wma", ".ape", ".opus")
STATE_FILENAME = "dst_music_bridge"
ALIVE_FILENAME = "dst_music_alive"
WORKER_FLAG = "--audio-worker"

# 时长缓存：路径 -> 秒。ffmpeg -i 只读头，很快。
_DURATION_CACHE = {}


def probe_duration(ffmpeg, path):
    if path in _DURATION_CACHE:
        return _DURATION_CACHE[path]

    seconds = 0.0
    try:
        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-i", path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=20,
            creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
        )
        text = result.stderr.decode("utf-8", "replace")
        match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
        if match:
            seconds = (int(match.group(1)) * 3600
                       + int(match.group(2)) * 60
                       + float(match.group(3)))
    except Exception:
        seconds = 0.0

    _DURATION_CACHE[path] = seconds
    return seconds


def format_time(seconds):
    seconds = max(0, int(seconds or 0))
    return "%d:%02d" % (seconds // 60, seconds % 60)


def app_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


BASE_DIR = app_dir()
CONFIG_PATH = BASE_DIR / "player.json"
LOG_PATH = BASE_DIR / "player.log"

_DEBUG = "python" in Path(sys.executable).name.lower()


def log(message):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), message)
    try:
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        pass
    if _DEBUG:
        try:
            print(line, file=sys.stderr, flush=True)
        except Exception:
            pass


# ---------------------------------------------------------------- 配置文件

DEFAULT_CONFIG = {
    "music_dir": str(Path.home() / "Music"),
    "master_volume": 0.8,
}


def load_config():
    config = dict(DEFAULT_CONFIG)
    try:
        if CONFIG_PATH.is_file():
            with CONFIG_PATH.open("r", encoding="utf-8-sig") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                config.update(data)
    except (OSError, ValueError) as error:
        log("读取 player.json 失败：%s" % error)

    if not config.get("music_dir"):
        config["music_dir"] = str(Path.home() / "Music")
    return config


def save_config(config):
    try:
        with CONFIG_PATH.open("w", encoding="utf-8") as handle:
            json.dump(config, handle, ensure_ascii=False, indent=2)
    except OSError as error:
        log("保存 player.json 失败：%s" % error)


def scan_tracks(folder):
    root = Path(folder)
    if not root.is_dir():
        return []

    found = []
    try:
        for path in root.rglob("*"):
            if path.suffix.lower() in AUDIO_EXTS and path.is_file():
                found.append(str(path))
    except OSError as error:
        log("扫描音乐文件夹出错：%s" % error)
    found.sort(key=str.lower)
    return found


# ---------------------------------------------------------------- 找游戏状态

def read_timestamp(path):
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except (OSError, AttributeError):
        return 0.0
    match = re.search(r"(\d{9,})", text)
    return float(match.group(1)) if match else 0.0


def read_state(path):
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except (OSError, AttributeError):
        return None

    fields = dict(re.findall(r"([A-Za-z_]\w*)=([^\s]*)", text))
    action = fields.get("action")
    if action not in ("play", "stop"):
        return None

    try:
        timestamp = float(fields.get("time", "0"))
    except ValueError:
        return None

    def number(key):
        try:
            return float(fields.get(key, "0"))
        except ValueError:
            return 0.0

    return {"action": action, "time": timestamp,
            "volume": number("volume"), "pan": number("pan")}


def find_state_file():
    root = Path.home() / "Documents" / "Klei" / "DoNotStarveTogether"
    if not root.is_dir():
        return None

    beats = []
    for pattern in ("*/save/", "*/*/save/", "*/*/*/save/"):
        try:
            beats.extend(root.glob(pattern + ALIVE_FILENAME))
        except OSError:
            continue

    now = time.time()
    newest_dir, newest_beat = None, 0.0
    playing_dir, playing_time = None, 0.0

    for beat in beats:
        stamp = read_timestamp(beat)
        if stamp > newest_beat:
            newest_beat, newest_dir = stamp, beat.parent

        state = read_state(beat.parent / STATE_FILENAME)
        if (state is not None
                and state["action"] == "play"
                and now - state["time"] <= 8.0
                and state["time"] > playing_time):
            playing_dir, playing_time = beat.parent, state["time"]

    chosen = playing_dir or newest_dir
    return chosen / STATE_FILENAME if chosen else None


# ================================================================ 音频子进程

class AudioWorker:
    """用 sounddevice（PortAudio 回调）出声，回调里只搬数据，绝不做重活。"""

    def __init__(self):
        self.lock = threading.Lock()
        self.paths = []
        self.index = -1
        self.playing = False
        self.master = 0.8
        self.game = {"connected": False, "playing": False, "volume": 0.0, "pan": 0.0}
        self.gen = 0
        self.halt = False
        self.error = ""
        self.pos = 0.0

        self._gain = 0.0
        self._pan = 0.0
        self._q = queue.Queue(maxsize=48)
        self._rate = 44100

    def _start_duration_probe(self):
        """后台算时长，别堵住出声。"""
        def work():
            try:
                import imageio_ffmpeg

                ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
                with self.lock:
                    paths = list(self.paths)
                for path in paths:
                    probe_duration(ffmpeg, path)
            except Exception as error:
                log("计算时长失败：%s" % error)

        threading.Thread(target=work, daemon=True).start()

    # ---- 命令 ----
    def handle(self, message):
        cmd = message.get("cmd")

        with self.lock:
            if cmd == "tracks":
                self.paths = list(message.get("paths") or [])
                self.index = 0 if self.paths else -1
                self.pos = 0.0
                self.gen += 1
                restarted = True
            elif cmd == "select":
                # 点歌：从这首的开头放
                restarted = False
                if self.paths:
                    self.index = int(message.get("index", 0)) % len(self.paths)
                    self.pos = 0.0
                    self.playing = True
                    self.gen += 1
            elif cmd == "play":
                # 播放/继续：暂停后从原位置接着放
                restarted = False
                if self.paths:
                    if self.index < 0:
                        self.index = 0
                    self.playing = True
            elif cmd == "pause":
                restarted = False
                self.playing = False
            elif cmd == "stop":
                restarted = False
                self.playing = False
                self.pos = 0.0
                self.gen += 1
            elif cmd == "seek":
                restarted = False
                if self.paths:
                    self.pos = max(0.0, float(message.get("value", 0.0)))
                    self.gen += 1
            elif cmd == "toggle":
                restarted = False
                if self.paths:
                    self.playing = not self.playing
            elif cmd == "next":
                restarted = False
                if self.paths:
                    self.index = (max(self.index, -1) + 1) % len(self.paths)
                    self.pos = 0.0
                    self.playing = True
                    self.gen += 1
            elif cmd == "prev":
                restarted = False
                if self.paths:
                    self.index = (self.index - 1) % len(self.paths)
                    self.pos = 0.0
                    self.playing = True
                    self.gen += 1
            elif cmd == "volume":
                restarted = False
                self.master = max(0.0, min(1.0, float(message.get("value", 0.8))))
            elif cmd == "game":
                restarted = False
                self.game = {
                    "connected": bool(message.get("connected")),
                    "playing": bool(message.get("playing")),
                    "volume": float(message.get("volume", 0.0)),
                    "pan": float(message.get("pan", 0.0)),
                }
            elif cmd == "quit":
                restarted = False
                self.halt = True
            else:
                restarted = False

        if restarted:
            self._start_duration_probe()

    def _current_duration(self):
        with self.lock:
            if 0 <= self.index < len(self.paths):
                return _DURATION_CACHE.get(self.paths[self.index], 0.0)
        return 0.0

    def snapshot(self):
        with self.lock:
            track = ""
            if 0 <= self.index < len(self.paths):
                track = Path(self.paths[self.index]).name
            pos = self.pos
            return {
                "index": self.index,
                "count": len(self.paths),
                "playing": self.playing,
                "track": track,
                "pos": pos,
                "duration": _DURATION_CACHE.get(
                    self.paths[self.index] if 0 <= self.index < len(self.paths) else "", 0.0),
                "game": dict(self.game),
                "error": self.error,
            }

    def _desired(self):
        with self.lock:
            game = dict(self.game)
            master = self.master

        if not game["connected"]:
            return master, 0.0
        if game["playing"]:
            return max(0.0, min(1.0, master * game["volume"])), game["pan"]
        return 0.0, game["pan"]

    def _drain(self):
        while True:
            try:
                self._q.get_nowait()
            except queue.Empty:
                return

    # ---- 回调：只搬数据 ----
    def _callback(self, outdata, frames, time_info, status):
        try:
            try:
                chunk = self._q.get_nowait()
            except queue.Empty:
                outdata.fill(0)
                return

            count = min(len(chunk), frames)
            outdata[:count] = chunk[:count]
            if count < frames:
                outdata[count:] = 0
        except Exception:
            try:
                outdata.fill(0)
            except Exception:
                pass

    # ---- 主循环 ----
    def run(self):
        import numpy as np
        import sounddevice as sd
        import imageio_ffmpeg

        try:
            info = sd.query_devices(kind="output")
            self._rate = int(info.get("default_samplerate") or 48000)
        except Exception as error:
            self.error = "找不到播放设备：%s" % error
            log(self.error)
            return

        log("音频引擎就绪：%s  %d Hz" % (info.get("name", "?"), self._rate))
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        frame_bytes = BLOCK * CHANNELS * 2

        try:
            stream = sd.OutputStream(
                samplerate=self._rate,
                channels=CHANNELS,
                dtype="float32",
                blocksize=BLOCK,
                callback=self._callback,
                latency="low",
            )
            stream.start()
        except Exception as error:
            self.error = "打开音频输出失败：%s" % error
            log(self.error)
            return

        try:
            decoder = None
            current = None
            current_gen = -1
            base = 0.0
            bytes_read = 0

            while not self.halt:
                with self.lock:
                    gen = self.gen
                    index = self.index
                    playing = self.playing
                    pos = self.pos
                    paths = list(self.paths)

                if index < 0 or index >= len(paths):
                    if decoder is not None:
                        try:
                            decoder.kill()
                        except OSError:
                            pass
                        decoder = None
                        current = None
                        self._drain()
                    time.sleep(0.02)
                    continue

                path = paths[index]

                # 换了歌 / 跳进度 / 重新开始 —— 旧解码器作废
                if decoder is not None and (current != path or current_gen != gen):
                    try:
                        decoder.kill()
                    except OSError:
                        pass
                    decoder = None
                    self._drain()

                if not playing:
                    # 暂停：解码器留着，进度不丢，恢复时接着放
                    self._drain()
                    time.sleep(0.02)
                    continue

                if decoder is None:
                    base = max(0.0, pos)
                    bytes_read = 0
                    decoder = self._open(ffmpeg, path, base)
                    current = path
                    current_gen = gen
                    if decoder is None:
                        self._advance(index, gen)
                        continue

                data = decoder.stdout.read(frame_bytes)
                if not data:
                    try:
                        decoder.kill()
                    except OSError:
                        pass
                    decoder = None
                    current = None
                    self._advance(index, gen)
                    continue

                if len(data) < frame_bytes:
                    data += b"\x00" * (frame_bytes - len(data))

                bytes_read += frame_bytes
                self.pos = base + bytes_read / (self._rate * CHANNELS * 2.0)

                block = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
                block = block.reshape(-1, CHANNELS)

                target_gain, target_pan = self._desired()
                self._gain += (target_gain - self._gain) * 0.2
                self._pan += (target_pan - self._pan) * 0.2

                out = np.empty_like(block)
                out[:, 0] = block[:, 0] * self._gain * (1.0 - max(0.0, self._pan))
                out[:, 1] = block[:, 1] * self._gain * (1.0 + min(0.0, self._pan))

                # 队列满就阻塞，解码速度自动跟随播放速度
                while not self.halt:
                    try:
                        self._q.put(out, timeout=0.1)
                        break
                    except queue.Full:
                        with self.lock:
                            if self.gen != gen:
                                break
        except Exception as error:
            self.error = "播放出错：%s" % error
            log(self.error)
        finally:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass

    def _open(self, ffmpeg, path, seek_to=0.0):
        args = [ffmpeg, "-v", "error", "-nostdin"]
        if seek_to and seek_to > 0.05:
            # -ss 放在 -i 前面：快速跳转，不用先解码前面那一段
            args += ["-ss", "%.3f" % seek_to]
        args += ["-i", path, "-f", "s16le", "-ac", str(CHANNELS), "-ar", str(self._rate), "-"]
        try:
            return subprocess.Popen(
                args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
            )
        except OSError as error:
            self.error = "启动解码器失败：%s" % error
            log(self.error)
            return None

    def _advance(self, index, gen):
        with self.lock:
            if self.gen == gen and self.index == index and self.paths:
                self.index = (index + 1) % len(self.paths)
                self.pos = 0.0
                self.gen += 1


ICON_NAME = "player.ico"


def apply_window_icon(root):
    """窗口左上角 / 任务栏也换成自定义图标（exe 图标只影响文件本身）。"""
    icon = BASE_DIR / ICON_NAME
    if not icon.is_file():
        return

    try:
        root.iconbitmap(default=str(icon))
    except Exception as error:
        log("设置窗口图标失败：%s" % error)


def run_audio_worker():
    if sys.stdout is None or sys.stdin is None:
        log("子进程没有标准输入输出，无法工作")
        return 1

    # 中文路径必须走 UTF-8，否则按 GBK 误解码会产生假的 "\" 让 JSON 解析失败
    for stream in (sys.stdin, sys.stdout):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    worker = AudioWorker()
    stop = threading.Event()
    log("音频子进程启动")

    def read_commands():
        try:
            for line in sys.stdin:
                line = line.strip()
                if not line:
                    continue
                try:
                    worker.handle(json.loads(line))
                except Exception as error:
                    log("命令解析失败：%s" % error)
        except Exception:
            pass
        stop.set()
        worker.halt = True

    def write_status():
        while not stop.wait(0.25) and not worker.halt:
            try:
                sys.stdout.write(json.dumps(worker.snapshot(), ensure_ascii=False) + "\n")
                sys.stdout.flush()
            except Exception:
                break

    threading.Thread(target=read_commands, daemon=True).start()
    threading.Thread(target=write_status, daemon=True).start()

    worker.run()
    stop.set()
    log("音频子进程退出")
    return 0


# ==================================================================== 界面

class EngineClient:
    """管理音频子进程；界面永远不会被音频阻塞。"""

    def __init__(self):
        self.proc = None
        self.state = {}
        self.restarts = 0
        self.resync = False
        self._lock = threading.Lock()

    def start(self):
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            self.proc = subprocess.Popen(
                [sys.executable, WORKER_FLAG],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=flags,
                cwd=str(BASE_DIR),
            )
        except Exception as error:
            log("启动音频子进程失败：%s" % error)
            self.proc = None
            return

        threading.Thread(target=self._read, args=(self.proc,), daemon=True).start()
        log("音频子进程已启动 pid=%s" % self.proc.pid)

    def _read(self, proc):
        try:
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    self.state = json.loads(line)
                except ValueError:
                    continue
        except Exception as error:
            log("读取子进程输出失败：%s" % error)
        log("音频子进程结束")

    def alive(self):
        return self.proc is not None and self.proc.poll() is None

    def ensure(self):
        if not self.alive() and self.restarts < 5:
            self.restarts += 1
            log("重启音频子进程（第 %d 次）" % self.restarts)
            self.start()
            self.resync = True

    def send(self, **message):
        proc = self.proc
        if proc is None or proc.poll() is not None:
            return
        try:
            with self._lock:
                proc.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
                proc.stdin.flush()
        except Exception as error:
            log("发送命令失败：%s" % error)

    def close(self):
        self.send(cmd="quit")
        proc = self.proc
        if proc is not None and proc.poll() is None:
            try:
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except OSError:
                    pass


class GameWatcher(threading.Thread):
    """读游戏写的状态文件，转给音频子进程。"""

    def __init__(self, client):
        super().__init__(daemon=True)
        self.client = client
        self.stop_event = threading.Event()

    def run(self):
        state_path = None
        next_discover = 0.0

        while not self.stop_event.is_set():
            now = time.time()
            try:
                if state_path is None or now >= next_discover:
                    next_discover = now + 2.0
                    state_path = find_state_file()

                alive = 0.0
                if state_path is not None:
                    alive = read_timestamp(state_path.parent / ALIVE_FILENAME)
                connected = alive > 0 and (now - alive) <= 6.0

                state = read_state(state_path) if (connected and state_path) else None
                playing = (state is not None
                           and state["action"] == "play"
                           and (now - state["time"]) <= 8.0)

                self.client.send(
                    cmd="game",
                    connected=connected,
                    playing=playing,
                    volume=state["volume"] if playing else 0.0,
                    pan=state["pan"] if playing else 0.0,
                )
            except Exception as error:
                log("读取游戏状态出错：%s" % error)

            self.stop_event.wait(0.25)

    def stop(self):
        self.stop_event.set()


class App:
    def __init__(self, root, client):
        self.root = root
        self.client = client
        self.tracks = []
        self.config = load_config()
        self._last_index = -2
        self._dragging = False

        root.title("饥荒留声机 · 专属播放器")
        root.geometry("560x600")
        root.minsize(480, 500)

        header = ttk.Frame(root, padding=(12, 10, 12, 0))
        header.pack(fill="x")

        self.status = ttk.Label(header, text="正在启动音频引擎……",
                                font=("Microsoft YaHei UI", 10))
        self.status.pack(anchor="w")

        self.title_label = ttk.Label(header, text="没有歌曲",
                                     font=("Microsoft YaHei UI", 12, "bold"))
        self.title_label.pack(anchor="w", pady=(6, 0))

        body = ttk.Frame(root, padding=(12, 8))
        body.pack(fill="both", expand=True)

        self.listbox = tk.Listbox(body, activestyle="none", exportselection=False)
        bar = ttk.Scrollbar(body, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=bar.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        self.listbox.bind("<Double-Button-1>", self.on_pick)

        # ---- 进度条 + 时间 ----
        progress_row = ttk.Frame(root, padding=(12, 6, 12, 0))
        progress_row.pack(fill="x")

        self.elapsed_label = ttk.Label(progress_row, text="0:00", width=6,
                                       font=("Consolas", 9))
        self.elapsed_label.pack(side="left")

        self.progress = ttk.Scale(progress_row, from_=0.0, to=1.0, value=0.0,
                                  command=self.on_scrub)
        self.progress.pack(side="left", fill="x", expand=True, padx=6)
        self.progress.bind("<ButtonPress-1>", self.on_scrub_start)
        self.progress.bind("<ButtonRelease-1>", self.on_scrub_end)

        self.duration_label = ttk.Label(progress_row, text="0:00", width=6,
                                        font=("Consolas", 9))
        self.duration_label.pack(side="left")

        # ---- 播放控制 ----
        controls = ttk.Frame(root, padding=(12, 8, 12, 0))
        controls.pack(fill="x")

        ttk.Button(controls, text="上一首",
                   command=lambda: self.client.send(cmd="prev")).pack(side="left")
        ttk.Button(controls, text="播放",
                   command=self.on_play).pack(side="left", padx=(8, 4))
        ttk.Button(controls, text="暂停",
                   command=lambda: self.client.send(cmd="pause")).pack(side="left")
        ttk.Button(controls, text="停止",
                   command=self.on_stop).pack(side="left", padx=(4, 8))
        ttk.Button(controls, text="下一首",
                   command=lambda: self.client.send(cmd="next")).pack(side="left")

        volume_row = ttk.Frame(root, padding=(12, 10, 12, 6))
        volume_row.pack(fill="x")
        ttk.Label(volume_row, text="总音量").pack(side="left")
        self.volume = ttk.Scale(volume_row, from_=0.0, to=1.0,
                                value=float(self.config.get("master_volume", 0.8)),
                                command=self.on_volume)
        self.volume.pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(volume_row, text="选择文件夹",
                   command=self.on_pick_folder).pack(side="left")

        credit = ttk.Frame(root, padding=(12, 0, 12, 10))
        credit.pack(fill="x")
        ttk.Label(credit, text="作者：hafeizhou", foreground="#777",
                  font=("Microsoft YaHei UI", 9)).pack(side="left")
        ttk.Label(credit, text="反馈：3024026103@qq.com", foreground="#777",
                  font=("Microsoft YaHei UI", 9)).pack(side="right")

        self.load_tracks(self.config.get("music_dir"), push=True)
        self.client.send(cmd="volume", value=float(self.config.get("master_volume", 0.8)))
        self.tick()

    def load_tracks(self, folder, push=False):
        self.tracks = scan_tracks(folder)
        self.listbox.delete(0, tk.END)
        for path in self.tracks:
            self.listbox.insert(tk.END, Path(path).name)
        if push:
            self.client.send(cmd="tracks", paths=self.tracks)
        log("歌单 %s：%d 首" % (folder, len(self.tracks)))

    def tick(self):
        try:
            self.client.ensure()

            if self.client.resync:
                # 音频子进程重启过：把歌单和音量重新发一遍，否则它手里是空的
                self.client.resync = False
                self.client.send(cmd="tracks", paths=self.tracks)
                self.client.send(cmd="volume",
                                 value=float(self.config.get("master_volume", 0.8)))

            state = self.client.state
            game = state.get("game") or {}
            count = state.get("count", len(self.tracks))
            index = state.get("index", -1)

            if state.get("error"):
                self.status.configure(text="⚠ " + state["error"])
            elif not count:
                self.status.configure(text="没有找到歌，点「选择文件夹」挑一个")
            elif game.get("connected"):
                self.status.configure(text="游戏已开，和留声机同步")
            else:
                self.status.configure(text="游戏没开，正常播放")

            self.title_label.configure(text=state.get("track") or "没有歌曲")

            pos = float(state.get("pos") or 0.0)
            duration = float(state.get("duration") or 0.0)

            if not self._dragging:
                if duration > 0.05:
                    self.progress.configure(to=duration, value=min(pos, duration))
                else:
                    self.progress.configure(to=1.0, value=0.0)
                self.elapsed_label.configure(text=format_time(pos))

            self.duration_label.configure(text=format_time(duration))

            if index != self._last_index and 0 <= index < self.listbox.size():
                self.listbox.selection_clear(0, tk.END)
                self.listbox.selection_set(index)
                self.listbox.see(index)
                self._last_index = index
        except Exception as error:
            log("界面刷新出错：%s" % error)

        self.root.after(200, self.tick)

    def on_play(self):
        self.client.send(cmd="play")

    def on_stop(self):
        self.client.send(cmd="stop")
        self.elapsed_label.configure(text="0:00")

    def on_scrub_start(self, _event=None):
        self._dragging = True

    def on_scrub(self, value):
        if not self._dragging:
            return
        try:
            self.elapsed_label.configure(text=format_time(float(value)))
        except (TypeError, ValueError):
            pass

    def on_scrub_end(self, _event=None):
        if not self._dragging:
            return
        self._dragging = False
        try:
            self.client.send(cmd="seek", value=float(self.progress.get()))
        except (TypeError, ValueError):
            pass

    def on_pick(self, _event=None):
        selection = self.listbox.curselection()
        if selection:
            self._last_index = selection[0]
            self.client.send(cmd="select", index=selection[0])

    def on_pick_folder(self):
        current = self.config.get("music_dir") or str(Path.home() / "Music")
        try:
            folder = filedialog.askdirectory(
                parent=self.root, title="选择音乐文件夹",
                initialdir=current, mustexist=True,
            )
        except Exception as error:
            log("选择文件夹失败：%s" % error)
            return

        if not folder:
            return

        self.config["music_dir"] = folder
        save_config(self.config)
        self.load_tracks(folder, push=True)

    def on_volume(self, value):
        try:
            self.config["master_volume"] = max(0.0, min(1.0, float(value)))
            save_config(self.config)
            self.client.send(cmd="volume", value=self.config["master_volume"])
        except (TypeError, ValueError):
            pass


def run_ui():
    client = EngineClient()
    client.start()

    watcher = GameWatcher(client)
    watcher.start()

    root = tk.Tk()
    apply_window_icon(root)
    App(root, client)

    def on_close():
        watcher.stop()
        client.close()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    try:
        root.mainloop()
    finally:
        watcher.stop()
        client.close()
    return 0


def main():
    if WORKER_FLAG in sys.argv:
        return run_audio_worker()
    return run_ui()


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""测 worker 的进度 / 暂停 / 停止 / 跳转 / 时长。

用真实音频文件跑一遍，逐步断言，最后汇总结果。
"""
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(r"C:\Users\hafeizhou\Desktop\Dontstarvetogethrer")
SRC = Path(r"C:\Users\hafeizhou\Desktop\刻碟视频\128k版本\output")
tracks = sorted(str(p) for p in SRC.glob("*.mp3"))[:1]
print("测试曲目:", Path(tracks[0]).name)

proc = subprocess.Popen(
    [sys.executable, str(BASE / "player.py"), "--audio-worker"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    text=True, encoding="utf-8", bufsize=1,
    creationflags=subprocess.CREATE_NO_WINDOW, cwd=str(BASE),
)

latest = {}


def reader():
    for line in proc.stdout:
        line = line.strip()
        if line:
            try:
                latest.update(json.loads(line))
            except ValueError:
                pass


threading.Thread(target=reader, daemon=True).start()


def send(**kw):
    proc.stdin.write(json.dumps(kw, ensure_ascii=False) + "\n")
    proc.stdin.flush()


def snap(tag):
    data = dict(latest)
    print("%-12s playing=%-5s pos=%5.1f dur=%6.1f"
          % (tag, data.get("playing"), data.get("pos", 0), data.get("duration", 0)))
    return data


results = []


def check(name, ok):
    results.append((name, ok))
    print("   %s  %s" % ("OK  " if ok else "FAIL", name))


time.sleep(4)
send(cmd="tracks", paths=tracks)
send(cmd="game", connected=False, playing=False, volume=0.0, pan=0.0)
time.sleep(3)
loaded = snap("加载后")
check("有总时长", loaded.get("duration", 0) > 60)

send(cmd="select", index=0)
time.sleep(2.5)
playing = snap("播放2.5s")
check("在播放", playing.get("playing") is True)
check("进度在前进了", playing.get("pos", 0) > 1.0)

send(cmd="pause")
time.sleep(2.0)
paused = snap("暂停后")
check("暂停后停止播放", paused.get("playing") is False)
check("暂停后进度基本不动",
      abs(paused.get("pos", 0) - playing.get("pos", 0)) < 1.5)

send(cmd="play")
time.sleep(1.5)
resumed = snap("继续后")
check("继续后从头接着放", resumed.get("pos", 0) >= paused.get("pos", 0) - 0.5)
check("继续后确实在播", resumed.get("playing") is True)

send(cmd="seek", value=60.0)
time.sleep(2.0)
seeked = snap("跳到60s")
check("跳转生效", seeked.get("pos", 0) >= 59.0)

send(cmd="stop")
time.sleep(1.0)
stopped = snap("停止后")
check("停止后未播放", stopped.get("playing") is False)
check("停止后进度归零", abs(stopped.get("pos", 0)) < 0.5)

send(cmd="play")
time.sleep(2.0)
replayed = snap("停止后播放")
check("停止后再播放从头开始", replayed.get("pos", 99) < 5.0)

send(cmd="quit")
try:
    proc.wait(timeout=6)
except Exception:
    proc.kill()

print("\n" + "=" * 40)
failed = [name for name, ok in results if not ok]
print("全部 %d 项通过" % len(results) if not failed else "失败: %s" % ", ".join(failed))
sys.exit(0 if not failed else 1)

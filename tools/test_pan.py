# -*- coding: utf-8 -*-
"""用打包好的 exe 播纯音，注入已知 pan，测左右声道实际输出。"""
import json
import math
import os
import struct
import subprocess
import sys
import threading
import time
import wave
from pathlib import Path

import numpy as np
import soundcard as sc

EXE = r"C:\Users\hafeizhou\Desktop\饥荒留声机播放器\DSTMusicPlayer.exe"
TMP = Path(os.environ["TEMP"]) / "pan_test"
TONE = TMP / "tone.wav"


def make_tone():
    TMP.mkdir(exist_ok=True)
    if TONE.exists():
        return
    w = wave.open(str(TONE), "w")
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(44100)
    amp = 12000
    w.writeframes(b"".join(
        struct.pack("<hh",
                    int(amp * math.sin(2 * math.pi * 440 * i / 44100)),
                    int(amp * math.sin(2 * math.pi * 440 * i / 44100)))
        for i in range(44100 * 40)
    ))
    w.close()


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    make_tone()
    proc = subprocess.Popen(
        [EXE, "--audio-worker"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
        creationflags=subprocess.CREATE_NO_WINDOW, cwd=str(Path(EXE).parent),
    )

    def send(**kw):
        proc.stdin.write(json.dumps(kw, ensure_ascii=False) + "\n")
        proc.stdin.flush()

    threading.Thread(target=lambda: [None for _ in proc.stdout], daemon=True).start()

    time.sleep(5)
    send(cmd="tracks", paths=[str(TONE)])
    send(cmd="play", index=0)
    time.sleep(2)

    spk = sc.default_speaker()
    mic = sc.get_microphone(id=str(spk.name), include_loopback=True)

    def levels(seconds=0.8):
        with mic.recorder(samplerate=48000, channels=2) as rec:
            d = rec.record(numframes=int(48000 * seconds))
        return (round(float(np.sqrt(np.mean(d[:, 0] ** 2))), 4),
                round(float(np.sqrt(np.mean(d[:, 1] ** 2))), 4))

    for pan in (0.0, 1.0, -1.0, 0.6, -0.6):
        send(cmd="game", connected=True, playing=True, volume=1.0, pan=pan)
        time.sleep(1.2)
        left, right = levels()
        if pan > 0.05:
            expect = "右声道更响"
        elif pan < -0.05:
            expect = "左声道更响"
        else:
            expect = "左右一样"
        got = "右" if right > left * 1.15 else ("左" if left > right * 1.15 else "平")
        print("pan=%+.1f  L=%.4f R=%.4f  期望:%s  实测:%s  %s"
              % (pan, left, right, expect, got,
                 "OK" if got in expect else "❌反了"))

    send(cmd="quit")
    try:
        proc.wait(timeout=6)
    except Exception:
        proc.kill()


if __name__ == "__main__":
    main()

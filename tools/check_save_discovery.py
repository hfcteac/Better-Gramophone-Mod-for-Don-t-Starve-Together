# -*- coding: utf-8 -*-
"""检查播放器能不能找到存档里的状态文件（本地存档 / 云存档两种布局）。

背景：云存档的存档目录比本地多一层 ——

    本地  <userid>/Cluster_3/Master/save/dst_music_bridge
    云端  <userid>/CloudSaves/<云端id>/Master/save/dst_music_bridge

旧版播放器按固定深度 glob（最多三层），云端布局永远匹配不到，
表现就是播放器一直显示「游戏没开」、留声机放着唱片也没声音。

用法：
  python tools/check_save_discovery.py
"""

import shutil
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 相对路径：本文件在 <仓库>/tools/ 下，往上一级就是仓库根
REPO = Path(__file__).resolve().parent.parent
SCRATCH = REPO / "cache" / "_save_discovery_test"

sys.path.insert(0, str(REPO))
import player  # noqa: E402


def make_save(folder, stamp):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / player.ALIVE_FILENAME).write_text("KLEI     1 %d" % stamp, encoding="utf-8")
    (folder / player.STATE_FILENAME).write_text(
        "KLEI     1 action=play\nvolume=1.000\npan=0.000\ntime=%d" % stamp,
        encoding="utf-8")


def main():
    user = SCRATCH / "1318090655"
    local = user / "Cluster_3" / "Master" / "save"
    cloud = user / "CloudSaves" / "7EA652BB4F323C26" / "Master" / "save"
    trashed = user / "trash" / "1795098136_7EA652BB4F323C26" / "Master" / "save"

    now = int(time.time())
    results = []

    cases = [
        ("只有本地存档", [(local, now)], local),
        ("只有云存档", [(cloud, now)], cloud),
        ("两个都有时取更新的", [(local, now - 5), (cloud, now)], cloud),
        ("trash 里的旧副本不参与", [(trashed, now + 30), (cloud, now)], cloud),
    ]

    print("=" * 60)
    print("  存档发现检查")
    print("=" * 60)

    for label, saves, expect in cases:
        if SCRATCH.exists():
            shutil.rmtree(SCRATCH)
        for folder, stamp in saves:
            make_save(folder, stamp)

        got = player.find_state_file(SCRATCH)
        ok = got == expect / player.STATE_FILENAME
        results.append(ok)
        print("  [%s] %s" % ("OK" if ok else "失败", label))
        if not ok:
            print("         期望：%s" % (expect / player.STATE_FILENAME).relative_to(SCRATCH))
            print("         实际：%s" % (got.relative_to(SCRATCH) if got else None))

    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)

    print("-" * 60)
    if all(results):
        print("  结果：本地存档和云存档都能找到。")
        return 0
    print("  结果：有布局找不到，云端存档时播放器会一直显示「游戏没开」。")
    return 1


if __name__ == "__main__":
    sys.exit(main())

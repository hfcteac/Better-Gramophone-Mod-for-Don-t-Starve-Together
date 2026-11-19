# -*- coding: utf-8 -*-
"""检查播放器能不能找到存档里的状态文件。

存档有三种形态，播放器都要认：

  1. 本地存档目录      <userid>/Cluster_3/Master/save/dst_music_bridge
  2. 云存档目录        <userid>/CloudSaves/<云端id>/Master/save/dst_music_bridge
  3. 云存档 zip        <userid>/CloudSaves/<云端id>/Master.zip 里的 save/dst_music_bridge

第 3 种是实际遇到的：Steam 云存档运行时**不保留解压目录**，
磁盘上只有 Master.zip / Caves.zip，状态文件就在 zip 里。
以前只扫目录，所以云存档永远显示「游戏没开」。

用法：
  python tools/check_save_discovery.py
"""

import shutil
import sys
import time
import zipfile
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


def make_save_zip(zip_path, stamp):
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("save/" + player.ALIVE_FILENAME, "KLEI     1 %d" % stamp)
        archive.writestr("save/" + player.STATE_FILENAME,
                         "KLEI     1 action=play\nvolume=1.000\npan=0.000\ntime=%d" % stamp)


def make_plain_zip(zip_path):
    """不是存档的 zip（里面没有状态文件），不应该被认成存档。"""
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("readme.txt", "not a save")


def main():
    user = SCRATCH / "1318090655"
    local = user / "Cluster_3" / "Master" / "save"
    cloud_dir = user / "CloudSaves" / "AAAA" / "Master" / "save"
    cloud_zip = user / "CloudSaves" / "BBBB" / "Master.zip"
    trashed = user / "trash" / "1795098136_CCCC" / "Master" / "save"

    now = int(time.time())
    results = []

    def is_dir_at(path):
        return lambda slot: slot is not None and slot.kind == "dir" and slot.path == path

    def is_zip_at(path):
        return lambda slot: slot is not None and slot.kind == "zip" and slot.path == path

    cases = [
        ("本地存档目录", lambda: make_save(local, now), is_dir_at(local)),
        ("云存档目录", lambda: make_save(cloud_dir, now), is_dir_at(cloud_dir)),
        ("云存档 zip（实际遇到的形态）",
         lambda: make_save_zip(cloud_zip, now), is_zip_at(cloud_zip)),
        ("本地 + 云 zip 同时存在时取更新的",
         lambda: (make_save(local, now - 5), make_save_zip(cloud_zip, now)),
         is_zip_at(cloud_zip)),
        ("trash 里的旧副本不参与",
         lambda: (make_save(trashed, now + 30), make_save_zip(cloud_zip, now)),
         is_zip_at(cloud_zip)),
        ("无关注 zip 不会被当成存档",
         lambda: (make_plain_zip(user / "CloudSaves" / "CCCC" / "NotSave.zip"),
                  make_save(local, now)),
         is_dir_at(local)),
    ]

    print("=" * 60)
    print("  存档发现检查")
    print("=" * 60)

    for label, setup, check in cases:
        if SCRATCH.exists():
            shutil.rmtree(SCRATCH)
        setup()

        slot = player.find_state_slot(SCRATCH)
        ok = check(slot)
        results.append(ok)
        print("  [%s] %s" % ("OK" if ok else "失败", label))
        if not ok:
            print("         实际：%s" % (slot,))

    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)

    print("-" * 60)
    if all(results):
        print("  结果：本地存档、云存档目录、云存档 zip 都能找到。")
        return 0
    print("  结果：有布局找不到，播放器会一直显示「游戏没开」。")
    return 1


if __name__ == "__main__":
    sys.exit(main())

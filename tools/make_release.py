# -*- coding: utf-8 -*-
"""打发布包：只放玩家需要的东西，不放源码。

产物：
  <工程目录>\\zip\\                    整理好的文件夹
  <工程目录>\\更好的唱片v1.2.0.zip      可以直接发给别人的压缩包

包含：
  myfirstmod\\              游戏 mod
  饥荒留声机播放器\\         电脑端播放器（exe + _internal）
  说明书.txt                放最外层，方便先看
"""

import shutil
import sys
import zipfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJ = Path(r"C:\Users\hafeizhou\Desktop\Dontstarvetogethrer")
MOD_SRC = Path(r"D:\SteamLibrary\steamapps\common\Don't Starve Together\mods\myfirstmod")
PLAYER_SRC = Path(r"C:\Users\hafeizhou\Desktop\饥荒留声机播放器")

STAGE = PROJ / "zip"
ARCHIVE = PROJ / "更好的唱片v1.2.0.zip"

# 这些是运行时产物，不该发给别人
SKIP_NAMES = {"player.json", "player.log", "player.old.log"}
SKIP_DIRS = {"__pycache__"}


def copy_tree(src, dst):
    shutil.copytree(
        src, dst,
        ignore=shutil.ignore_patterns(*SKIP_DIRS, *SKIP_NAMES),
    )


def build_stage():
    if STAGE.exists():
        shutil.rmtree(STAGE)
    STAGE.mkdir(parents=True)

    copy_tree(MOD_SRC, STAGE / "myfirstmod")
    copy_tree(PLAYER_SRC, STAGE / "饥荒留声机播放器")
    shutil.copy2(PROJ / "说明书.txt", STAGE / "说明书.txt")


def build_archive():
    if ARCHIVE.exists():
        ARCHIVE.unlink()

    count = 0
    total = 0
    with zipfile.ZipFile(ARCHIVE, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(STAGE.rglob("*")):
            if path.is_dir():
                continue
            arcname = path.relative_to(STAGE)
            archive.write(path, str(arcname))
            count += 1
            total += path.stat().st_size
    return count, total


def main():
    for required in (MOD_SRC, PLAYER_SRC, PROJ / "说明书.txt"):
        if not required.exists():
            print("缺少：%s" % required)
            return 1

    print("整理文件……")
    build_stage()

    print("压缩中（大概 125MB，稍等）……")
    count, total = build_archive()

    size = ARCHIVE.stat().st_size
    print()
    print("打包完成：%s" % ARCHIVE.name)
    print("  文件数      : %d" % count)
    print("  原始大小    : %.1f MB" % (total / 1048576.0))
    print("  压缩后大小  : %.1f MB" % (size / 1048576.0))
    print()
    print("包内结构：")
    for item in sorted(STAGE.iterdir()):
        if item.is_dir():
            inner = len(list(item.rglob("*")))
            print("  %s\\  (%d 项)" % (item.name, inner))
        else:
            print("  %s" % item.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())

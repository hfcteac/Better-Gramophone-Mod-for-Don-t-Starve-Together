# -*- coding: utf-8 -*-
"""打发布包：只放玩家需要的东西，不放源码。

产物：
  <工程目录>\\zip\\                    整理好的文件夹
  <工程目录>\\更好的唱片v1.2.2.zip      可以直接发给别人的压缩包

包含：
  myfirstmod\\              游戏 mod
  饥荒留声机播放器\\         电脑端播放器（exe + _internal）
  说明书.txt                放最外层，方便先看
"""

import shutil
import sys
import time
import zipfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJ = Path(r"C:\Users\hafeizhou\Desktop\Dontstarvetogethrer")
PLAYER_SRC = Path(r"C:\Users\hafeizhou\Desktop\饥荒留声机播放器")

# mod 文件直接从工程源码组装，不再依赖游戏 mods 目录或创意工坊目录。
# 以前从游戏目录复制，那边一被删或被订阅的工坊版覆盖，打包就会拿到错的或旧的。
MOD_ROOT_FILES = ["modinfo.lua", "modmain.lua", "modicon.tex", "modicon.xml"]
MOD_PREFABS = ["pcbridge_record.lua"]

STAGE = PROJ / "zip"
ARCHIVE = PROJ / "更好的唱片v1.2.2.zip"

# 这些是运行时产物，不该发给别人
SKIP_NAMES = {"player.json", "player.log", "player.old.log"}
SKIP_DIRS = {"__pycache__"}


def copy_tree(src, dst):
    shutil.copytree(
        src, dst,
        ignore=shutil.ignore_patterns(*SKIP_DIRS, *SKIP_NAMES),
    )


def build_mod(dst):
    """按 mod 目录结构组装一份，全部来自工程源码。"""
    dst.mkdir(parents=True, exist_ok=True)
    for name in MOD_ROOT_FILES:
        shutil.copy2(PROJ / name, dst / name)
    prefabs = dst / "scripts" / "prefabs"
    prefabs.mkdir(parents=True, exist_ok=True)
    for name in MOD_PREFABS:
        shutil.copy2(PROJ / "scripts" / "prefabs" / name, prefabs / name)
    shutil.copy2(PROJ / "说明书.txt", dst / "说明书.txt")


def build_stage():
    if STAGE.exists():
        shutil.rmtree(STAGE)
    STAGE.mkdir(parents=True)

    build_mod(STAGE / "myfirstmod")
    copy_tree(PLAYER_SRC, STAGE / "饥荒留声机播放器")
    shutil.copy2(PROJ / "说明书.txt", STAGE / "说明书.txt")


def build_archive():
    if ARCHIVE.exists():
        ARCHIVE.unlink()

    # zip 内每个条目的时间戳统一成打包时刻。
    # 不这么做的话，zip 会保留源文件原来的修改时间，玩家解压后看到
    # 一堆旧日期，会以为下载到了老版本。
    now = time.localtime()[:6]

    count = 0
    total = 0
    with zipfile.ZipFile(ARCHIVE, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(STAGE.rglob("*")):
            if path.is_dir():
                continue
            arcname = path.relative_to(STAGE)
            info = zipfile.ZipInfo(str(arcname).replace("\\", "/"), date_time=now)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            with open(path, "rb") as fh:
                archive.writestr(info, fh.read())
            count += 1
            total += path.stat().st_size
    return count, total


def main():
    required_files = [PROJ / name for name in MOD_ROOT_FILES]
    required_files += [PROJ / "scripts" / "prefabs" / name for name in MOD_PREFABS]
    required_files += [PROJ / "说明书.txt", PLAYER_SRC]

    for required in required_files:
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

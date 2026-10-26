# -*- coding: utf-8 -*-
"""检查「从 GitHub 下载的包」能不能真的跑起来。

背景（这个工具就是为了不再犯这个错才写的）：
  .gitignore 里曾经写着 *.zip，这条规则连带把
  饥荒留声机播放器/_internal/base_library.zip 也排除掉了。
  那个文件一直没进版本库，所以 GitHub 上每次 Download ZIP
  拿到的包都缺它，双击 exe 只会弹
  「Failed to start embedded python interpreter」。
  但本地目录是好的 —— 因为本地文件不受 .gitignore 影响，
  所以本地怎么测都是正常的，问题只出在下载下来的包。

这个工具做两件事：
  1. 用 git archive 生成「等同于 GitHub Download ZIP」的包
  2. 检查这个包里播放器必需的文件是不是都在
本地目录有文件 ≠ 包里有文件。只测本地是测不出这个问题的。

用法：
  python tools/check_release_ready.py
"""

import io
import subprocess
import sys
import zipfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = Path(r"C:\Users\hafeizhou\Desktop\jswjj\Better-Gramophone-Mod-for-Don-t-Starve-Together")
PLAYER_DIR = "饥荒留声机播放器"

# 播放器能不能启动，缺一不可
REQUIRED = [
    (PLAYER_DIR + "/DSTMusicPlayer.exe", "主程序"),
    (PLAYER_DIR + "/_internal/base_library.zip", "Python 核心库"),
    (PLAYER_DIR + "/_internal/python38.dll", "Python 运行库"),
    (PLAYER_DIR + "/_internal/_tkinter.pyd", "窗口模块"),
    (PLAYER_DIR + "/_internal/tcl86t.dll", "Tcl 库"),
    (PLAYER_DIR + "/_internal/tk86t.dll", "Tk 库"),
    (PLAYER_DIR + "/_internal/_tcl_data/init.tcl", "Tcl 数据"),
    (PLAYER_DIR + "/_internal/_tk_data/tk.tcl", "Tk 数据"),
    (PLAYER_DIR + "/_internal/_sounddevice_data/portaudio-binaries/libportaudio64bit.dll",
     "声音输出库"),
    ("说明书.txt", "说明书"),
]

# mod 能不能加载，缺一不可
REQUIRED += [
    ("modinfo.lua", "mod 元信息"),
    ("modmain.lua", "mod 逻辑"),
    ("modicon.tex", "mod 图标"),
    ("scripts/prefabs/pcbridge_record.lua", "唱片 prefab"),
]


def build_archive(out_zip):
    """git archive 产出的内容和 GitHub Download ZIP 完全一致。"""
    if out_zip.exists():
        out_zip.unlink()
    result = subprocess.run(
        ["git", "-C", str(REPO), "archive", "--format=zip",
         "-o", str(out_zip), "HEAD"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    return result.returncode == 0, result.stderr.decode("utf-8", "replace")


def main():
    if not REPO.is_dir():
        print("找不到仓库：%s" % REPO)
        return 1

    out_zip = Path(sys.executable).parent / "_release_check.zip"
    ok, err = build_archive(out_zip)
    if not ok:
        print("git archive 失败：%s" % err)
        return 1

    try:
        with zipfile.ZipFile(out_zip) as archive:
            names = set(archive.namelist())

            print("=" * 60)
            print("  模拟 GitHub Download ZIP 的检查")
            print("=" * 60)
            print("  包里条目总数：%d" % len(names))
            print()

            missing = []
            for path, desc in REQUIRED:
                if path in names:
                    print("  [OK]   %s" % desc)
                else:
                    print("  [缺失] %s    <== %s" % (desc, path))
                    missing.append((path, desc))

            # 顺便确认 .zip 规则没有误伤别的东西
            extra = [n for n in names
                     if n.endswith(".zip") and "base_library" not in n]
            if extra:
                print()
                print("  [提示] 包里有其他 .zip（发布包，正常）：%d 个" % len(extra))

            print()
            print("-" * 60)
            if missing:
                print("  结果：缺 %d 个文件，下载下来的人用不了！" % len(missing))
                print()
                print("  排查方法：")
                for path, desc in missing:
                    print("      git -C <仓库> check-ignore -v \"%s\"" % path)
                    print("      # 如果被 .gitignore 排除，用 git add -f 补进去")
                return 1

            print("  结果：全部齐了，下载解压就能用。")
            print("-" * 60)
            return 0
    finally:
        if out_zip.exists():
            out_zip.unlink()


if __name__ == "__main__":
    sys.exit(main())

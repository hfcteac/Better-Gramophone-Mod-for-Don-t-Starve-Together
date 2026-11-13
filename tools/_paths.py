# -*- coding: utf-8 -*-
"""统一推算项目路径，供 tools/ 下各脚本共用。

原则：**全部相对脚本自身位置推算，不写死任何绝对路径。**
这样整个仓库拷到任何电脑、任何盘符（C盘/D盘/U盘）都能直接跑，
不需要改任何一行代码。

游戏安装目录是唯一和具体机器相关的东西，所以做成自动探测：
  1. 优先读环境变量 DST_DIR（想手动指定时用）
        set DST_DIR=D:\SteamLibrary\steamapps\common\Don't Starve Together
  2. 否则按 Steam 的几种常见安装位置挨个找
  3. 都找不到就返回 None，调用方自己决定怎么报错
"""

import os
from pathlib import Path

# 本文件在 <仓库>/tools/ 下，往上一级就是仓库根
REPO = Path(__file__).resolve().parent.parent

# 播放器成品目录（exe + _internal）
PLAYER = REPO / "饥荒留声机播放器"

# mod 源文件（相对于仓库根）
MOD_ROOT_FILES = ["modinfo.lua", "modmain.lua", "modicon.tex", "modicon.xml"]
MOD_PREFABS = ["pcbridge_record.lua"]

# 找游戏时的候选位置：盘符 × 常见 Steam 路径
_DRIVES = ("C:", "D:", "E:", "F:", "G:")
_STEAM_BASES = (
    r"\SteamLibrary\steamapps\common",
    r"\Program Files (x86)\Steam\steamapps\common",
    r"\Program Files\Steam\steamapps\common",
    r"\Games\Steam\steamapps\common",
    r"\Steam\steamapps\common",
)


def find_game():
    """返回饥荒安装目录，找不到返回 None。"""
    env = os.environ.get("DST_DIR")
    if env:
        p = Path(env)
        if (p / "bin64").is_dir():
            return p

    for drive in _DRIVES:
        for base in _STEAM_BASES:
            p = Path(drive + base) / "Don't Starve Together"
            if (p / "bin64").is_dir():
                return p
    return None


GAME_ROOT = find_game()
GAME_MODS = (GAME_ROOT / "mods") if GAME_ROOT else None
SERVER_EXE = ((GAME_ROOT / "bin64"
               / "dontstarve_dedicated_server_nullrenderer_x64.exe")
              if GAME_ROOT else None)


def require_game():
    """测试脚本开头调用；找不到游戏就打印清楚的原因并退出。"""
    if GAME_ROOT is None:
        print("找不到饥荒安装目录。")
        print()
        print("请用环境变量指定游戏装在哪：")
        print(r'    set DST_DIR=D:\SteamLibrary\steamapps\common\Don\'t Starve Together')
        print()
        print("找过的位置：")
        for drive in _DRIVES:
            for base in _STEAM_BASES:
                print("    " + drive + base + r"\Don't Starve Together")
        raise SystemExit(1)
    return GAME_ROOT


def describe():
    """打印当前推算出来的路径，方便排查。"""
    print("仓库根      :", REPO)
    print("播放器目录  :", PLAYER, "(存在)" if PLAYER.is_dir() else "(不存在!)")
    if GAME_ROOT is None:
        print("游戏目录    : 未找到（可 set DST_DIR=... 指定）")
    else:
        print("游戏目录    :", GAME_ROOT)
        print("服务器程序  :", SERVER_EXE,
              "(存在)" if SERVER_EXE and SERVER_EXE.is_file() else "(不存在!)")

# -*- coding: utf-8 -*-
"""检查源码目录和游戏目录里的 Lua 语法。"""
import os
import sys
from pathlib import Path

import lupa

# 相对路径：本文件在 <仓库>/tools/ 下，往上一级就是仓库根
ROOT = Path(__file__).resolve().parent.parent

# 游戏安装目录：默认按 Steam 常见位置猜，猜不到就用环境变量 DST_DIR 覆盖
#     set DST_DIR=D:\你的游戏\Don't Starve Together
def find_game():
    env = os.environ.get("DST_DIR")
    if env and Path(env).is_dir():
        return Path(env)
    for drive in ("C:", "D:", "E:", "F:"):
        for base in (r"\SteamLibrary\steamapps\common",
                     r"\Program Files (x86)\Steam\steamapps\common",
                     r"\Program Files\Steam\steamapps\common"):
            p = Path(drive + base) / "Don't Starve Together"
            if p.is_dir():
                return p
    return None


GAME_ROOT = find_game()
GAME = (GAME_ROOT / "mods" / "myfirstmod") if GAME_ROOT else None

runtime = lupa.LuaRuntime()
loadfile = runtime.globals().loadfile

ok = True
targets = [(ROOT, "源码")]
if GAME is not None and GAME.is_dir():
    targets.append((GAME, "游戏目录"))
else:
    print("（没找到游戏 mod 目录，只检查源码。要检查游戏目录请 set DST_DIR=游戏安装路径）")

for base, label in targets:
    for path in sorted(base.rglob("*.lua")):
        if loadfile(str(path)) is None:
            ok = False
            print("FAIL", label, path.name)
        else:
            print("OK  ", label, path.name)

print("全部通过" if ok else "有语法错误")
sys.exit(0 if ok else 1)

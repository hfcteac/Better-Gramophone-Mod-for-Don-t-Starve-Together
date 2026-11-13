# -*- coding: utf-8 -*-
"""检查游戏目录里的 modinfo/modmain 语法（路径含撇号，单独放文件里避免转义问题）。

游戏位置自动探测，也可用环境变量指定：
    set DST_DIR=D:\SteamLibrary\steamapps\common\Don't Starve Together
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _paths

import lupa

if _paths.GAME_MODS is None:
    print("找不到饥荒安装目录，跳过游戏目录检查。")
    print("要用请先 set DST_DIR=游戏安装路径")
    sys.exit(0)

GAME = _paths.GAME_MODS / "myfirstmod"

runtime = lupa.LuaRuntime()
loadfile = runtime.globals().loadfile

ok = True
for name in ("modinfo.lua", "modmain.lua", "scripts/prefabs/pcbridge_record.lua"):
    path = GAME / name
    if loadfile(str(path)) is None:
        ok = False
        print("FAIL", name)
    else:
        print("OK  ", name)

print("全部通过" if ok else "有语法错误")
sys.exit(0 if ok else 1)

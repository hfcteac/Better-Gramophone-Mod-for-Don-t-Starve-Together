# -*- coding: utf-8 -*-
"""检查游戏目录里的 modinfo/modmain 语法（路径含撇号，单独放文件里避免转义问题）。"""
import sys
from pathlib import Path

import lupa

GAME = Path(r"D:\SteamLibrary\steamapps\common\Don't Starve Together\mods\myfirstmod")

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

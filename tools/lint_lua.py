# -*- coding: utf-8 -*-
"""检查源码目录和游戏目录里的 Lua 语法。"""
import sys
from pathlib import Path

import lupa

ROOT = Path(r"C:\Users\hafeizhou\Desktop\Dontstarvetogethrer")
GAME = Path(r"D:\SteamLibrary\steamapps\common\Don't Starve Together\mods\myfirstmod")

runtime = lupa.LuaRuntime()
loadfile = runtime.globals().loadfile

ok = True
for base, label in ((ROOT, "源码"), (GAME, "游戏目录")):
    for path in sorted(base.rglob("*.lua")):
        if loadfile(str(path)) is None:
            ok = False
            print("FAIL", label, path.name)
        else:
            print("OK  ", label, path.name)

print("全部通过" if ok else "有语法错误")
sys.exit(0 if ok else 1)

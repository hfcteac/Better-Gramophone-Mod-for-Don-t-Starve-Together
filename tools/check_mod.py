# -*- coding: utf-8 -*-
"""在隔离的临时目录里跑专用服务器，验证 mod 能加载、配方和图标正常。"""
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

EXE = r"D:\SteamLibrary\steamapps\common\Don't Starve Together\bin64\dontstarve_dedicated_server_nullrenderer_x64.exe"
ROOT = Path(os.environ["TEMP"]) / "dstmod_check"
CLUSTER = ROOT / "DoNotStarveTogether" / "CheckCluster"
MASTER = CLUSTER / "Master"


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def setup():
    shutil.rmtree(ROOT, ignore_errors=True)
    write(CLUSTER / "cluster.ini", """[GAMEPLAY]
game_mode = survival
max_players = 2
pause_when_empty = false

[NETWORK]
cluster_name = ModCheck
cluster_password =
offline_cluster = true
lan_only_cluster = true

[MISC]
console_enabled = true

[SHARD]
shard_enabled = false
bind_ip = 127.0.0.1
master_ip = 127.0.0.1
master_port = 10998
cluster_key = checkkey
""")
    write(MASTER / "server.ini", """[NETWORK]
server_port = 11300

[SHARD]
is_master = true

[STEAM]
master_server_port = 27218
authentication_port = 8968
""")
    write(MASTER / "modoverrides.lua", """return {
  ["myfirstmod"] = {
    enabled = true,
    configuration_options = { VOLUME = 1.0, CARRY_PLAY = true, PAN_MODE = "flip" },
  },
}
""")


def main():
    setup()
    proc = subprocess.Popen(
        [EXE,
         "-persistent_storage_root", str(ROOT),
         "-conf_dir", "DoNotStarveTogether",
         "-cluster", "CheckCluster",
         "-shard", "Master",
         "-skip_update_server_mods"],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=os.path.dirname(EXE),
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    log = MASTER / "server_log.txt"
    deadline = time.time() + 200
    while time.time() < deadline:
        time.sleep(2)
        if log.is_file():
            text = log.read_text(encoding="utf-8", errors="ignore")
            if "Loading modmain.lua" in text and "Registering prefab file" in text:
                break

    time.sleep(3)
    # 等世界真正跑起来再发命令，否则 SpawnPrefab 会报 "Can't find prefab"
    ready_deadline = time.time() + 120
    while time.time() < ready_deadline:
        text = log.read_text(encoding="utf-8", errors="ignore") if log.is_file() else ""
        if "Sim paused" in text or "World generated" in text:
            break
        time.sleep(2)
    time.sleep(8)

    proc.stdin.write('print("RECIPE_CHECK", AllRecipes["pcbridge_record"] ~= nil)\n')
    proc.stdin.write('local r = AllRecipes["pcbridge_record"]; '
                     'if r then for i, ing in ipairs(r.ingredients) do '
                     'print("ING", ing.type, ing.amount) end '
                     'print("TECH_LEVEL", r.level.SCIENCE) end\n')
    proc.stdin.flush()
    time.sleep(3)

    # 造一个物品出来，看它在物品栏里有没有图标
    proc.stdin.write('local item = SpawnPrefab("pcbridge_record"); '
                     'local inv = item.components.inventoryitem; '
                     'print("ITEM_IMAGE", tostring(inv and inv.imagename)); '
                     'print("ITEM_ATLAS", tostring(GetInventoryItemAtlas("record"))); '
                     'item:Remove()\n')
    proc.stdin.flush()
    time.sleep(3)

    # 拿起照样放：留声机的 onputininventoryfn 应该被清掉（否则拿起就关机）
    proc.stdin.write('PH_TEST = SpawnPrefab("phonograph"); '
                     'print("CARRY_CB", tostring(PH_TEST.components.inventoryitem.onputininventoryfn == nil))\n')
    proc.stdin.flush()
    time.sleep(2)

    # 放唱片 + 开机，确认状态文件写成 action=play
    proc.stdin.write('PH_TEST.Transform:SetPosition(10,0,10); '
                     'local rec = SpawnPrefab("pcbridge_record"); '
                     'PH_TEST.components.inventory:GiveItem(rec); '
                     'PH_TEST.components.machine:TurnOn(); '
                     'print("MACHINE_ON", tostring(PH_TEST.components.machine:IsOn()))\n')
    proc.stdin.flush()
    time.sleep(3)

    proc.stdin.write("c_shutdown(true)\n")
    proc.stdin.flush()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()

    text = log.read_text(encoding="utf-8", errors="ignore") if log.is_file() else ""

    state_file = MASTER / "save" / "dst_music_bridge"
    state_ok = False
    state_text = ""
    if state_file.is_file():
        state_text = state_file.read_text(encoding="utf-8", errors="ignore")
        state_ok = "action=play" in state_text

    print("=== mod 加载 ===")
    for line in text.splitlines():
        if any(k in line for k in ("myfirstmod", "Registering prefab", "pcbridge",
                                   "RECIPE_CHECK", "ING", "TECH_LEVEL", "ITEM_",
                                   "CARRY_CB", "MACHINE_ON",
                                   "invalid", "attempt to", "error")):
            print(" ", line.strip())

    print("\n=== 结论 ===")
    ok_mod = "Loading mod: myfirstmod" in text
    ok_prefab = "pcbridge_record" in text
    ok_recipe = "RECIPE_CHECK\ttrue" in text
    print("mod 加载   :", "OK" if ok_mod else "失败")
    print("prefab 注册:", "OK" if ok_prefab else "失败")
    print("配方存在   :", "OK" if ok_recipe else "失败")
    print("拿下继续放 :", "OK" if "CARRY_CB\ttrue" in text else "失败")
    print("开机播放   :", "OK" if "MACHINE_ON\ttrue" in text else "失败")
    print("状态写入   :", "OK" if state_ok else "未确认")
    if state_text:
        print("  内容:", state_text.replace("\n", " | ")[:120])
    print("无报错     :", "OK" if not any(
        k in text for k in ("invalid filepath", "attempt to index", "stack traceback")) else "有错误")
    return 0 if (ok_mod and ok_prefab and ok_recipe) else 1


if __name__ == "__main__":
    sys.exit(main())

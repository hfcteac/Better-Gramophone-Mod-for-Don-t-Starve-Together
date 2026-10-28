# -*- coding: utf-8 -*-
"""复现「带着留声机进洞穴掉线」并验证兜底是否生效。

真实的崩溃链路（从玩家 Master/server_log.txt 挖出来的）：

    玩家走进洞穴
      → 游戏序列化随身物品，留声机被 Remove()（inlimbo=true）
      → 触发留声机的 onremove 事件
      → 「AV唱片」(workshop-3570863128) 的监听器执行：
            local owner = inst.components.inventoryitem.owner
            owner.SoundEmitter:KillSound("neon_ragtime")
        此时 owner 是背包（amu_backpack），背包没有 SoundEmitter
      → attempt to index field 'SoundEmitter' (a nil value)
      → 这个错抛在引擎 PushEvent 内部，整个服务器进程死掉
      → 客户端: Dedicated server process terminated prematurely

本脚本注册一个和 AV唱片 一模一样「不设防」的 onremove 监听器，
然后模拟「留声机放进背包 → 被移除」，看服务器会不会崩、会不会报错。

用法：
  python tools/check_carry_cave.py
"""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

EXE = (r"D:\SteamLibrary\steamapps\common\Don't Starve Together"
       r"\bin64\dontstarve_dedicated_server_nullrenderer_x64.exe")
GAME_MODS = Path(r"D:\SteamLibrary\steamapps\common\Don't Starve Together\mods")
PROJ = Path(r"C:\Users\hafeizhou\Desktop\Dontstarvetogethrer")

ROOT = Path(os.environ["TEMP"]) / "dstcarry_check"
CLUSTER = ROOT / "DoNotStarveTogether" / "CarryCluster"
MASTER = CLUSTER / "Master"

MOD_ID = "myfirstmod_carrycheck"
MOD_DST = GAME_MODS / MOD_ID

# 模拟 AV唱片：独立的 mod，名字字母序排在前面，保证它先加载、
# 它的 onremove 监听器先注册、先执行 —— 这正是真实崩溃时的顺序。
SABOTAGE_ID = "aa_sabotage_check"
SABOTAGE_DST = GAME_MODS / SABOTAGE_ID

MOD_FILES = ["modinfo.lua", "modmain.lua", "modicon.tex", "modicon.xml"]
MOD_PREFABS = ["pcbridge_record.lua"]

# 可用环境变量 CARRY_TEST_MODMAIN 指定用哪个 modmain.lua 来测，
# 方便拿旧版做对照实验（证明修复前后确实是这个差别）
MODMAIN_OVERRIDE = os.environ.get("CARRY_TEST_MODMAIN")

SABOTAGE_INFO = """name = "AA sabotage check"
description = "test only"
author = "test"
version = "1.0.0"
api_version = 10
dst_compatible = true
client_only_mod = false
all_clients_require_mod = false
server_filter_tags = {}
"""

# 这个「测试用外来 mod」故意复刻 AV唱片 的写法：
# 它比我们的 mod 早注册 onremove 监听器，并且完全不做防护。
SABOTAGE = """
-- 复刻 AV唱片 modmain.lua:147-164 的写法，用来验证兜底是否生效
local function ClearPlayerTag(owner)
    owner.SoundEmitter:KillSound("neon_ragtime")
    owner._neon_phonograph = nil
end

local function onremove(inst, data)
    local owner = inst.components.inventoryitem.owner
    if owner then
        ClearPlayerTag(owner)
    end
end

AddPrefabPostInit("phonograph", function(inst)
    inst:ListenForEvent("onremove", onremove)
    return inst
end)
"""

MOD_OVERRIDE = """return {
  ["%s"] = {
    enabled = true,
    configuration_options = { VOLUME = 1.0, CARRY_PLAY = true },
  },
  ["%s"] = {
    enabled = true,
  },
}
""" % (MOD_ID, SABOTAGE_ID)


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def install_mod():
    for dst in (MOD_DST, SABOTAGE_DST):
        if dst.exists():
            shutil.rmtree(str(dst))

    MOD_DST.mkdir(parents=True)
    for name in MOD_FILES:
        shutil.copy2(str(PROJ / name), str(MOD_DST / name))
    if MODMAIN_OVERRIDE:
        shutil.copy2(MODMAIN_OVERRIDE, str(MOD_DST / "modmain.lua"))
        print("  [对照实验] 使用指定的 modmain：%s" % MODMAIN_OVERRIDE)
    prefabs = MOD_DST / "scripts" / "prefabs"
    prefabs.mkdir(parents=True)
    for name in MOD_PREFABS:
        shutil.copy2(str(PROJ / "scripts" / "prefabs" / name), str(prefabs / name))
    shutil.copy2(str(PROJ / "说明书.txt"), str(MOD_DST / "说明书.txt"))

    SABOTAGE_DST.mkdir(parents=True)
    write(SABOTAGE_DST / "modinfo.lua", SABOTAGE_INFO)
    write(SABOTAGE_DST / "modmain.lua", SABOTAGE)


def remove_mod():
    for dst in (MOD_DST, SABOTAGE_DST):
        shutil.rmtree(str(dst), ignore_errors=True)


def setup():
    shutil.rmtree(ROOT, ignore_errors=True)
    write(CLUSTER / "cluster.ini", """[GAMEPLAY]
game_mode = survival
max_players = 2
pause_when_empty = false

[NETWORK]
cluster_name = CarryCheck
cluster_password =
offline_cluster = true
lan_only_cluster = true

[MISC]
console_enabled = true

[SHARD]
shard_enabled = false
bind_ip = 127.0.0.1
master_ip = 127.0.0.1
master_port = 10997
cluster_key = carrykey
""")
    write(MASTER / "server.ini", """[NETWORK]
server_port = 11320

[SHARD]
is_master = true

[STEAM]
master_server_port = 27238
authentication_port = 8988
""")
    write(MASTER / "modoverrides.lua", MOD_OVERRIDE)
    write(MASTER / "worldgenoverride.lua", """return {
  override_enabled = true,
  preset = "SURVIVAL_TOGETHER",
}
""")


def main():
    install_mod()
    proc = None
    try:
        setup()
        proc = subprocess.Popen(
            [EXE,
             "-persistent_storage_root", str(ROOT),
             "-conf_dir", "DoNotStarveTogether",
             "-cluster", "CarryCluster",
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
        deadline = time.time() + 260
        while time.time() < deadline:
            time.sleep(3)
            if log.is_file():
                text = log.read_text(encoding="utf-8", errors="ignore")
                if "Sim paused" in text or "World generated" in text:
                    break

        time.sleep(8)

        print("=" * 66)
        print("  复现：留声机放进背包 → 被移除（等价于带着进洞穴）")
        print("=" * 66)

        # 轮询探测：直到世界真的能 SpawnPrefab 为止。
        # 光看日志关键字不够 —— 世界日志说生成了，prefab 表可能还没就绪，
        # 那样 SpawnPrefab 会报 "Can't find prefab"，测出来全是假失败。
        ready = False
        for _ in range(60):
            proc.stdin.write(
                'print("PROBE", tostring(TheWorld ~= nil), '
                'tostring(Prefabs ~= nil and Prefabs.phonograph ~= nil))\n'
            )
            proc.stdin.flush()
            time.sleep(3)
            text = log.read_text(encoding="utf-8", errors="ignore") if log.is_file() else ""
            if "PROBE\ttrue\ttrue" in text:
                ready = True
                break

        print("  世界可 SpawnPrefab：%s" % ("是" if ready else "否（超时）"))
        if not ready:
            print("  结果：世界没准备好，测试无效，需要重跑。")
            return 1
        time.sleep(3)

        # 关键：必须用一个「确实没有 SoundEmitter」的对象当容器。
        # 原版 backpack 自带 SoundEmitter，用它测永远测不出来 ——
        # 真实崩溃里 owner 是别的 mod 的背包（amu_backpack），那种背包没有 SoundEmitter。
        steps = [
            'OWNER = SpawnPrefab("log")',
            'print("OWNER_HAS_SE_BEFORE", tostring(OWNER.SoundEmitter ~= nil))',
            'PH = SpawnPrefab("phonograph")',
            'REC = SpawnPrefab("pcbridge_record")',
            'PH.components.inventory:GiveItem(REC)',
            'PH.components.machine:TurnOn()',
            'PH.components.inventoryitem:RemoveFromScene()',
            'local cb = PH.components.inventoryitem.onputininventoryfn '
            'if cb then cb(PH, OWNER) end',
            'print("OWNER_HAS_SE_AFTER", tostring(OWNER.SoundEmitter ~= nil))',
            'PH.components.inventoryitem.owner = OWNER',
            'PH:Remove()',
            'print("SURVIVED_REMOVE", "yes")',
        ]
        for line in steps:
            proc.stdin.write(line + "\n")
            proc.stdin.flush()
            time.sleep(0.6)

        time.sleep(4)

        # 服务器还活着吗？
        alive = proc.poll() is None
        print()
        text = log.read_text(encoding="utf-8", errors="ignore") if log.is_file() else ""

        bag_has = "OWNER_HAS_SE_AFTER\ttrue" in text
        owner_bag = "OWNER_HAS_SE_BEFORE\tfalse" in text
        survived = "SURVIVED_REMOVE\tyes" in text
        sound_err = "SoundEmitter' (a nil value)" in text

        print("  容器原本没有 SoundEmitter : %s" % ("是" if owner_bag else "未确认"))
        print("  兜底后容器有了 SoundEmitter: %s" % ("是" if bag_has else "否"))
        print("  移除后代码继续往下执行     : %s" % ("是" if survived else "否"))
        print("  SoundEmitter nil 报错      : %s" % ("出现（失败）" if sound_err else "没有（通过）"))
        print("  服务器进程存活             : %s" % ("是（通过）" if alive else "已死（失败）"))
        print()

        ok = owner_bag and bag_has and survived and not sound_err and alive
        if ok:
            print("  结果：兜底生效，AV唱片 那种写法不会再崩服务器。")
            return 0

        print("  结果：兜底没生效，需要继续排查。")
        if sound_err:
            for line in text.splitlines():
                if "SoundEmitter" in line or "stack traceback" in line:
                    print("     > " + line.strip()[:150])
        return 1
    finally:
        if proc is not None:
            try:
                proc.stdin.write("c_shutdown(true)\n")
                proc.stdin.flush()
                proc.wait(timeout=15)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        remove_mod()


if __name__ == "__main__":
    sys.exit(main())

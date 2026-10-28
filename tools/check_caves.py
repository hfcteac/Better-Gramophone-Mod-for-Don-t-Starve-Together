# -*- coding: utf-8 -*-
"""测试 mod 在「地表 + 洞穴」双分片下能不能正常加载。

为什么需要这个脚本：
  饥荒的洞穴是一个独立的服务器进程（caves shard）。地表是 master shard。
  两者各跑一份 Lua 虚拟机、各加载一次 mod。很多 mod 在地表好好的，
  一到洞穴就出问题 —— 因为：

    1. 洞穴启动时 TheWorld 可能还没建好，直接写 TheWorld.ismastersim 会报错
    2. 洞穴不加载 mod 的话，玩家带着 mod 的物品（比如连接电脑唱片）进去，
       洞穴服务端不认识那个 prefab，表现就是「你已于服务器断开连接」

这个脚本同时起两个 shard，然后检查两边日志里 mod 有没有报错。

用法：
  python tools/check_caves.py
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

ROOT = Path(os.environ["TEMP"]) / "dstcave_check"
CLUSTER = ROOT / "DoNotStarveTogether" / "CaveCluster"
MASTER = CLUSTER / "Master"
CAVES = CLUSTER / "Caves"

MOD_ID = "myfirstmod_cavecheck"
MOD_DST = GAME_MODS / MOD_ID

MOD_FILES = ["modinfo.lua", "modmain.lua", "modicon.tex", "modicon.xml"]
MOD_PREFABS = ["pcbridge_record.lua"]

MOD_OVERRIDE = """return {
  ["%s"] = {
    enabled = true,
    configuration_options = { VOLUME = 1.0, CARRY_PLAY = true },
  },
}
""" % MOD_ID


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def install_mod():
    if MOD_DST.exists():
        shutil.rmtree(str(MOD_DST))
    MOD_DST.mkdir(parents=True)
    for name in MOD_FILES:
        shutil.copy2(str(PROJ / name), str(MOD_DST / name))
    prefabs = MOD_DST / "scripts" / "prefabs"
    prefabs.mkdir(parents=True)
    for name in MOD_PREFABS:
        shutil.copy2(str(PROJ / "scripts" / "prefabs" / name), str(prefabs / name))
    shutil.copy2(str(PROJ / "说明书.txt"), str(MOD_DST / "说明书.txt"))


def remove_mod():
    shutil.rmtree(str(MOD_DST), ignore_errors=True)


def setup():
    shutil.rmtree(ROOT, ignore_errors=True)

    write(CLUSTER / "cluster.ini", """[GAMEPLAY]
game_mode = survival
max_players = 2
pause_when_empty = false

[NETWORK]
cluster_name = CaveCheck
cluster_password =
offline_cluster = true
lan_only_cluster = true

[MISC]
console_enabled = true

[SHARD]
shard_enabled = true
bind_ip = 127.0.0.1
master_ip = 127.0.0.1
master_port = 10999
cluster_key = cavekey
""")

    write(MASTER / "server.ini", """[NETWORK]
server_port = 11310

[SHARD]
is_master = true
name = Master

[STEAM]
master_server_port = 27228
authentication_port = 8978
""")

    write(CAVES / "server.ini", """[NETWORK]
server_port = 11311

[SHARD]
is_master = false
name = Caves

[STEAM]
master_server_port = 27229
authentication_port = 8979
""")

    # 两个 shard 都必须启用 mod，否则洞穴不认识 mod 的物品
    write(MASTER / "modoverrides.lua", MOD_OVERRIDE)
    write(CAVES / "modoverrides.lua", MOD_OVERRIDE)

    # 洞穴世界必须声明有洞穴层，否则 caves shard 不会生成地下世界
    write(MASTER / "worldgenoverride.lua", """return {
  override_enabled = true,
  preset = "DST_CAVE",
}
""")
    write(CAVES / "worldgenoverride.lua", """return {
  override_enabled = true,
  preset = "DST_CAVE",
}
""")


def launch(shard_dir, shard_name):
    return subprocess.Popen(
        [EXE,
         "-persistent_storage_root", str(ROOT),
         "-conf_dir", "DoNotStarveTogether",
         "-cluster", "CaveCluster",
         "-shard", shard_name,
         "-skip_update_server_mods"],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=os.path.dirname(EXE),
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def wait_for_log(log, markers, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(3)
        if log.is_file():
            text = log.read_text(encoding="utf-8", errors="ignore")
            if any(m in text for m in markers):
                return text
    return log.read_text(encoding="utf-8", errors="ignore") if log.is_file() else ""


BAD = [
    "attempt to index",
    "attempt to call",
    "attempt to compare",
    "stack traceback",
    "invalid filepath",
    "SCRIPT ERROR",
    "Failed to load mod",
    "could not load mod",
    "nil value",
]


def analyze(label, log_path):
    if not log_path.is_file():
        print("  %-8s 日志不存在：%s" % (label, log_path))
        return False, ""

    text = log_path.read_text(encoding="utf-8", errors="ignore")

    loaded = "Loading modmain.lua" in text or "Loading mod: " in text
    prefab_ok = "Registering prefab file" in text
    bad = [b for b in BAD if b in text]

    print("  %-8s mod 加载=%s  prefab 注册=%s" % (
        label,
        "OK" if loaded else "未确认",
        "OK" if prefab_ok else "未确认",
    ))
    if bad:
        print("           发现错误关键字：%s" % ", ".join(bad))
        # 打印出错的相关行
        for line in text.splitlines():
            low = line.lower()
            if any(b.lower() in low for b in BAD):
                print("             > " + line.strip()[:160])
    return loaded and prefab_ok and not bad, text


def main():
    print("=" * 62)
    print("  双分片（地表 + 洞穴）加载测试")
    print("=" * 62)

    install_mod()
    master_proc = caves_proc = None
    try:
        setup()
        print("  正在启动地表服务器……")
        master_proc = launch(MASTER, "Master")
        master_text = wait_for_log(
            MASTER / "server_log.txt",
            ["Loading modmain.lua", "Registering prefab file"],
            timeout=240,
        )

        print("  正在启动洞穴服务器……")
        caves_proc = launch(CAVES, "Caves")
        # 洞穴要先等世界生成，比地表慢得多
        caves_text = wait_for_log(
            CAVES / "server_log.txt",
            ["Loading modmain.lua"],
            timeout=240,
        )

        # 再给一点时间让洞穴真正跑起来
        time.sleep(20)

        print()
        print("-" * 62)
        master_ok, _ = analyze("Master", MASTER / "server_log.txt")
        caves_ok, _ = analyze("Caves", CAVES / "server_log.txt")
        print("-" * 62)
        print()

        if master_ok and caves_ok:
            print("  结果：地表和洞穴都正常加载了 mod。")
            return 0

        print("  结果：有分片加载有问题，详见上面的错误行。")
        print()
        print("  日志位置：")
        print("    %s" % (MASTER / "server_log.txt"))
        print("    %s" % (CAVES / "server_log.txt"))
        return 1
    finally:
        for proc in (master_proc, caves_proc):
            if proc is None:
                continue
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

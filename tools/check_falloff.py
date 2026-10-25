# -*- coding: utf-8 -*-
"""验证音量随距离衰减的曲线（纯数学复现 modmain 里的算法）。

对应 modmain.lua：
    falloff  = 1 - (距离 - FULL) / (SILENT - FULL)
    volume   = VOLUME * clamp(falloff, 0, 1)
"""

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FULL = 12
SILENT = 60
VOLUME = 1.0


def volume_at(distance):
    if distance >= SILENT:
        return 0.0
    falloff = 1 - (distance - FULL) / (SILENT - FULL)
    return VOLUME * max(0.0, min(1.0, falloff))


def bar(value, width=32):
    filled = int(round(value * width))
    return "#" * filled + "." * (width - filled)


def main():
    print("满音量范围 %d 格，静音范围 %d 格" % (FULL, SILENT))
    print("=" * 62)
    print("%-10s %-8s %s" % ("距离(格)", "音量", "曲线"))
    print("-" * 62)

    for distance in (0, 5, 10, 12, 15, 20, 25, 30, 36, 40, 45, 50, 55, 59, 60, 70):
        value = volume_at(distance)
        print("%-10d %-8.0f%% %s" % (distance, value * 100, bar(value)))

    print("-" * 62)

    # 单调性检查：越远必须越小（或相等），绝不能回升
    prev = None
    ok = True
    for distance in range(0, 81):
        value = volume_at(distance)
        if prev is not None and value > prev + 1e-9:
            print("❌ 距离 %d 格音量回升了：%.3f -> %.3f" % (distance, prev, value))
            ok = False
        prev = value

    print("单调递减检查:", "通过" if ok else "失败")

    # 边界检查
    checks = [
        ("12 格内满音量", volume_at(0) == 1.0 and volume_at(12) == 1.0),
        ("60 格外静音", volume_at(60) == 0.0 and volume_at(59) > 0.0),
        ("中途没有跳变", abs(volume_at(35) - volume_at(37)) < 0.05),
    ]
    for name, passed in checks:
        print(("OK    " if passed else "FAIL  ") + name)

    return 0 if ok and all(p for _, p in checks) else 1


if __name__ == "__main__":
    sys.exit(main())

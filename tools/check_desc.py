# -*- coding: utf-8 -*-
"""检查 modinfo 说明会不会被游戏截断。

游戏实际限制（scripts/widgets/redux/modstab.lua）：
    maxlines = 17
    maxchars = 77 / 行
    width    = 505 px，CHATFONT 22 号 → 约 21 个汉字宽

这里用保守的 21 个汉字宽估算，任何一行超宽都算超行。
"""

import sys
from pathlib import Path

MAX_LINES = 17
# 用户实测：一行最多能看到 36 个汉字（跟分辨率缩放有关）
CHARS_PER_LINE = 36
MAX_CHARS = 77        # 游戏的字符数硬上限

MODINFO = Path(r"C:\Users\hafeizhou\Desktop\Dontstarvetogethrer\modinfo.lua")


def visual_width(line):
    """汉字算 1 个字宽，ASCII 算 0.55。"""
    total = 0.0
    for ch in line:
        total += 0.55 if ord(ch) < 128 else 1.0
    return total


def main():
    text = MODINFO.read_text(encoding="utf-8")
    desc = text.split("[[", 1)[1].split("]]", 1)[0]
    lines = desc.split("\n")
    # 首尾空行游戏会忽略
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()

    max_chars_per_line = CHARS_PER_LINE
    rendered = 0
    ok = True

    print("渲染行数上限 %d，估计每行可放 %.1f 个汉字" % (MAX_LINES, max_chars_per_line))
    print("-" * 60)

    for index, line in enumerate(lines, 1):
        width = visual_width(line)
        wraps = max(1, int(width / max_chars_per_line) + (1 if width % max_chars_per_line else 0))
        rendered += wraps
        flag = "  折成 %d 行" % wraps if wraps > 1 else ""
        if len(line) > MAX_CHARS:
            flag += "  超过 %d 字符" % MAX_CHARS
        print("%2d| %-44s w=%.1f%s" % (index, line, width, flag))

    print("-" * 60)
    print("实际占 %d 行 / 上限 %d 行" % (rendered, MAX_LINES))
    if rendered > MAX_LINES:
        print("结果：会被截断，超了 %d 行" % (rendered - MAX_LINES))
        return 1

    print("结果：放得下，富余 %d 行" % (MAX_LINES - rendered))
    return 0


if __name__ == "__main__":
    sys.exit(main())

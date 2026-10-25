# -*- coding: utf-8 -*-
"""从截图里找出按钮的实际像素位置，避免靠估算点错。"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main():
    path = Path(sys.argv[1])
    image = np.array(Image.open(path).convert("RGB"))
    height, width = image.shape[:2]
    print("图片 %dx%d" % (width, height))

    # 按钮边框是灰色细线，找每一列「接近 #A0A0A0 的纵向连续段」
    gray = image.mean(axis=2)
    columns = []
    for x in range(width):
        col = gray[:, x]
        dark = int(np.sum(col < 190))
        if dark > height * 0.25:
            columns.append(x)

    # 合并相邻列
    groups = []
    for x in columns:
        if groups and x - groups[-1][-1] <= 2:
            groups[-1].append(x)
        else:
            groups.append([x])

    edges = [int(np.mean(g)) for g in groups]
    print("检测到竖线 x =", edges)

    if len(edges) >= 2:
        print("\n按钮区间（百分比，窗口宽 %d）：" % width)
        for i in range(0, len(edges) - 1, 2):
            left, right = edges[i], edges[i + 1]
            center = (left + right) / 2.0
            print("  %d-%d  中心 %.4f" % (left, right, center / width))


if __name__ == "__main__":
    main()

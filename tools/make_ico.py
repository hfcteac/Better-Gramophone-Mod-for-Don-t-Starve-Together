# -*- coding: utf-8 -*-
"""把图片转成 Windows 的 .ico（播放器 exe 和快捷方式用）。

用法：
    python tools/make_ico.py PHOTO.jpg player.ico
"""

import sys
from pathlib import Path

from PIL import Image

SIZES = [16, 24, 32, 48, 64, 128, 256]


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1

    source = Path(sys.argv[1])
    target = Path(sys.argv[2])

    image = Image.open(source).convert("RGBA")

    # 居中裁成正方形，避免拉伸变形
    side = min(image.size)
    left = (image.width - side) // 2
    top = (image.height - side) // 2
    image = image.crop((left, top, left + side, top + side))

    base = image.resize((256, 256), Image.LANCZOS)
    target.parent.mkdir(parents=True, exist_ok=True)
    base.save(target, format="ICO", sizes=[(size, size) for size in SIZES])

    print("生成 %s  (%d 字节)" % (target, target.stat().st_size))
    print("包含尺寸:", ", ".join("%dx%d" % (s, s) for s in SIZES))
    return 0


if __name__ == "__main__":
    sys.exit(main())

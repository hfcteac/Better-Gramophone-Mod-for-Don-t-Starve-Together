# -*- coding: utf-8 -*-
"""解码生成的 .tex，和原图对比，验证编码没写错。"""
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))


def parse_ktex(blob):
    assert blob[:4] == b"KTEX", "不是 KTEX"
    header = struct.unpack("<I", blob[4:8])[0]
    fmt = (header >> 4) & 31
    mips = (header >> 13) & 31
    offset = 8
    entries = []
    for _ in range(mips):
        w, h, pitch, size = struct.unpack("<HHHI", blob[offset:offset + 10])
        entries.append((w, h, pitch, size))
        offset += 10

    levels = []
    for w, h, pitch, size in entries:
        levels.append((w, h, blob[offset:offset + size]))
        offset += size

    return fmt, entries, levels, offset


def decode_dxt5_block(block):
    a0, a1 = block[0], block[1]
    bits = int.from_bytes(block[2:8], "little")

    if a0 > a1:
        alphas = [a0, a1] + [((8 - i) * a0 + (i - 1) * a1) // 7 for i in range(2, 8)]
    else:
        alphas = [a0, a1] + [((6 - i) * a0 + (i - 1) * a1) // 5 for i in range(2, 6)] + [0, 255]

    ai = [(bits >> (3 * i)) & 0x7 for i in range(16)]

    c0, c1 = struct.unpack("<HH", block[8:12])
    cb = int.from_bytes(block[12:16], "little")

    def to_rgb(c):
        r = ((c >> 11) & 0x1F) * 255 // 31
        g = ((c >> 5) & 0x3F) * 255 // 63
        b = (c & 0x1F) * 255 // 31
        return np.array([r, g, b], dtype=np.int32)

    p0, p1 = to_rgb(c0), to_rgb(c1)
    if c0 > c1:
        palette = [p0, p1, (2 * p0 + p1) // 3, (p0 + 2 * p1) // 3]
    else:
        palette = [p0, p1, (p0 + p1) // 2, np.zeros(3, dtype=np.int32)]

    out = np.zeros((4, 4, 4), dtype=np.uint8)
    for i in range(16):
        color = palette[(cb >> (2 * i)) & 0x3]
        out[i // 4, i % 4, :3] = color
        out[i // 4, i % 4, 3] = alphas[ai[i]]
    return out


def decode_level(width, height, payload):
    blocks_x = (width + 3) // 4
    blocks_y = (height + 3) // 4
    image = np.zeros((blocks_y * 4, blocks_x * 4, 4), dtype=np.uint8)
    pos = 0
    for by in range(blocks_y):
        for bx in range(blocks_x):
            block = payload[pos:pos + 16]
            pos += 16
            image[by * 4:by * 4 + 4, bx * 4:bx * 4 + 4] = decode_dxt5_block(block)
    return image[:height, :width]


def main():
    if len(sys.argv) < 3:
        print("用法: verify_tex.py <file.tex> <source.jpg>")
        return 1

    tex_path = Path(sys.argv[1])
    src_path = Path(sys.argv[2])
    blob = tex_path.read_bytes()

    fmt, entries, levels, consumed = parse_ktex(blob)
    print("格式: fmt=%d (2=DXT5)  mip 数=%d  读掉 %d/%d 字节"
          % (fmt, len(entries), consumed, len(blob)))

    width, height, payload = levels[0]
    decoded = decode_level(width, height, payload)

    # 纹理里行 0 是最下面一行，比较前要翻回来
    decoded = decoded[::-1]

    reference = np.array(
        Image.open(src_path).convert("RGBA").resize((width, height), Image.LANCZOS),
        dtype=np.uint8,
    )

    diff = decoded[:, :, :3].astype(np.float32) - reference[:, :, :3].astype(np.float32)
    mse = float(np.mean(diff ** 2))
    psnr = 10 * np.log10(255.0 ** 2 / mse) if mse > 0 else 99.0
    print("PSNR = %.2f dB  (35+ 肉眼看不出差别)" % psnr)

    out = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("decoded_preview.png")
    Image.fromarray(decoded, "RGBA").save(out)
    print("解码预览已保存:", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""把 .tex 解码成 png，用来检查朝向。"""
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image


def decode_block(block):
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
        return np.array([((c >> 11) & 0x1F) * 255 // 31,
                         ((c >> 5) & 0x3F) * 255 // 63,
                         (c & 0x1F) * 255 // 31], dtype=np.int32)

    p0, p1 = to_rgb(c0), to_rgb(c1)
    if c0 > c1:
        palette = [p0, p1, (2 * p0 + p1) // 3, (p0 + 2 * p1) // 3]
    else:
        palette = [p0, p1, (p0 + p1) // 2, np.zeros(3, dtype=np.int32)]

    out = np.zeros((4, 4, 4), dtype=np.uint8)
    for i in range(16):
        out[i // 4, i % 4, :3] = palette[(cb >> (2 * i)) & 0x3]
        out[i // 4, i % 4, 3] = alphas[ai[i]]
    return out


def decode(tex_path):
    blob = Path(tex_path).read_bytes()
    assert blob[:4] == b"KTEX"
    header = struct.unpack("<I", blob[4:8])[0]
    mips = (header >> 13) & 31
    offset = 8
    entries = []
    for _ in range(mips):
        w, h, pitch, size = struct.unpack("<HHHI", blob[offset:offset + 10])
        entries.append((w, h, size))
        offset += 10

    w, h, size = entries[0]
    payload = blob[offset:offset + size]

    bx, by = (w + 3) // 4, (h + 3) // 4
    img = np.zeros((by * 4, bx * 4, 4), dtype=np.uint8)
    pos = 0
    for yy in range(by):
        for xx in range(bx):
            img[yy * 4:yy * 4 + 4, xx * 4:xx * 4 + 4] = decode_block(payload[pos:pos + 16])
            pos += 16
    return img[:h, :w]


if __name__ == "__main__":
    src = sys.argv[1]
    dst = sys.argv[2]
    flip = len(sys.argv) > 3 and sys.argv[3] == "flip"
    arr = decode(src)
    if flip:
        arr = arr[::-1, :, :]
    Image.fromarray(arr, "RGBA").save(dst)
    print("saved", dst, arr.shape)

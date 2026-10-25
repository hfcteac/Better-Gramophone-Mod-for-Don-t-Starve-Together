# -*- coding: utf-8 -*-
"""把图片转成饥荒用的 .tex（KTEX 容器 + DXT5 压缩）和配套的 .xml 图集描述。

KTEX 结构（反向确认自现成 mod 的 modicon.tex）：
    "KTEX"                         4 字节
    uint32 header                  位域：pixel_format(4-8) texture_type(9-12)
                                        mipmaps(13-17) flags(18-19) fill(20-31)
    每个 mipmap 10 字节表项          width u16, height u16, pitch u16, data_size u32
    mipmap 数据                     DXT5 块，从大到小拼接

用法：
    python tools/img_to_tex.py PHOTO.jpg mods/myfirstmod/modicon
"""

import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image

DXT5_FORMAT = 2
TEXTURE_TYPE_2D = 1
HEADER_FLAGS = 3
HEADER_FILL = 4095


def _rgb_to_565(rgb):
    r = (rgb[:, 0] >> 3).astype(np.uint16)
    g = (rgb[:, 1] >> 2).astype(np.uint16)
    b = (rgb[:, 2] >> 3).astype(np.uint16)
    return (r << 11) | (g << 5) | b


def _565_to_rgb(c):
    c = c.astype(np.uint32)
    r = ((c >> 11) & 0x1F) * 255 // 31
    g = ((c >> 5) & 0x3F) * 255 // 63
    b = (c & 0x1F) * 255 // 31
    return np.stack((r, g, b), axis=-1).astype(np.int32)


def _blocks(image, size=4):
    """把 HxWx4 的图切成 4x4 块，返回 (n, 16, 4)。"""
    h, w = image.shape[:2]
    pad_h = (-h) % size
    pad_w = (-w) % size
    if pad_h or pad_w:
        image = np.pad(image, ((0, pad_h), (0, pad_w), (0, 0)), mode="edge")

    bh, bw = image.shape[0] // size, image.shape[1] // size
    view = image.reshape(bh, size, bw, size, image.shape[2])
    view = view.transpose(0, 2, 1, 3, 4)
    return view.reshape(bh * bw, size * size, image.shape[2])


def dxt5_block_alpha(alpha):
    """alpha: (n, 16) uint8 → 8 字节 alpha 块"""
    a0 = alpha.max(axis=1).astype(np.int32)
    a1 = alpha.min(axis=1).astype(np.int32)

    # 全等块：两端点相同，索引全 0，解码回来还是同一个值
    palette = np.empty((len(alpha), 8), dtype=np.int32)
    palette[:, 0] = a0
    palette[:, 1] = a1
    for i in range(2, 8):
        palette[:, i] = ((8 - i) * a0 + (i - 1) * a1) // 7

    diff = np.abs(alpha[:, :, None] - palette[:, None, :])
    idx = diff.argmin(axis=2)

    bits = np.zeros(len(alpha), dtype=np.uint64)
    for i in range(16):
        bits |= idx[:, i].astype(np.uint64) << np.uint64(3 * i)

    out = np.empty((len(alpha), 8), dtype=np.uint8)
    out[:, 0] = np.clip(a0, 0, 255).astype(np.uint8)
    out[:, 1] = np.clip(a1, 0, 255).astype(np.uint8)
    for i in range(6):
        out[:, 2 + i] = ((bits >> np.uint64(8 * i)) & np.uint64(0xFF)).astype(np.uint8)
    return out


def dxt5_block_color(rgb):
    """rgb: (n, 16, 3) uint8 → 8 字节颜色块（565 两端点 + 16 个 2 位索引）"""
    pixels = rgb.astype(np.int32)
    count = len(rgb)

    # 经典做法：按每通道包围盒取端点，再往里缩 1/16，减少越界量化误差
    lo = pixels.min(axis=1)
    hi = pixels.max(axis=1)
    inset = (hi - lo) // 16
    lo = np.clip(lo + inset, 0, 255)
    hi = np.clip(hi - inset, 0, 255)

    e0 = _rgb_to_565(hi.astype(np.uint8))
    e1 = _rgb_to_565(lo.astype(np.uint8))

    swap = e0 < e1
    if np.any(swap):
        e0 = e0.copy()
        e1 = e1.copy()
        e0[swap], e1[swap] = e1[swap], e0[swap]

    same = e0 == e1
    if np.any(same):
        e1 = e1.copy()
        e1[same] = np.where(e0[same] > 0, e0[same] - 1, 0)

    def build(ea, eb):
        p0 = _565_to_rgb(ea)
        p1 = _565_to_rgb(eb)
        p2 = (2 * p0 + p1) // 3
        p3 = (p0 + 2 * p1) // 3
        palette = np.stack((p0, p1, p2, p3), axis=1)
        diff = np.abs(pixels[:, :, None, :] - palette[:, None, :, :]).sum(axis=3)
        return diff.argmin(axis=2).astype(np.uint32), diff

    idx, diff = build(e0, e1)
    best = diff.min(axis=2).sum(axis=1)
    best_idx = idx

    # 再试一次：把端点沿误差方向微调一格，取更好的那个
    for de0, de1 in ((1, 0), (0, 1), (-1, 0), (0, -1)):
        ea = np.clip(e0.astype(np.int32) + de0, 0, 0xFFFF).astype(np.uint16)
        eb = np.clip(e1.astype(np.int32) + de1, 0, 0xFFFF).astype(np.uint16)
        if np.any(ea <= eb):
            continue
        cand_idx, cand_diff = build(ea, eb)
        cand_best = cand_diff.min(axis=2).sum(axis=1)
        better = cand_best < best
        if np.any(better):
            best = np.where(better, cand_best, best)
            best_idx = np.where(better[:, None], cand_idx, best_idx)
            e0 = np.where(better, ea, e0).astype(np.uint16)
            e1 = np.where(better, eb, e1).astype(np.uint16)

    idx = best_idx
    bits = np.zeros(count, dtype=np.uint32)
    for i in range(16):
        bits |= idx[:, i] << np.uint32(2 * i)

    out = np.empty((count, 8), dtype=np.uint8)
    out[:, 0] = (e0 & 0xFF).astype(np.uint8)
    out[:, 1] = (e0 >> 8).astype(np.uint8)
    out[:, 2] = (e1 & 0xFF).astype(np.uint8)
    out[:, 3] = (e1 >> 8).astype(np.uint8)
    for i in range(4):
        out[:, 4 + i] = ((bits >> np.uint32(8 * i)) & np.uint32(0xFF)).astype(np.uint8)
    return out


def encode_dxt5(image):
    """image: HxWx4 uint8 → DXT5 字节"""
    blocks = _blocks(image)                  # (n, 16, 4)
    alpha_part = dxt5_block_alpha(blocks[:, :, 3])
    color_part = dxt5_block_color(blocks[:, :, :3])
    combined = np.concatenate((alpha_part, color_part), axis=1)
    return combined.tobytes()


def downsample(image, size):
    """用 PIL 做高质量的缩小。"""
    img = Image.fromarray(image, mode="RGBA")
    return np.array(img.resize((size, size), Image.LANCZOS), dtype=np.uint8)


def build_ktex(image_bytes, size):
    """生成完整 KTEX 文件内容。"""
    mips = []
    level = np.array(Image.open(image_bytes).convert("RGBA"), dtype=np.uint8)
    if level.shape[0] != size or level.shape[1] != size:
        level = np.array(Image.fromarray(level).resize((size, size), Image.LANCZOS), dtype=np.uint8)

    # 饥荒/OpenGL 的纹理是「行 0 = 图片最下面那一行」，
    # 所以要先上下翻转，否则游戏里会看到倒立的图。
    level = level[::-1].copy()

    current = size
    while True:
        mips.append((current, current, level))
        if current == 1:
            break
        current = max(1, current // 2)
        level = downsample(level, current)

    data_chunks = []
    entries = []
    for w, h, img in mips:
        payload = encode_dxt5(img)
        pitch = ((w + 3) // 4) * 16
        entries.append((w, h, pitch, len(payload)))
        data_chunks.append(payload)

    header = ((DXT5_FORMAT << 4)
              | (TEXTURE_TYPE_2D << 9)
              | (len(entries) << 13)
              | (HEADER_FLAGS << 18)
              | (HEADER_FILL << 20))

    out = bytearray()
    out += b"KTEX"
    out += struct.pack("<I", header)
    for w, h, pitch, size_bytes in entries:
        out += struct.pack("<HHHI", w, h, pitch, size_bytes)
    for chunk in data_chunks:
        out += chunk

    return bytes(out), entries


def write_atlas_xml(path, tex_name, size):
    inset = 0.5 / size
    xml = (
        '<Atlas><Texture filename="%s" /><Elements>'
        '<Element name="%s" u1="%.8f" u2="%.8f" v1="%.8f" v2="%.8f" />'
        "</Elements></Atlas>"
    ) % (tex_name, tex_name, inset, 1.0 - inset, inset, 1.0 - inset)
    Path(path).write_text(xml, encoding="utf-8")


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1

    source = Path(sys.argv[1])
    target = Path(sys.argv[2])
    size = int(sys.argv[3]) if len(sys.argv) > 3 else 128

    blob, entries = build_ktex(source, size)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.with_suffix(".tex").write_bytes(blob)
    write_atlas_xml(target.with_suffix(".xml"), target.with_suffix(".tex").name, size)

    print("生成 %s  (%d 字节)" % (target.with_suffix(".tex"), len(blob)))
    for w, h, pitch, sz in entries:
        print("   mip %dx%d  pitch=%d  size=%d" % (w, h, pitch, sz))
    print("生成 %s" % target.with_suffix(".xml"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

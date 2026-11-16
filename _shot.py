# -*- coding: utf-8 -*-
"""把裁剪区域存成 PNG（无第三方库），供人工核对界面。"""
import ctypes
import struct
import sys
import zlib

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass


class BIH(ctypes.Structure):
    _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
                ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
                ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32),
                ("biYPelsPerMeter", ctypes.c_int32), ("biClrUsed", ctypes.c_uint32),
                ("biClrImportant", ctypes.c_uint32)]


def screen_bgra():
    sw, sh = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    hdc = user32.GetDC(0)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, sw, sh)
    gdi32.SelectObject(mem, bmp)
    gdi32.BitBlt(mem, 0, 0, sw, sh, hdc, 0, 0, 0x00CC0020)
    bi = BIH()
    bi.biSize = ctypes.sizeof(BIH)
    bi.biWidth = sw
    bi.biHeight = -sh
    bi.biPlanes = 1
    bi.biBitCount = 32
    bi.biCompression = 0
    buf = ctypes.create_string_buffer(sw * sh * 4)
    gdi32.GetDIBits(mem, bmp, 0, sh, buf, ctypes.byref(bi), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(0, hdc)
    return sw, sh, buf.raw


def save_png(path, sw, sh, data, box, step):
    x0, y0, cw, ch = box
    cw = min(cw, sw - x0)
    ch = min(ch, sh - y0)
    ow, oh = max(1, cw // step), max(1, ch // step)
    rows = []
    for j in range(oh):
        src = ((y0 + j * step) * sw + x0) * 4
        line = bytearray(ow * 3)
        for i in range(ow):
            p = src + i * step * 4
            line[i * 3] = data[p + 2]
            line[i * 3 + 1] = data[p + 1]
            line[i * 3 + 2] = data[p]
        rows.append(b"\x00" + bytes(line))
    co = zlib.compressobj(9)
    raw = co.compress(b"".join(rows)) + co.flush()

    def chunk(tag, body):
        c = tag + body
        return struct.pack(">I", len(body)) + c + struct.pack(">I", zlib.crc32(c) & 0xffffffff)

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", ow, oh, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", raw) + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)
    print("  -> %s  %dx%d  %d KB" % (path, ow, oh, len(png) // 1024))


if __name__ == "__main__":
    # 用法：_shot.py out.png x y w h [step]
    out = sys.argv[1]
    box = [int(v) for v in sys.argv[2:6]]
    step = int(sys.argv[6]) if len(sys.argv) > 6 else 1
    sw, sh, data = screen_bgra()
    print("屏幕 %dx%d" % (sw, sh))
    save_png(out, sw, sh, data, box, step)

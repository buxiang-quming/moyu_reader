# -*- coding: utf-8 -*-
"""悬停显隐的时序验收：注入假鼠标坐标，量「移开后多久消失」「移回来多久出现」。

不真的挪系统光标（锁屏/远程断开会话时 GetCursorPos 会返回 0,0），
所以结果稳定可重复。
"""
import os
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

import wapi
wapi.set_dpi_aware()

import tkinter as tk
from app import ReaderApp

FAIL = []
PT = [-1000, -1000]          # 注入给 _pointer() 的假坐标


def ck(name, cond, extra=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else "  " + str(extra)))
    if not cond:
        FAIL.append(name)


root = tk.Tk()
app = ReaderApp(root)
app._pointer = lambda: (PT[0], PT[1])


def pump(ms):
    end = time.time() + ms / 1000.0
    while time.time() < end:
        root.update()
        time.sleep(0.004)


def mv(x, y):
    PT[0], PT[1] = x, y


def wait_state(want_visible, limit=2.0):
    t0 = time.time()
    while time.time() - t0 < limit:
        root.update()
        if app.visible == want_visible:
            return time.time() - t0
        time.sleep(0.004)
    return None


items = app.store.shelf()
CX = CY = 0


def s1():
    mv(-1000, -1000)
    app.open_shelf_item(items[0])
    root.after(1500, s2)


def s2():
    global CX, CY
    w, h = root.winfo_width(), root.winfo_height()
    CX = root.winfo_rootx() + w // 2
    CY = root.winfo_rooty() + h // 2
    print("  阅读窗 %dx%d @ %d,%d 中心 (%d,%d)"
          % (w, h, root.winfo_rootx(), root.winfo_rooty(), CX, CY))
    ck("刚进阅读态是显示的", app.visible)

    mv(CX, CY)
    pump(300)
    ck("鼠标在窗口内保持显示", app.visible)
    ck("「刚选完书先按住」已解除", app._hold_until == 0.0)

    # 1) 移出窗口（不在热区）→ 立刻消失
    mv(120, 620)
    took = wait_state(False)
    ck("移出后自动隐藏", took is not None, "2s 内没隐藏")
    if took is not None:
        print("  移出 → 消失 %.0f ms" % (took * 1000))
        ck("隐藏够快（<120ms）", took < 0.12, "%.0f ms" % (took * 1000))

    # 2) 回到原来那块地方 → 重新出现
    mv(CX, CY)
    took = wait_state(True)
    ck("移回原位置重新显示", took is not None, "2s 内没显示")
    if took is not None:
        print("  移回 → 显示 %.0f ms" % (took * 1000))
        ck("重新显示够快（<400ms）", took < 0.4, "%.0f ms" % (took * 1000))

    # 3) 反复来回
    n = 0
    for _ in range(3):
        mv(120, 620)
        if wait_state(False):
            n += 1
        mv(CX, CY)
        if wait_state(True):
            n += 1
    ck("反复 3 轮都能藏能出", n == 6, n)

    # 4) 窗口边缘 ±10px 缓冲：刚好出界才藏
    mv(CX, root.winfo_rooty() + root.winfo_height() + 4)
    ck("界内 4px 缓冲仍算在里面", wait_state(False, 0.4) is None)
    mv(CX, root.winfo_rooty() + root.winfo_height() + 40)
    ck("超出缓冲就藏", wait_state(False, 0.5) is not None)

    root.after(200, s3)


def s3():
    # 5) 老板键后，鼠标扫过原位置不该自动出现；唤出键能恢复
    mv(CX, CY)
    pump(200)
    app.boss_key()
    pump(200)
    ck("老板键后隐藏", not app.visible)
    mv(200, 640)
    pump(150)
    mv(CX, CY)
    pump(500)
    ck("老板键后扫过原位不自动出现", not app.visible, app.visible)
    app.show()
    pump(200)
    ck("唤出键能恢复", app.visible)

    # 6) 钉住后移开不消失
    app.toggle_lock()
    mv(200, 640)
    pump(600)
    ck("钉住后移开不消失", app.visible)
    app.toggle_lock()
    ck("松开后立刻消失", wait_state(False, 0.5) is not None)
    print("")
    print("失败 %d 项" % len(FAIL) if FAIL else "全部通过")
    root.after(150, app.quit)


root.after(400, s1)
root.mainloop()

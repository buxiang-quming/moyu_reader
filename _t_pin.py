# -*- coding: utf-8 -*-
"""验证「移开不隐藏」的根因已修：单击正文不再把窗口钉死，钉住必须有可见标识。

用真鼠标（SetCursorPos）走完整链路。
"""
import ctypes
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

u = ctypes.windll.user32
FAIL = []


def ck(name, cond, extra=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else "  " + str(extra)))
    if not cond:
        FAIL.append(name)


def move(x, y):
    u.SetCursorPos(int(x), int(y))


class E(object):
    def __init__(self, x, y):
        self.x, self.y, self.x_root, self.y_root = x, y, x, y


root = tk.Tk()
app = ReaderApp(root)


def pump(ms):
    end = time.time() + ms / 1000.0
    while time.time() < end:
        root.update()
        time.sleep(0.005)


def wait(cond, ms):
    t0 = time.time()
    while (time.time() - t0) * 1000 < ms:
        root.update()
        if cond():
            return int((time.time() - t0) * 1000)
        time.sleep(0.005)
    return -1


def run():
    print("=" * 56)
    pump(900)
    app.open_shelf_item(app.store.shelf()[0])
    pump(1200)
    app._hold_until = 0.0

    rx, ry = root.winfo_rootx(), root.winfo_rooty()
    cx, cy = rx + root.winfo_width() // 2, ry + root.winfo_height() // 2
    print("  阅读窗 %dx%d @ %d,%d  click_pin=%s  mouse_page=%s"
          % (root.winfo_width(), root.winfo_height(), rx, ry,
             app.click_pin, app.mouse_page))

    # 1) 单击正文：默认不该钉住
    move(cx, cy)
    shown = wait(lambda: app.visible, 1500)
    print("  移入后 %s" % ("%d ms 显示" % shown if shown >= 0 else "1.5 秒没显示"))
    ck("鼠标在窗内可见", app.visible)
    app._on_press(E(cx, cy))
    app._on_release(E(cx, cy))
    pump(250)
    ck("单击正文不再钉住", app.locked is False, app.locked)

    # 2) 移开 → 应立刻隐藏
    move(80, 1000)
    t = wait(lambda: not app.visible, 2000)
    print("  单击后移开 → %s" % ("%d ms 隐藏" % t if t >= 0 else "2 秒没隐藏"))
    ck("单击后移开仍会自动隐藏", t >= 0)
    ck("隐藏够快（<300ms）", 0 <= t < 300, t)

    # 3) Ctrl+P 钉住 → 移开不隐藏，且右下角有「已钉住」
    move(cx, cy)
    ck("移回能显示", wait(lambda: app.visible, 2000) >= 0)
    app.toggle_lock()
    pump(300)
    ck("Ctrl+P 后处于钉住", app.locked is True)
    badge = app.pct.cget("text")
    print("  角标文字 = %r" % badge)
    ck("钉住时右下角显示「已钉住」", "已钉住" in str(badge), badge)
    move(80, 1000)
    t2 = wait(lambda: not app.visible, 2500)
    ck("钉住后移开不隐藏（符合预期）", t2 == -1)

    # 4) 再按 Ctrl+P 松开 → 应该恢复隐藏
    app.toggle_lock()
    pump(200)
    ck("松开后 locked=False", app.locked is False)
    t3 = wait(lambda: not app.visible, 2000)
    print("  松开后 %s" % ("%d ms 隐藏" % t3 if t3 >= 0 else "2 秒没隐藏"))
    ck("松开后恢复自动隐藏", t3 >= 0)

    # 5) 老板键也应当解掉钉住
    move(cx, cy)
    wait(lambda: app.visible, 1500)
    app.locked = True
    app.boss_key()
    pump(200)
    ck("老板键后 locked 被清", app.locked is False)
    ck("老板键后窗口不可见", app.visible is False)

    print("")
    print("失败 %d 项" % len(FAIL) if FAIL else "全部通过")
    root.after(100, app.quit)


root.after(1000, run)
root.mainloop()

# -*- coding: utf-8 -*-
"""启动流程验收：先开书架 → 选书 → 进阅读态。

不依赖鼠标自动化，直接驱动 ReaderApp 的状态切换并截图（data/*.png）。
"""
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

import wapi
wapi.set_dpi_aware()

import tkinter as tk
from app import ReaderApp
import _shot

OUT = os.path.join(BASE, "data")
if not os.path.isdir(OUT):
    os.makedirs(OUT)

FAIL = []


def ck(name, cond, extra=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else "  " + str(extra)))
    if not cond:
        FAIL.append(name)


def snap(win, name, pad=10, step=2):
    x = max(0, win.winfo_rootx() - pad)
    y = max(0, win.winfo_rooty() - pad)
    w = win.winfo_width() + pad * 2
    h = win.winfo_height() + pad * 2
    sw, sh, data = _shot.screen_bgra()
    print("  截图 %s  区域 %d,%d %dx%d" % (name, x, y, w, h))
    _shot.save_png(os.path.join(OUT, name), sw, sh, data,
                   (x, y, w, h), step)


root = tk.Tk()
app = ReaderApp(root)
items = app.store.shelf()
print("书架共 %d 本" % len(items))


def step1():
    ck("启动后 stage = shelf", app.stage == "shelf", app.stage)
    ck("书架窗口已打开", app._shelf_win is not None)
    ck("阅读窗未显示", root.winfo_viewable() == 0, root.winfo_viewable())
    ck("没有自动加载书", app.book is None, app.book)
    if app._shelf_win is not None:
        w = app._shelf_win.win
        print("  书架 %dx%d @ %d,%d" % (w.winfo_width(), w.winfo_height(),
                                        w.winfo_rootx(), w.winfo_rooty()))
        w.lift()
        w.focus_force()
    root.after(500, step2)


def step2():
    ck("书架卡片数 = 书数 + 1", len(app._shelf_win._cards) == len(items) + 1,
       len(app._shelf_win._cards))
    snap(app._shelf_win.win, "flow_1_shelf.png", step=2)
    app.open_shelf_item(items[0])
    root.after(1200, step3)


def step3():
    app.locked = True
    b = app.book
    ck("选书后 stage = reading", app.stage == "reading", app.stage)
    ck("书已加载", b is not None and b.name == items[0].get("title"),
       b.name if b else None)
    ck("书架已收起", app._shelf_win is None)
    ck("阅读窗已显示", root.winfo_viewable() == 1, root.winfo_viewable())
    w, h = root.winfo_width(), root.winfo_height()
    print("  阅读窗 %dx%d @ %d,%d  第 %d/%d 章  正文 %d 字"
          % (w, h, root.winfo_rootx(), root.winfo_rooty(),
             app.ci + 1, len(b.chapters), len(app.text.get("1.0", "end"))))
    ck("尺寸仍为设置的窄窗", w == int(app.store.get("width")) and
       h == int(app.store.get("height")), (w, h))
    ck("正文已渲染", len(app.text.get("1.0", "end").strip()) > 50)
    ck("窗口在屏幕内", root.winfo_rooty() + h <= root.winfo_screenheight() and
       root.winfo_rootx() + w <= root.winfo_screenwidth(),
       (root.winfo_rootx(), root.winfo_rooty()))
    root.after(300, step4)


def step4():
    snap(root, "flow_2_reading.png", pad=14, step=2)
    app.open_shelf()
    root.after(800, step5)


def step5():
    ck("阅读中也能再开书架", app._shelf_win is not None and app.stage == "reading")
    snap(app._shelf_win.win, "flow_3_shelf_again.png", step=3)
    app._close_shelf()
    root.after(400, step6)


def step6():
    ck("关掉书架仍在阅读态", app.stage == "reading" and app.book is not None)
    ck("阅读窗仍可见", root.winfo_viewable() == 1)
    print("")
    print("失败 %d 项" % len(FAIL) if FAIL else "全部通过")
    root.after(200, app.quit)


root.after(1300, step1)
root.mainloop()

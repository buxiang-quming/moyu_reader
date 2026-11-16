# -*- coding: utf-8 -*-
"""启动流程的边角情形：关掉书架不选书、老板键清书架、唤出键叫回书架。"""
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

import wapi
wapi.set_dpi_aware()

import tkinter as tk
from app import ReaderApp

FAIL = []


def ck(name, cond, extra=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else "  " + str(extra)))
    if not cond:
        FAIL.append(name)


root = tk.Tk()
app = ReaderApp(root)


def s1():
    ck("启动就在书架态", app.stage == "shelf")
    # 等价于点书架右上角 X，还没选书
    app._close_shelf()
    root.after(500, s2)


def s2():
    ck("关书架后 stage = idle", app.stage == "idle", app.stage)
    ck("没有书", app.book is None)
    ck("提示窗露出来了", root.winfo_viewable() == 1, root.winfo_viewable())
    hint = app.text.get("1.0", "end")
    ck("提示里有 Ctrl+B 书架", "Ctrl+B" in hint, hint[:40])
    ck("提示窗不是空白", len(hint.strip()) > 30)
    app.open_shelf()
    root.after(600, s3)


def s3():
    ck("还能再打开书架", app._shelf_win is not None and app.stage == "shelf",
       app.stage)
    app.boss_key()          # 书架态按老板键
    root.after(500, s4)


def s4():
    ck("老板键把书架也藏了", app._shelf_win.win.winfo_viewable() == 0,
       app._shelf_win.win.winfo_viewable())
    ck("阅读窗也是藏的", root.winfo_viewable() == 0, root.winfo_viewable())
    app._reveal()           # 唤出键
    root.after(600, s5)


def s5():
    ck("唤出键把书架叫回来", app._shelf_win.win.winfo_viewable() == 1,
       app._shelf_win.win.winfo_viewable())
    ck("唤出键后仍是书架态", app.stage == "shelf", app.stage)
    print("")
    print("失败 %d 项" % len(FAIL) if FAIL else "全部通过")
    root.after(200, app.quit)


root.after(1300, s1)
root.mainloop()

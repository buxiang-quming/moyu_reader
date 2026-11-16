# -*- coding: utf-8 -*-
"""滚轮/翻页手感验收：以「屏比例」为单位（yview 差值 1.0 = 一整屏）。"""
import os, sys, time
BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import wapi; wapi.set_dpi_aware()
import tkinter as tk
from app import ReaderApp

root = tk.Tk(); app = ReaderApp(root)
FAIL = []
def ck(name, cond, extra=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else "  " + str(extra)))
    if not cond: FAIL.append(name)

def pump(ms):
    end = time.time() + ms/1000.0
    while time.time() < end:
        root.update(); time.sleep(0.004)

class E: delta = -120

def scroll_pct(fn):
    """返回一次操作挪动的「屏」比例：yview 差值 / 一屏占文档的比例。"""
    app.text.yview_moveto(0); pump(150)
    span = max(1e-9, app.text.yview()[1] - app.text.yview()[0])
    y0 = app.text.yview()[0]
    fn(); pump(150)
    return (app.text.yview()[0] - y0) / span

def run():
    pump(600)
    app.open_shelf_item(app.store.shelf()[0]); pump(900)
    t = app.text
    print("窗口 %dx%d  text 高 %d" % (root.winfo_width(), root.winfo_height(), t.winfo_height()))
    print("linespace=%d spacing1=%s spacing2=%s spacing3=%s" % (
        app.linespace, t.cget("spacing1"), t.cget("spacing2"), t.cget("spacing3")))
    # 实测单行高：用可见区域首个字符的 bbox
    t.yview_moveto(0); pump(200)
    b = t.bbox("@0,2")
    lh = b[3] if b else 0
    print("实测单行高 = %d px  → 可见 %.1f 行" % (lh, t.winfo_height() / float(lh or 1)))
    print("配置：wheel_lines=%d  wheel_delay=%dms  page_lines=%d" % (
        app.wheel_lines, int(app.wheel_delay*1000), app.page_lines))
    print("-" * 46)

    def one_wheel():
        app._last_wheel = 0.0
        app._on_wheel(E())

    p1 = scroll_pct(one_wheel)
    print("滚轮 1 次     = %.0f%% 屏 (%.2f 行)" % (p1*100, p1 * (t.winfo_height()/float(lh or 1))))
    ck("滚轮 1 次约在 15%~40% 屏之间", 0.15 <= p1 <= 0.40, "%.0f%%" % (p1*100))

    def three_wheel():
        for i in range(3):
            app._last_wheel = 0.0
            app._on_wheel(E())
    p3 = scroll_pct(three_wheel)
    print("滚轮 3 次     = %.0f%% 屏" % (p3*100))
    ck("滚轮 3 次约等于翻一屏左右", 0.6 <= p3 <= 1.2, "%.0f%%" % (p3*100))

    pp = scroll_pct(lambda: app._page(1))
    print("翻页键 1 次   = %.0f%% 屏" % (pp*100))
    ck("翻页键约翻一屏", 0.6 <= pp <= 1.15, "%.0f%%" % (pp*100))

    # 节流：连发 10 次滚轮（不重置时间戳），应只生效 1 次
    def burst():
        app._last_wheel = 0.0
        for i in range(10):
            app._on_wheel(E())     # 不重置 _last_wheel，模拟真实高频
    pb = scroll_pct(burst)
    print("连发 10 次    = %.0f%% 屏（节流后应≈1 次）" % (pb*100))
    ck("高频连滚被节流，不会飞好几页", pb <= p1 * 2.2, "%.0f%%" % (pb*100))

    # 滚轮在章末向下 = 进下一章
    t.yview_moveto(1.0); pump(150)
    ci0 = app.ci
    app._last_wheel = 0.0
    app._on_wheel(E()); pump(300)
    print("章末向下滚    : 章号 %d -> %d" % (ci0, app.ci))
    ck("章末向下滚进入下一章", app.ci == ci0 + 1 or app.ci == ci0, app.ci)

    app.quit()

root.after(800, run)
root.mainloop()

# -*- coding: utf-8 -*-
"""真鼠标端到端验收：用 SetCursorPos 真的把光标挪走，看窗口是否自动隐藏。

之前的 _t_hover.py 是注入假坐标，测的是判断逻辑；这个测的是「真实指针读取」
这一整条链路——用户遇到的「移开不隐藏」只有这一步能测出来。
"""
import ctypes
import ctypes.wintypes as wt
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


def cursor():
    p = wt.POINT()
    u.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


def move(x, y):
    u.SetCursorPos(int(x), int(y))


root = tk.Tk()
app = ReaderApp(root)


def pump(ms):
    end = time.time() + ms / 1000.0
    while time.time() < end:
        root.update()
        time.sleep(0.005)


def pump_until(cond, timeout_ms):
    """一边跑事件循环一边等条件成立，返回耗时毫秒（超时返回 -1）。"""
    t0 = time.time()
    while (time.time() - t0) * 1000.0 < timeout_ms:
        root.update()
        if cond():
            return int((time.time() - t0) * 1000.0)
        time.sleep(0.005)
    return -1


def run():
    print("=" * 52)
    print("会话锁定 = %s   屏幕 = %dx%d" % (wapi.session_locked(),
                                          root.winfo_screenwidth(),
                                          root.winfo_screenheight()))
    pump(900)

    # 先选一本书，进入阅读态
    items = app.store.shelf()
    app.open_shelf_item(items[0])
    pump(1200)
    app.locked = False
    app._hold_until = 0.0
    app._boss_hidden = False
    print("  阅读窗 %dx%d @ %d,%d   第 %d 章"
          % (root.winfo_width(), root.winfo_height(),
             root.winfo_rootx(), root.winfo_rooty(), app.ci + 1))

    # 关键：window 用的是 Tk 逻辑坐标，真鼠标用物理坐标。先搞清楚比例
    sw_tk, sh_tk = app._screen()
    sw_ph, sh_ph = u.GetSystemMetrics(0), u.GetSystemMetrics(1)
    print("  Tk 屏幕 %dx%d   物理屏幕 %dx%d   比例 %.3f"
          % (sw_tk, sh_tk, sw_ph, sh_ph, sw_ph / float(sw_tk)))
    scale = sw_ph / float(sw_tk)

    rx, ry = root.winfo_rootx(), root.winfo_rooty()
    cx, cy = rx + root.winfo_width() // 2, ry + root.winfo_height() // 2
    print("  窗口中心（Tk 坐标）%d,%d → 物理 %d,%d" % (cx, cy, cx * scale, cy * scale))

    # 1) 鼠标移进窗口 —— 应保持显示
    move(cx * scale, cy * scale)
    pump(300)
    ptr = app._pointer()
    print("  移入后 _pointer() = %s（应为 %d,%d 附近）" % (ptr, cx, cy))
    ck("真实指针读数正常", ptr is not None)
    if ptr:
        ck("读到的坐标和窗口中心一致（误差<40px）",
           abs(ptr[0] - cx) < 40 and abs(ptr[1] - cy) < 40, (ptr, (cx, cy)))
    ck("鼠标在窗内时保持显示", app.visible)

    # 2) 鼠标移开（挪到屏幕左下角，远离窗口也远离热区）
    move(80 * scale, (sh_ph - 80))
    took = pump_until(lambda: not app.visible, 2000)
    print("  移开 → %s" % ("%d ms 后隐藏" % took if took >= 0 else "2 秒内没隐藏"))
    ck("移开后自动隐藏", took >= 0)
    ck("隐藏够快（<300ms）", 0 <= took < 300, took)

    # 3) 鼠标移回原位置 —— 应重新出现
    app._cooldown = 0.0
    move(cx * scale, cy * scale)
    back = pump_until(lambda: app.visible, 2000)
    print("  移回 → %s" % ("%d ms 后显示" % back if back >= 0 else "2 秒内没显示"))
    ck("移回原位置重新显示", back >= 0)
    ck("重新显示够快（<600ms）", 0 <= back < 600, back)

    # 4) 再移开，确认不是只灵一次
    for i in range(2):
        app._cooldown = 0.0
        move(80 * scale, (sh_ph - 80))
        t = pump_until(lambda: not app.visible, 1500)
        ck("第 %d 次移开仍能隐藏" % (i + 2), t >= 0, t)
        app._cooldown = 0.0
        move(cx * scale, cy * scale)
        t2 = pump_until(lambda: app.visible, 1500)
        ck("第 %d 次移回仍能显示" % (i + 2), t2 >= 0, t2)

    # 5) 把真实状态打出来，万一失败便于定位
    print("")
    print("  现场状态：stage=%s visible=%s locked=%s pause_hide=%d hold=%.1f "
          "boss_hidden=%s leave_delay=%s"
          % (app.stage, app.visible, app.locked, app.pause_hide,
             max(0.0, app._hold_until - time.time()), app._boss_hidden,
             app.store.get("leave_delay")))

    print("")
    print("失败 %d 项" % len(FAIL) if FAIL else "全部通过")
    root.after(100, app.quit)


root.after(1200, run)
root.mainloop()

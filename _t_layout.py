# -*- coding: utf-8 -*-
"""界面布局静态验收：不截图，直接量控件几何。

会话锁屏时 GDI 抓屏只能拿到全黑，因此改用「量」的方式：
  1. 已显示控件必须有正尺寸（没被压成 0）
  2. 文字不能被裁（实际宽度 < 需要的宽度 → 说明被截断）
  3. 同一父容器里用 pack/grid 摆放的兄弟控件不允许重叠
  4. 控件不能跑到窗口外面
覆盖：书架窗口、设置窗口三个页签、阅读窗正文窗。
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

import time

FAIL = []


def ck(name, cond, extra=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else "  " + str(extra)))
    if not cond:
        FAIL.append(name)


def pump(ms):
    end = time.time() + ms / 1000.0
    while time.time() < end:
        try:
            app.root.update()
        except Exception:
            break
        time.sleep(0.005)


def children(w):
    try:
        return list(w.winfo_children())
    except Exception:
        return []


def manager(w):
    try:
        return w.winfo_manager()
    except Exception:
        return ""


def text_of(w):
    try:
        return str(w.cget("text"))
    except Exception:
        return ""


def scan(win, tag):
    """扫描一个窗口，返回 (问题列表, 控件数)。

    画布里的内容（设置页是装进 Canvas 的，可滚动）允许超出可视区，
    因此 in_canvas 为真时跳过「出界」判定。
    """
    problems = []
    n = 0
    stack = [(win, False)]
    while stack:
        p, in_canvas = stack.pop()
        # 画布的直系内容可滚动，允许超出可视区
        child_canvas = in_canvas or p.winfo_class() == "Canvas"
        kids = children(p)
        for k in kids:
            stack.append((k, child_canvas))
        boxes = []
        for c in kids:
            try:
                if not c.winfo_ismapped():
                    continue
            except Exception:
                continue
            n += 1
            w, h = c.winfo_width(), c.winfo_height()
            cls = c.winfo_class()
            t = text_of(c).replace("\n", " / ")[:18]

            # 1) 尺寸（1~2px 的纯分隔线、竖线是刻意的，放过）
            thin = (w <= 2 or h <= 2) and not t.strip() and not children(c)
            if (w <= 1 or h <= 1) and not thin:
                problems.append("%s 尺寸为 %dx%d [%s] 「%s」" % (cls, w, h, tag, t))
                continue

            # 2) 文字截断：Label/Button 没有 wraplength 时，实际宽度应 >= 需要宽度
            if cls in ("Label", "Button", "TButton", "Checkbutton", "Radiobutton"):
                try:
                    wrap = int(c.cget("wraplength") or 0)
                except Exception:
                    wrap = 0
                if wrap <= 1 and t.strip():
                    need = c.winfo_reqwidth()
                    if need > w + 2:
                        problems.append("%s 文字被裁 需要%d 实际%d [%s] 「%s」"
                                        % (cls, need, w, tag, t))

            # 3) 位置：不能出窗口（画布内容除外）
            rx = ry = 0
            try:
                rx = c.winfo_rootx() - win.winfo_rootx()
                ry = c.winfo_rooty() - win.winfo_rooty()
                if not child_canvas:
                    if rx + w > win.winfo_width() + 2 or ry + h > win.winfo_height() + 2:
                        problems.append("%s 超出窗口 [%s] 右%d 下%d 窗口%d x %d"
                                        % (cls, tag, rx + w, ry + h,
                                           win.winfo_width(), win.winfo_height()))
                    if rx < -2 or ry < -2:
                        problems.append("%s 跑到窗口左上方 [%s] %d,%d" % (cls, tag, rx, ry))
            except Exception:
                pass

            # 4) pack/grid 兄弟重叠
            m = manager(c)
            if m in ("pack", "grid"):
                boxes.append((m, c, rx, ry, w, h, cls, t))

        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                a, b = boxes[i], boxes[j]
                if a[0] != b[0]:
                    continue          # 不同布局器不管
                ax, ay, aw, ah = a[2], a[3], a[4], a[5]
                bx, by, bw, bh = b[2], b[3], b[4], b[5]
                ox = min(ax + aw, bx + bw) - max(ax, bx)
                oy = min(ay + ah, by + bh) - max(ay, by)
                if ox > 3 and oy > 3:
                    problems.append("%s「%s」与 %s「%s」重叠 %dx%d [%s]"
                                    % (a[6], a[7], b[6], b[7], ox, oy, tag))
    return problems, n


def report(tag, win):
    probs, n = scan(win, tag)
    print("  · %s：%d 个控件" % (tag, n))
    ck("%s 控件都已显示且尺寸正常、无重叠、文字未被裁" % tag, not probs,
       "\n      " + "\n      ".join(probs[:12]))
    return probs


root = tk.Tk()
app = ReaderApp(root)


def run():
    print("=" * 52)
    print("一、书架窗口")
    ck("启动后处于书架态", app.stage == "shelf", app.stage)
    sh = app._shelf_win
    ck("书架窗口存在", sh is not None)
    if sh is not None:
        w = sh.win
        pump(400)
        print("  书架 %dx%d @ %d,%d" % (w.winfo_width(), w.winfo_height(),
                                        w.winfo_rootx(), w.winfo_rooty()))
        ck("书架尺寸够放卡片", w.winfo_width() >= 900 and w.winfo_height() >= 560,
           (w.winfo_width(), w.winfo_height()))
        ck("书架完整在屏幕内",
           w.winfo_rootx() >= 0 and w.winfo_rooty() >= 0 and
           w.winfo_rootx() + w.winfo_width() <= w.winfo_screenwidth() and
           w.winfo_rooty() + w.winfo_height() <= w.winfo_screenheight(),
           (w.winfo_rootx(), w.winfo_rooty()))
        ck("卡片数与书数一致", len(sh._cards) == len(app.store.shelf()) + 1,
           len(sh._cards))
        report("书架", w)

    print("")
    print("二、阅读窗")
    app.open_shelf_item(app.store.shelf()[0])
    pump(900)
    app.locked = True
    ck("已进入阅读态", app.stage == "reading", app.stage)
    ck("书籍已加载", app.book is not None)
    rw, rh = root.winfo_width(), root.winfo_height()
    print("  阅读窗 %dx%d @ %d,%d" % (rw, rh, root.winfo_rootx(), root.winfo_rooty()))
    ck("阅读窗尺寸符合设置",
       rw == int(app.store.get("width")) and rh == int(app.store.get("height")), (rw, rh))
    body = app.text.get("1.0", "end").strip()
    ck("正文有内容", len(body) > 50, len(body))
    ck("正文行未被压缩（首行不空）", body.split("\n")[0].strip() != "")
    # 正文整体宽度是否超出可视宽度（会导致横向截断）
    try:
        txt_w = app.text.winfo_width()
        need = app.text.winfo_reqwidth()
        ck("正文可视宽度足够", txt_w >= 200, txt_w)
        print("  · 正文档位 视宽 %d / 需要 %d" % (txt_w, need))
    except Exception as e:
        ck("正文宽度可读", False, e)
    report("阅读窗", root)

    print("")
    print("三、设置窗口")
    app.open_settings()
    pump(700)
    st = app._settings_win
    ck("设置窗口已打开", st is not None)
    if st is not None:
        sw = st.win
        print("  设置 %dx%d @ %d,%d" % (sw.winfo_width(), sw.winfo_height(),
                                        sw.winfo_rootx(), sw.winfo_rooty()))
        ck("设置窗口完整在屏幕内",
           sw.winfo_rootx() >= 0 and sw.winfo_rooty() >= 0 and
           sw.winfo_rootx() + sw.winfo_width() <= sw.winfo_screenwidth() and
           sw.winfo_rooty() + sw.winfo_height() <= sw.winfo_screenheight(),
           (sw.winfo_rootx(), sw.winfo_rooty()))
        report("设置-默认页签", sw)
        # 切三个页签各扫一遍
        try:
            for key, nm in (("look", "外观"), ("func", "功能"), ("misc", "其他")):
                st._switch(key)
                pump(350)
                report("设置-%s" % nm, sw)
        except Exception as e:
            ck("设置页签可切换", False, e)

    print("")
    print("四、收尾")
    try:
        app._close_settings()
        pump(200)
        ck("设置可关闭", app._settings_win is None)
    except Exception as e:
        ck("设置可关闭", False, e)
    ck("会话状态已记录（锁屏=%s）" % wapi.session_locked(), True)
    print("")
    print("失败 %d 项" % len(FAIL) if FAIL else "全部通过")
    root.after(100, app.quit)


root.after(1200, run)


def _watchdog(depth=[0]):
    """卡死兜底：30 秒还没跑完就直接收场，别把 CI 挂住。"""
    depth[0] += 1
    if depth[0] > 300:
        print("  !! 超时中断")
        try:
            root.quit()
        except Exception:
            pass
        return
    try:
        root.after(100, _watchdog)
    except Exception:
        pass


_watchdog()
root.mainloop()

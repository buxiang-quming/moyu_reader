# -*- coding: utf-8 -*-
"""真实启动验收：用 pythonw 起真程序，再用 Win32 枚举窗口核对。

不截图、不动鼠标（锁屏会话下这两样都不可靠），只看真实进程的窗口状态：
  1. 启动进程后，书架窗口真实存在、可见、尺寸位置合理
  2. 阅读窗此时不可见（屏幕上不该有文字条）
  3. 再启动一次：第二个进程应快速退出，第一个进程把书架唤到前台
  4. 收尾杀进程，不留残余
"""
import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)
PYW = r"C:\Users\Administrator\AppData\Local\Programs\Python\Python37\pythonw.exe"

user32 = ctypes.windll.user32

# 关键：本测量进程必须声明 DPI 感知，否则 GetWindowRect 返回的是被虚拟化
# 到 1536x864 逻辑坐标系的尺寸（会看到 1038x707 变成 830x566，白判一次失败）。
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass

FAIL = []


def ck(name, cond, extra=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else "  " + str(extra)))
    if not cond:
        FAIL.append(name)


def windows_of(pid):
    """枚举某进程的所有顶层窗口。"""
    out = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(hwnd, _):
        p = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid:
            n = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(n + 2)
            user32.GetWindowTextW(hwnd, buf, n + 2)
            r = wt.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            out.append({
                "hwnd": hwnd,
                "title": buf.value,
                "visible": bool(user32.IsWindowVisible(hwnd)),
                "rect": (r.left, r.top, r.right, r.bottom),
                "w": r.right - r.left,
                "h": r.bottom - r.top,
            })
        return True

    user32.EnumWindows(cb, 0)
    return out


def find(wins, title):
    for w in wins:
        if w["title"] == title:
            return w
    return None


def kill(tree):
    subprocess.call(["taskkill", "/F", "/T", "/PID", str(tree.pid)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    # 先清掉可能残留的实例
    subprocess.call(["taskkill", "/F", "/IM", "pythonw.exe"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.5)

    print("=" * 52)
    print("一、首次启动")
    env = dict(os.environ)
    env.pop("MOYU_DEBUG", None)
    p1 = subprocess.Popen([PYW, "main.py"], cwd=BASE, env=env)
    time.sleep(4.5)
    ck("进程还活着（没崩）", p1.poll() is None, p1.poll())
    wins = windows_of(p1.pid)
    print("  该进程窗口 %d 个：%s" % (len(wins),
                                     [(w["title"], w["w"], w["h"], w["visible"]) for w in wins]))

    shelf = find(wins, "我的书架")
    ck("书架窗口已创建", shelf is not None)
    if shelf:
        ck("书架窗口可见", shelf["visible"])
        ck("书架尺寸合理（>=900x560）", shelf["w"] >= 900 and shelf["h"] >= 560,
           (shelf["w"], shelf["h"]))
        l, t, r, b = shelf["rect"]
        ck("书架在屏幕内", l >= -8 and t >= -8 and r <= 1930 and b <= 1090, shelf["rect"])

    titled = [w for w in wins if w["visible"] and w["title"]]
    ck("可见窗口只有书架（阅读窗不该露出来）",
       len(titled) == 1, [(w["title"]) for w in titled])

    print("")
    print("二、再次启动（双击第二次）")
    t0 = time.time()
    p2 = subprocess.Popen([PYW, "main.py"], cwd=BASE, env=env)
    code = None
    for _ in range(80):
        code = p2.poll()
        if code is not None:
            break
        time.sleep(0.05)
    dur = time.time() - t0
    print("  第二个进程 %.2fs 退出，码 %s" % (dur, code))
    ck("第二个进程自己退出（单实例生效）", code is not None, code)
    ck("退得够快（<3s）", code is not None and dur < 3.0, dur)
    ck("第一个进程仍在跑", p1.poll() is None)

    time.sleep(1.2)
    wins2 = windows_of(p1.pid)
    shelf2 = find(wins2, "我的书架")
    ck("书架还在", shelf2 is not None and shelf2["visible"])
    ck("唤出后没有变成两个书架",
       sum(1 for w in wins2 if w["title"] == "我的书架") == 1)

    print("")
    print("三、进程干净退出")
    kill(p1)
    time.sleep(1.0)
    ck("进程已结束", p1.poll() is not None, p1.poll())
    left = [w for w in windows_of(p1.pid) if w["visible"]]
    ck("没有留下可见窗口", not left, left)

    print("")
    print("失败 %d 项" % len(FAIL) if FAIL else "全部通过")


main()

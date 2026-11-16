# -*- coding: utf-8 -*-
"""验证真实入口：双击 启动.bat / start.bat 能否正确起程序并停在书架。

关键：整个过程放在同一个进程里做，避免「后台任务结束 → 子进程被回收」的假失败。
"""
import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import time

BASE = os.path.dirname(os.path.abspath(__file__))
u = ctypes.windll.user32
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    u.SetProcessDPIAware()

FAIL = []


def ck(name, cond, extra=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else "  " + str(extra)))
    if not cond:
        FAIL.append(name)


def pyw_pids():
    raw = subprocess.check_output(
        ["tasklist", "/FI", "IMAGENAME eq pythonw.exe", "/FO", "CSV", "/NH"],
        stderr=subprocess.DEVNULL)
    # tasklist 在中文系统上是 GBK 输出，不能用 utf-8 解
    text = raw.decode("gbk", "replace")
    pids = []
    for line in text.strip().splitlines():
        parts = line.replace('"', "").split(",")
        if len(parts) >= 2 and parts[1].strip().isdigit():
            pids.append(int(parts[1]))
    return pids


def windows_of(pid):
    out = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(h, _):
        p = wt.DWORD()
        u.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid:
            n = u.GetWindowTextLengthW(h)
            b = ctypes.create_unicode_buffer(n + 2)
            u.GetWindowTextW(h, b, n + 2)
            r = wt.RECT()
            u.GetWindowRect(h, ctypes.byref(r))
            out.append({"title": b.value,
                        "visible": bool(u.IsWindowVisible(h)),
                        "w": r.right - r.left, "h": r.bottom - r.top,
                        "x": r.left, "y": r.top})
        return True

    u.EnumWindows(cb, 0)
    return out


def cleanup():
    subprocess.call(["taskkill", "/F", "/IM", "pythonw.exe"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.8)


def try_bat(name):
    print("=" * 52)
    print("测试入口：%s" % name)
    cleanup()
    before = set(pyw_pids())
    # stdout 必须给 DEVNULL：bat 里用 start 起的 pythonw 会继承这个句柄，
    # 若用 PIPE，run() 会一直等管道关闭而挂死。
    r = subprocess.run(["cmd", "/c", name], cwd=BASE,
                       stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("  cmd 退出码 %d" % r.returncode)
    time.sleep(5)
    after = set(pyw_pids()) - before
    ck("启动出了 pythonw 进程", len(after) == 1, after)
    if not after:
        return
    pid = after.pop()
    wins = windows_of(pid)
    titles = [(w["title"], w["w"], w["h"], w["visible"]) for w in wins if w["title"]]
    print("  窗口：%s" % (titles,))
    shelf = [w for w in wins if w["title"] == "我的书架"]
    ck("书架窗口出现", bool(shelf))
    if shelf:
        s = shelf[0]
        ck("书架可见", s["visible"])
        ck("书架尺寸正常（约 1038x707）", 900 <= s["w"] <= 1400 and 560 <= s["h"] <= 900,
           (s["w"], s["h"]))
        ck("书架在屏幕内", s["x"] >= -8 and s["y"] >= -8 and
           s["x"] + s["w"] <= 1930 and s["y"] + s["h"] <= 1090, (s["x"], s["y"]))
    reading = [w for w in wins if w["title"] == "tk"]
    ck("阅读窗处于隐藏", all(not w["visible"] for w in reading), reading)
    ck("屏幕上只有书架一个可见窗口",
       sum(1 for w in wins if w["visible"] and w["title"]) == 1,
       [w["title"] for w in wins if w["visible"] and w["title"]])


for bat in ("启动.bat", "start.bat"):
    try_bat(bat)

cleanup()
print("")
print("失败 %d 项" % len(FAIL) if FAIL else "全部通过")

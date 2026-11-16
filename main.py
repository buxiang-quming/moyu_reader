# -*- coding: utf-8 -*-
"""入口。

用 pythonw.exe 启动时没有控制台窗口，异常会写到 data/error.log。
"""
import os
import sys
import traceback

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

DEBUG = os.environ.get("MOYU_DEBUG") == "1"


def _log(msg):
    if not DEBUG:
        return
    try:
        d = os.path.join(BASE, "data")
        if not os.path.isdir(d):
            os.makedirs(d)
        with open(os.path.join(d, "debug.log"), "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


def main():
    _log("boot")

    import wapi
    # 句柄要留到进程结束，否则互斥量会被提前释放
    mutex, exists = wapi.create_mutex()
    if exists:
        # 已经有实例在跑（多半是被老板键藏起来了，用户以为关掉了）。
        # 不静默退出：叫醒它，让窗口自己冒出来。
        _log("already running -> signal reveal")
        if wapi.signal_reveal():
            _log("revealed existing instance")
            return
        # 旧版本实例没有事件通道，至少给句人话
        _log("reveal failed -> message box")
        wapi.message_box(
            "阅读器已经在运行了，只是被隐藏着。\n\n"
            "按 Ctrl+Alt+Z 唤出窗口，或把鼠标移到屏幕右上角。\n"
            "想彻底退出：唤出后右键 → 退出。",
            "已在运行")
        return

    try:
        wapi.set_dpi_aware()
        _log("dpi ok")

        import tkinter as tk
        from app import ReaderApp

        root = tk.Tk()
        _log("tk ok")
        app = ReaderApp(root)
        _log("app ok")
        root.mainloop()
        _log("loop exited")
    except Exception:
        tb = traceback.format_exc()
        try:
            d = os.path.join(BASE, "data")
            if not os.path.isdir(d):
                os.makedirs(d)
            with open(os.path.join(d, "error.log"), "a", encoding="utf-8") as f:
                f.write(tb + "\n")
        except Exception:
            pass
        try:
            import tkinter as tk
            from tkinter import messagebox
            r = tk.Tk()
            r.withdraw()
            messagebox.showerror("启动失败", tb[-1200:])
            r.destroy()
        except Exception:
            pass

    # 兜底：万一还有非守护线程没退，别留个僵尸进程占着单实例锁
    try:
        sys.stdout.flush()
    except Exception:
        pass
    os._exit(0)


if __name__ == "__main__":
    main()

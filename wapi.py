# -*- coding: utf-8 -*-
"""Win32 轻封装：DPI、鼠标位置、全局热键轮询、前台进程判断。

全部用 ctypes 调 user32，不依赖 pywin32，保证绿色免安装。
"""
import ctypes
import os

user32 = ctypes.windll.user32


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def set_dpi_aware():
    """必须在创建 Tk 之前调用，否则高分屏下窗口会糊。"""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        return True
    except Exception:
        pass
    try:
        user32.SetProcessDPIAware()
        return True
    except Exception:
        return False


def screen_size():
    return (user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))


def get_cursor_pos():
    pt = POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


DESKTOP_READOBJECTS = 0x0001


def session_locked():
    """锁屏 / 远程断开：没有输入桌面，也没有前台窗口。

    这时 GetCursorPos 会老实地返回 (0,0)，看起来像个合法坐标，
    照它判断显隐会把窗口一直按在「移出」状态。
    """
    try:
        if user32.GetForegroundWindow():
            return False
        h = user32.OpenInputDesktop(0, 0, DESKTOP_READOBJECTS)
        if not h:
            return True
        user32.CloseDesktop(h)
        return False
    except Exception:
        return False


def key_down(vk):
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


VK_MOD = {
    "ctrl": 0x11, "control": 0x11,
    "alt": 0x12, "shift": 0x10,
    "win": 0x5B,
}
VK_SPECIAL = {
    "space": 0x20, "esc": 0x1B, "tab": 0x09,
    "`": 0xC0, "-": 0xBD, "=": 0xBB,
    "[": 0xDB, "]": 0xDD,
}


def parse_combo(combo):
    """'ctrl+alt+q' -> [0x11, 0x12, 0x51]"""
    keys = []
    for part in combo.lower().split("+"):
        part = part.strip()
        if not part:
            continue
        if part in VK_MOD:
            keys.append(VK_MOD[part])
        elif part in VK_SPECIAL:
            keys.append(VK_SPECIAL[part])
        elif len(part) == 1 and part.isalpha():
            keys.append(ord(part.upper()))
        elif len(part) == 1 and part.isdigit():
            keys.append(ord(part))
        elif part.startswith("f") and part[1:].isdigit():
            n = int(part[1:])
            if 1 <= n <= 24:
                keys.append(0x70 + n - 1)
    return keys


class Hotkeys(object):
    """轮询式全局热键：不注册系统热键，所以不占键位、不需要管理员权限。"""

    def __init__(self):
        self._bindings = []     # (name, vk_list, callback)
        self._latched = set()

    def bind(self, name, combo, callback):
        vks = parse_combo(combo)
        if vks:
            self._bindings.append((name, vks, callback))
            return True
        return False

    def clear(self):
        self._bindings = []
        self._latched = set()

    def poll(self):
        for name, vks, cb in self._bindings:
            if all(key_down(v) for v in vks):
                if name not in self._latched:
                    self._latched.add(name)
                    try:
                        cb()
                    except Exception:
                        pass
            else:
                self._latched.discard(name)


def foreground_is_self():
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return False
    pid = ctypes.c_ulong(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value == os.getpid()


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


def foreground_is_fullscreen():
    """前台窗口是否基本占满屏幕（全屏浏览器、PPT 放映、全屏视频）。"""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return False
    if foreground_is_self():
        return False
    r = RECT()
    try:
        if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
            return False
    except Exception:
        return False
    sw, sh = screen_size()
    w = r.right - r.left
    h = r.bottom - r.top
    if w <= 0 or h <= 0:
        return False
    return w >= sw * 0.92 and h >= sh * 0.92 and r.left <= 2 and r.top <= 2


def mix_color(c1, c2, t):
    """把 c1 向 c2 混合 t（0~1），返回 #RRGGBB。t 越大越接近 c2。"""
    try:
        a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
        b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    except (ValueError, IndexError):
        return c1
    t = max(0.0, min(1.0, float(t)))
    out = [int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3)]
    return "#%02X%02X%02X" % tuple(out)


# ---------------------------------------------------------------- 点击穿透
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080


def get_hwnd(tk_root):
    """拿到 Tk 顶层窗口的 HWND。"""
    try:
        return int(tk_root.frame(), 16)
    except Exception:
        pass
    try:
        return user32.GetParent(tk_root.winfo_id())
    except Exception:
        return 0


def set_click_through(hwnd, enable):
    """开启后鼠标事件穿透到下层窗口，窗口仍然可见。"""
    if not hwnd:
        return False
    try:
        cur = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        if enable:
            new = cur | WS_EX_LAYERED | WS_EX_TRANSPARENT
        else:
            new = cur & (~WS_EX_TRANSPARENT)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new)
        return True
    except Exception:
        return False


def hide_from_taskbar(hwnd):
    """标记为工具窗口，不在任务栏/Alt-Tab 里出现。"""
    if not hwnd:
        return False
    try:
        cur = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, cur | WS_EX_TOOLWINDOW)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- 单实例与唤醒
# 第二次双击启动时，用命名事件通知已在跑的那个实例把窗口叫出来，
# 而不是静默退出——否则用户会觉得「点了没反应」。

k32 = ctypes.WinDLL("kernel32", use_last_error=True)

MUTEX_NAME = "MOYU_READER_SINGLE_INSTANCE"
EVENT_NAME = "MOYU_READER_REVEAL"
EVENT_MODIFY_STATE = 0x0002

for _fn, _args, _res in (
        ("CreateMutexW", [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p], ctypes.c_void_p),
        ("CreateEventW", [ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                          ctypes.c_wchar_p], ctypes.c_void_p),
        ("OpenEventW", [ctypes.c_int, ctypes.c_int, ctypes.c_wchar_p], ctypes.c_void_p),
        ("SetEvent", [ctypes.c_void_p], ctypes.c_int),
        ("CloseHandle", [ctypes.c_void_p], ctypes.c_int),
        ("WaitForSingleObject", [ctypes.c_void_p, ctypes.c_uint], ctypes.c_uint)):
    try:
        _f = getattr(k32, _fn)
        _f.argtypes = _args
        _f.restype = _res
    except Exception:
        pass


def create_mutex(name=MUTEX_NAME):
    """返回 (句柄, 是否已有实例)。句柄必须留到进程结束，别让 GC 关掉。"""
    try:
        h = k32.CreateMutexW(None, 0, name)
        return h, (ctypes.get_last_error() == 183)   # ERROR_ALREADY_EXISTS
    except Exception:
        return 0, False


def create_reveal_event(name=EVENT_NAME):
    """自动重置事件：被 Wait 消费后自动清零。"""
    try:
        return k32.CreateEventW(None, 0, 0, name)
    except Exception:
        return 0


def signal_reveal(name=EVENT_NAME):
    """叫醒已运行的实例。没有实例（或旧版本）时返回 False。"""
    try:
        h = k32.OpenEventW(EVENT_MODIFY_STATE, 0, name)
        if not h:
            return False
        k32.SetEvent(h)
        k32.CloseHandle(h)
        return True
    except Exception:
        return False


def wait_reveal(handle, timeout=0):
    """非阻塞检查是否有人叫我们。"""
    if not handle:
        return False
    try:
        return k32.WaitForSingleObject(handle, timeout) == 0
    except Exception:
        return False


def message_box(text, title="摸鱼阅读器", flags=0x40):
    """不走 Tk 的原生提示框，Tk 起不来时也能用。"""
    try:
        user32.MessageBoxW(None, text, title, flags)
        return True
    except Exception:
        return False

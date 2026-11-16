# -*- coding: utf-8 -*-
"""主程序：透明置顶窗口 + 三态交互（书架 / 阅读 / 空提示）+ 设置/书架/目录。"""
import re
import time
import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, simpledialog

import core
import wapi
import webimport
import zhconv
import settings_ui
import bookshelf as shelf_mod

TRANSPARENT_KEY = "#010203"

EMPTY_HINT = (
    "书架已经关掉了，还没有打开书。\n"
    "\n"
    "Ctrl+B   打开书架，挑一本开始读\n"
    "Ctrl+O   导入本地书（txt / epub）\n"
    "Ctrl+U   导入网址\n"
    "\n"
    "读书时：鼠标移到屏幕右上角，正文就会出现；\n"
    "移开一会儿，它自己消失。\n"
    "Ctrl+,   设置（外观、翻页、快键）\n"
    "Ctrl+G   目录\n"
    "Ctrl+Alt+Q  一键清屏\n"
)


def to_tk_seq(combo):
    """'ctrl+alt+q' -> '<Control-Alt-q>'"""
    if not combo:
        return None
    mods = []
    key = ""
    for part in combo.split("+"):
        p = part.strip()
        low = p.lower()
        if low in ("ctrl", "control"):
            mods.append("Control")
        elif low == "alt":
            mods.append("Alt")
        elif low == "shift":
            mods.append("Shift")
        elif p:
            key = p
    if not key:
        return None
    kmap = {"up": "Up", "down": "Down", "left": "Left", "right": "Right",
            "space": "space", "enter": "Return", "esc": "Escape",
            "pageup": "Prior", "pagedown": "Next", "tab": "Tab",
            "home": "Home", "end": "End", "backspace": "BackSpace"}
    key = kmap.get(key.lower(), key)
    seq = "<" + "".join(m + "-" for m in mods) + key + ">"
    return seq


class ReaderApp(object):

    def __init__(self, root):
        self.root = root
        self.store = core.Store()

        self.book = None
        self.ci = 0
        # stage: shelf（启动先选书）/ reading（读书）/ idle（书架被关掉但没书）
        self.stage = "shelf"
        self.locked = False
        self.visible = False
        self.pause_hide = 0
        self.pos = [0, 0]
        self._hide_at = 0.0
        self._show_at = 0.0
        self._cooldown = 0.0
        self._grace = time.time() + 3.0
        # 刚选完书先按住一会儿，等鼠标进过一次再交还给悬停规则
        self._hold_until = 0.0
        self._drag = None
        self._last_wheel = 0.0
        self._body_cache = {}
        self._render_cache = {}
        self._loading = set()
        self._saved_key = None
        self._bound_seqs = []
        self._settings_win = None
        self._shelf_win = None
        self._tip_until = 0.0
        self._hwnd = 0
        self.click_through = False
        # 老板键清屏后，鼠标扫过原位置不许自动冒出来
        self._boss_hidden = False

        self.hotkeys = wapi.Hotkeys()

        self._load_settings()
        self._build_window()
        self._build_ui()
        self._bind_fixed()
        self.refresh_bindings()
        self.refresh_hotkeys()
        self.apply_settings(render=False)
        self._start_flow()
        self.root.after(60, self._tick)
        self.root.after(400, self._auto_page_loop)
        self.root.after(300, self._init_hwnd)
        # 供「再次双击启动」唤出用
        self._reveal_h = wapi.create_reveal_event()

    def _start_flow(self):
        """启动流程：先开书架，挑完书才进阅读态。

        阅读窗此时保持隐藏——不给「一打开就甩一屏正文在同事面前」的机会。
        """
        self.stage = "shelf"
        self._set_text(EMPTY_HINT)
        self._grace = time.time() + 1.0
        self.open_shelf()

    def _enter_reading(self):
        """选好书：收起书架，把阅读窗放出来。"""
        self.stage = "reading"
        self._grace = time.time() + 1.2
        self._hold_until = time.time() + 8.0
        self._hide_at = 0.0
        self._show_at = 0.0
        if self._shelf_win is not None:
            self._close_shelf()
        self.show()
        # 窗口这次真正映射了，重新取一次 HWND 把工具窗/穿透标记补上
        self.root.after(150, self._init_hwnd)

    def _dlg_parent(self):
        """对话框父窗口：书架在前台时用书架，否则用阅读窗。"""
        if self.stage == "shelf" and self._shelf_win is not None:
            try:
                return self._shelf_win.win
            except Exception:
                pass
        return self.root

    # ------------------------------------------------------------ 配置

    def _load_settings(self):
        s = self.store
        self.bg_mode = s.get("bg_mode")
        self.fg = s.get("fg")
        self.bg = s.get("bg")
        self.bg_alpha = float(s.get("bg_alpha"))
        self.font_size = int(s.get("font_size"))
        self.font_family = s.get("font_family")
        self.line_spacing = float(s.get("line_spacing"))
        self.para_spacing = int(s.get("para_spacing"))
        self.keep_format = bool(s.get("keep_format"))
        self.show_percent = bool(s.get("show_percent"))
        self.show_bar = bool(s.get("show_bar"))
        self.page_lines = int(s.get("page_lines"))
        self.zh = s.get("zh_convert")
        self.auto_page = int(s.get("auto_page"))
        self.continuous = bool(s.get("continuous"))
        self.mouse_page = bool(s.get("mouse_page"))
        self.click_pin = bool(s.get("click_pin"))
        self.window_movable = bool(s.get("window_movable"))
        self.wheel_delay = int(s.get("wheel_delay")) / 1000.0
        self.wheel_invert = bool(s.get("wheel_invert"))
        self.hide_keep_br = int(s.get("hide_keep_br"))
        self.hide_on_blur = bool(s.get("hide_on_blur"))

    def apply_settings(self, render=True):
        """设置改动后统一生效：主题、排版、尺寸、快捷键。"""
        old_w = self.root.winfo_width()
        old_h = self.root.winfo_height()
        top = self._top_index()
        self._load_settings()
        self._apply_theme()
        self._apply_alpha()
        self._apply_geometry(old_w, old_h)
        self.refresh_bindings()
        if render:
            self._render(top=top)
        else:
            self._update_progress()

    def _apply_geometry(self, old_w, old_h):
        w = int(self.store.get("width"))
        h = int(self.store.get("height"))
        if w == old_w and h == old_h:
            return
        sw, sh = self._screen()
        self.pos[0] = max(0, min(self.pos[0], sw - 120))
        self.pos[1] = max(0, min(self.pos[1], sh - 40))
        self.root.geometry("%dx%d+%d+%d" % (w, h, self.pos[0], self.pos[1]))

    def _init_hwnd(self):
        """窗口映射后拿 HWND，做工具窗口标记与穿透恢复。"""
        self._hwnd = wapi.get_hwnd(self.root)
        if self.store.get("hide_taskbar"):
            wapi.hide_from_taskbar(self._hwnd)
        self.click_through = bool(self.store.get("click_through"))
        if self.click_through:
            wapi.set_click_through(self._hwnd, True)

    def toggle_through(self, force=None):
        """鼠标点击穿透：窗口还看得见，但点击落到下层软件上。"""
        new = (not self.click_through) if force is None else bool(force)
        if new == self.click_through:
            return
        if not self._hwnd:
            self._hwnd = wapi.get_hwnd(self.root)
        ok = wapi.set_click_through(self._hwnd, new)
        if not ok:
            self.flash("这台机器不支持穿透切换")
            return
        self.click_through = new
        self.store.set("click_through", new)
        self.store.save()
        if new:
            self.flash("穿透开 · 鼠标可直接操作下层，%s 切回"
                       % str(self.store.get("through_key")).upper())
        else:
            self.flash("穿透关 · 窗口恢复接收点击")

    def refresh_hotkeys(self):
        self.hotkeys.clear()
        self.hotkeys.bind("boss", self.store.get("boss_key"), self.boss_key)
        self.hotkeys.bind("reveal", self.store.get("reveal_key"), self._reveal)
        self.hotkeys.bind("through", self.store.get("through_key"),
                          self.toggle_through)

    # ------------------------------------------------------------ 窗口

    def _screen(self):
        """Tk 坐标系的屏幕尺寸，必须和 winfo_pointerxy 配套使用。"""
        try:
            return self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        except Exception:
            return wapi.screen_size()

    def _pointer(self):
        """Tk 逻辑坐标下的鼠标位置（不能用 GetCursorPos，那是物理像素）。

        锁屏或远程断开会话时 Tk 会读出垃圾值、GetCursorPos 退回 (0,0)，
        这种时候返回 None——上层这一拍什么都不做，别乱藏乱显。
        """
        sw, sh = self._screen()
        try:
            x, y = self.root.winfo_pointerxy()
        except Exception:
            x, y = -1, -1
        if 0 <= x <= sw and 0 <= y <= sh:
            return x, y
        try:
            x, y = wapi.get_cursor_pos()
        except Exception:
            return None
        if 0 <= x <= sw and 0 <= y <= sh and not wapi.session_locked():
            return x, y
        return None

    def _bg_color(self):
        return TRANSPARENT_KEY if self.bg_mode == "transparent" else self.bg

    def _dim_color(self, t=0.45):
        """把文字色往背景色方向退，用于百分比、提示这类附属文字。"""
        base = "#FFFFFF" if self.bg_mode == "transparent" else self.bg
        return wapi.mix_color(self.fg, base, t)

    def _build_window(self):
        r = self.root
        r.withdraw()
        r.overrideredirect(True)
        try:
            r.attributes("-topmost", True)
        except Exception:
            pass

        w = int(self.store.get("width"))
        h = int(self.store.get("height"))
        sw, sh = self._screen()
        x = self.store.get("pos_x")
        y = self.store.get("pos_y")
        if x is None:
            x = sw - w - 60
        if y is None:
            y = int(sh * 0.22)
        x = max(0, min(int(x), sw - 120))
        y = max(0, min(int(y), sh - 50))
        self.pos = [x, y]
        r.geometry("%dx%d+%d+%d" % (w, h, x, y))
        r.configure(bg=self._bg_color())

    def _build_ui(self):
        bg = self._bg_color()

        self.canvas_bar = tk.Canvas(self.root, height=2, bg=bg, bd=0,
                                    highlightthickness=0)
        self.canvas_bar.pack(fill="x", side="top")
        self.bar = self.canvas_bar.create_rectangle(0, 0, 0, 2,
                                                    fill=self._dim_color(0.25),
                                                    outline="")

        self.text = tk.Text(
            self.root, wrap="char", bd=0, highlightthickness=0,
            bg=bg, fg=self.fg, insertbackground=self.fg,
            padx=14, pady=10, cursor="arrow", undo=False,
            font=(self.font_family, self.font_size),
            spacing1=0, spacing2=4, spacing3=6,
            selectbackground="#3A3A3A", selectforeground="#FFFFFF",
            state="disabled",
        )
        self.text.pack(fill="both", expand=True)

        self.pct = tk.Label(self.root, text="", bg=bg, fg=self._dim_color(0.45),
                            font=("Consolas", 8), anchor="e")
        self.lbl = tk.Label(self.root, text="", bg=bg, fg=self._dim_color(0.3),
                            font=("Microsoft YaHei", 8), anchor="e")

        self.canvas_bar.bind("<Configure>", lambda e: self._update_progress())

    def _apply_theme(self):
        bg = self._bg_color()
        self.root.configure(bg=bg)
        self.canvas_bar.configure(bg=bg)
        self.canvas_bar.itemconfigure(self.bar, fill=self._dim_color(0.25))

        fnt = tkfont.Font(family=self.font_family, size=self.font_size)
        self.linespace = fnt.metrics("linespace")
        gap = int(round(self.linespace * max(0.0, self.line_spacing - 1.0)))

        self.text.configure(
            bg=bg, fg=self.fg,
            font=(self.font_family, self.font_size),
            spacing2=max(0, gap),
            spacing3=max(0, self.para_spacing),
        )
        self.pct.configure(bg=bg, fg=self._dim_color(0.42))
        self.lbl.configure(bg=bg, fg=self._dim_color(0.28))

        if self.show_bar:
            self.canvas_bar.pack(fill="x", side="top", before=self.text)
            self.canvas_bar.configure(height=2)
        else:
            self.canvas_bar.configure(height=0)
            self.canvas_bar.pack_forget()

        self._place_pct()

    def _place_pct(self):
        """百分比角标的位置。钉住时即使没开「显示百分比」也要露出来，
        否则用户只看到「移开不消失」，却没有任何提示告诉他为什么。"""
        if self.show_percent or self.locked:
            try:
                self.pct.place(relx=1.0, rely=1.0, anchor="se", x=-8, y=-2)
                self.pct.lift()
            except Exception:
                pass
        else:
            try:
                self.pct.place_forget()
            except Exception:
                pass

    def _apply_alpha(self):
        r = self.root
        try:
            if self.bg_mode == "transparent":
                r.attributes("-transparentcolor", "")
                r.attributes("-alpha", 1.0)
                r.attributes("-transparentcolor", TRANSPARENT_KEY)
            else:
                r.attributes("-transparentcolor", "")
                r.attributes("-alpha", max(0.2, min(1.0, self.bg_alpha)))
        except Exception:
            pass

    def _wake_by_second_launch(self):
        """用户又点了一次「启动」：把窗口叫出来，别再静默装死。"""
        try:
            self._grace = time.time() + 6.0
            if not self.book:
                self._bring_shelf_front()
                return
            if not self.visible:
                self.show()
            self.flash("已在运行 · 已唤出窗口")
        except Exception:
            pass

    def _bring_shelf_front(self):
        """书架可能在后面、被清屏藏了、或已被销毁——都拉回前台。"""
        if self._shelf_win is not None:
            try:
                self._shelf_win.win.deiconify()
                self._shelf_win.win.lift()
                self._shelf_win.win.focus_force()
                self._shelf_win.refresh()
                return True
            except Exception:
                self._shelf_win = None
        self.open_shelf()
        return True

    def show(self):
        # 书架态阅读窗不该露头（书架就是当前界面）
        if self.stage == "shelf":
            return
        r = self.root
        try:
            r.deiconify()
        except Exception:
            pass
        r.overrideredirect(True)
        try:
            r.attributes("-topmost", True)
        except Exception:
            pass
        self.visible = True
        self._boss_hidden = False
        w, h = r.winfo_width(), r.winfo_height()
        if w < 50:
            w = int(self.store.get("width"))
            h = int(self.store.get("height"))
        r.geometry("%dx%d+%d+%d" % (w, h, self.pos[0], self.pos[1]))
        self._apply_alpha()
        # 老板键清空了渲染，重新出来时必须重绘，否则是空白
        if self.book and not self.text.get("1.0", "end").strip():
            self._render(top=getattr(self, "_boss_top", None))
        self._update_progress()

    def hide(self):
        if self.locked:
            return
        self._save_progress()
        try:
            self.root.withdraw()
        except Exception:
            pass
        self.visible = False
        # 冷却给得很短：移开就藏、移回来就出，别让人等
        self._cooldown = time.time() + 0.05

    def boss_key(self):
        """清空渲染 + 隐藏，不留任何文字痕迹。"""
        self._boss_top = self._top_index()
        self._save_progress()
        self.locked = False
        self._hold_until = 0.0
        try:
            self.text.configure(state="normal")
            self.text.delete("1.0", "end")
            self.text.configure(state="disabled")
            self.pct.place_forget()
        except Exception:
            pass
        try:
            self.root.withdraw()
        except Exception:
            pass
        # 书架 / 设置也一起收掉，否则屏幕上还杵着「我的书架」四个大字
        for attr in ("_shelf_win", "_settings_win"):
            w = getattr(self, attr, None)
            try:
                if w is not None:
                    w.win.withdraw()
            except Exception:
                pass
        self.visible = False
        self._boss_hidden = True
        self._cooldown = time.time() + 1.0

    def _reveal(self):
        if not self.book:
            # 还没进阅读态：唤出的是书架，不是空提示窗
            self._bring_shelf_front()
            self._hide_at = 0.0
            return
        self.show()
        self._hide_at = 0.0

    def toggle_lock(self):
        self.locked = not self.locked
        if self.locked:
            self.flash("已钉住 · 移开不会消失（Ctrl+P 松开）")
        else:
            self.flash("已松开 · 移开自动隐藏")
        # 钉住状态必须有常驻标识，否则用户只会觉得「坏了，不隐藏了」
        self._update_progress()

    def _hint_click_once(self):
        """单击不再默认钉住（一碰就永不隐藏太难排查），只提示一次怎么钉。"""
        try:
            if self.store.data.get("hint_click_pin"):
                return
            self.store.data["hint_click_pin"] = True
            self.store.save()
        except Exception:
            return
        self.flash("单击不再固定窗口 · 想固定按 Ctrl+P")

    # ------------------------------------------------------------ 主循环

    def _in_window(self, x, y):
        try:
            rx, ry = self.root.winfo_rootx(), self.root.winfo_rooty()
            rw, rh = self.root.winfo_width(), self.root.winfo_height()
        except Exception:
            return False
        pad = 10
        return (rx - pad) <= x <= (rx + rw + pad) and (ry - pad) <= y <= (ry + rh + pad)

    def _in_hotzone(self, x, y):
        sw, sh = self._screen()
        hw = int(self.store.get("hotzone_w"))
        hh = int(self.store.get("hotzone_h"))
        corner = self.store.get("hotzone_corner")
        if corner == "top-right":
            return (sw - hw) <= x <= sw and 0 <= y <= hh
        if corner == "top-left":
            return 0 <= x <= hw and 0 <= y <= hh
        if corner == "bottom-right":
            return (sw - hw) <= x <= sw and (sh - hh) <= y <= sh
        return False

    def _in_keep_zone(self, x, y):
        """鼠标停在屏幕右下角保留区时，不触发隐藏。"""
        if not self.hide_keep_br:
            return False
        sw, sh = self._screen()
        return x >= sw * (1 - self.hide_keep_br / 100.0) and \
            y >= sh * (1 - self.hide_keep_br / 100.0)

    def _tick(self):
        try:
            if wapi.wait_reveal(self._reveal_h):
                self._wake_by_second_launch()
            self.hotkeys.poll()
            now = time.time()
            pt = self._pointer()
            if pt is None:
                # 锁屏 / 远程断开会话：读不到鼠标，这一拍维持现状
                self.root.after(50, self._tick)
                return
            x, y = pt
            in_zone = self._in_hotzone(x, y)
            # 隐藏时也要算：鼠标回到原来那块地方，就该重新显出来
            in_win = self._in_window(x, y)
            # 老板键清屏后，鼠标扫过原位置不算数（太容易误触），只认热区和唤出键
            in_area = in_win and not self._boss_hidden

            if self.hide_on_blur and self.visible and wapi.foreground_is_fullscreen():
                self.hide()
                self._hide_at = 0.0
                self.root.after(60, self._tick)
                return

            # 刚选完书：鼠标进过窗口一次就交还给正常悬停规则
            if self._hold_until and in_win:
                self._hold_until = 0.0
            holding = now < self._hold_until

            if holding:
                self._hide_at = 0.0
                self._show_at = 0.0
            elif self.stage in ("shelf", "idle"):
                # 还没选书：书架是主界面；idle 是「书架被关掉但没选书」的兜底提示页。
                # 这两种情况都不是阅读态，阅读窗不该参与自动显隐——否则鼠标一移开，
                # 屏幕上就什么都不剩，用户会以为程序没了。
                self._hide_at = 0.0
                self._show_at = 0.0
            elif self.locked or self.pause_hide > 0 or now < self._grace:
                self._hide_at = 0.0
                self._show_at = 0.0
            elif in_area or in_zone or (self.visible and self._in_keep_zone(x, y)):
                self._hide_at = 0.0
                if not self.visible and now >= self._cooldown:
                    if self._show_at == 0.0:
                        self._show_at = now
                    elif (now - self._show_at) * 1000.0 >= int(self.store.get("enter_delay")):
                        self.show()
                        self._show_at = 0.0
                elif self.visible:
                    self._show_at = 0.0
            else:
                self._show_at = 0.0
                if self.visible:
                    delay = int(self.store.get("leave_delay"))
                    if delay <= 0:
                        # 立刻隐藏：不等下一次 tick，鼠标一离开就没了
                        self.hide()
                        self._hide_at = 0.0
                    elif self._hide_at == 0.0:
                        self._hide_at = now
                    elif (now - self._hide_at) * 1000.0 >= delay:
                        self.hide()
                        self._hide_at = 0.0
        except Exception:
            pass
        self.root.after(50, self._tick)

    # ------------------------------------------------------------ 渲染

    def _set_text(self, s):
        t = self.text
        t.configure(state="normal")
        t.delete("1.0", "end")
        t.insert("1.0", s)
        t.configure(state="disabled")

    def _raw_body(self, ci):
        if getattr(self.book, "is_remote", False):
            return self._remote_body()
        if 0 <= ci < len(self.book.chapters):
            return self.book.chapters[ci][1]
        return ""

    def _styled(self, raw, slot):
        key = (slot, self.keep_format, self.zh)
        hit = self._render_cache.get(key)
        if hit is not None:
            return hit
        s = zhconv.convert(raw, self.zh)
        s = core.format_body(s, keep_format=self.keep_format, indent=True)
        if len(self._render_cache) > 40:
            self._render_cache.clear()
        self._render_cache[key] = s
        return s

    def _render(self, top=None):
        if not self.book:
            self._set_text(EMPTY_HINT)
            self._update_progress()
            return
        body = self._styled(self._raw_body(self.ci),
                            (self.book.fingerprint, self.ci))
        self._set_text(body)
        if top:
            try:
                self.text.yview(top)
            except Exception:
                self.text.yview_moveto(0)
        else:
            self.text.yview_moveto(0)
        self._update_progress()

    def _remote_body(self):
        key = (self.book.fingerprint, self.ci)
        if key in self._body_cache:
            return self._body_cache[key]
        if key in self._loading:
            return "正在取这一章…"
        self._loading.add(key)
        ci = self.ci
        book = self.book

        def work():
            try:
                body = book.fetch_chapter(ci)
            except Exception as e:
                body = "抓取失败：%s\n\n可以按方向键换一章试试，或回到目录重新选。" % e
            self._body_cache[key] = body
            self._loading.discard(key)
            self.root.after(0, lambda: self._after_fetch(ci))

        threading.Thread(target=work, daemon=True).start()
        return "正在取这一章…"

    def _after_fetch(self, ci):
        if self.book and self.ci == ci:
            self._set_text(self._styled(
                self._body_cache.get((self.book.fingerprint, ci), ""),
                (self.book.fingerprint, ci)))
            self.text.yview_moveto(0)
            self._update_progress()

    def flash(self, msg):
        try:
            self.lbl.configure(text=msg, fg=self._dim_color(0.15))
            self.lbl.place(relx=0.0, rely=1.0, anchor="sw", x=8, y=-2)
            self._tip_until = time.time() + 2.0
            self.root.after(2100, self._clear_flash)
        except Exception:
            pass

    def _clear_flash(self):
        if time.time() >= self._tip_until - 0.15:
            try:
                self.lbl.configure(text="")
                self.lbl.place_forget()
            except Exception:
                pass

    def _top_index(self):
        try:
            return self.text.index("@0,0")
        except Exception:
            return None

    def _update_progress(self):
        if not self.book:
            try:
                self.canvas_bar.coords(self.bar, 0, 0, 0, 2)
            except Exception:
                pass
            self._set_badge(None)
            return
        try:
            frac = (self.ci + self.text.yview()[0]) / float(max(1, len(self.book.chapters)))
        except Exception:
            frac = 0.0
        if self.show_bar:
            try:
                w = self.canvas_bar.winfo_width()
                if w < 2:
                    w = self.root.winfo_width()
                self.canvas_bar.coords(self.bar, 0, 0, int(w * frac), 2)
            except Exception:
                pass
        self._set_badge(frac if self.show_percent else None)

    def _set_badge(self, frac):
        """右下角小字：百分比 + 钉住标识。钉住时无论开没开百分比都要显示。"""
        parts = []
        if self.locked:
            parts.append("已钉住")
        if frac is not None:
            parts.append("%.2f%%" % (frac * 100))
        txt = " · ".join(parts)
        try:
            self.pct.configure(text=txt)
        except Exception:
            return
        self._place_pct()

    # ------------------------------------------------------------ 进度

    def _save_progress(self):
        if not self.book:
            return
        top = self._top_index() or "1.0"
        key = (self.book.fingerprint, self.ci, top)
        if key == self._saved_key:
            # 位置没变就不写盘：现在隐藏是「立刻」的，别每次移开鼠标都存一遍
            return
        self._saved_key = key
        try:
            frac = (self.ci + self.text.yview()[0]) / float(max(1, len(self.book.chapters)))
        except Exception:
            frac = 0.0
        self.store.set_progress(self.book.fingerprint, self.book.name,
                                self.book.path, self.ci, top, frac)

    def resume_last(self, silent=True):
        """继续上次读到的那本（书架上的「▶ 继续」按钮用）。"""
        last = self.store.data.get("last")
        rec = self.store.get_progress(last) if last else None
        if not rec:
            return False
        item = self.store.shelf_find(last)
        if not item:
            return False
        self.open_shelf_item(item, silent=silent)
        return True

    # ------------------------------------------------------------ 导入

    def cmd_import(self):
        self.pause_hide += 1
        try:
            paths = filedialog.askopenfilenames(
                parent=self._dlg_parent(), title="选择书籍（可多选）",
                filetypes=[("电子书", "*.txt *.epub"),
                           ("文本文件", "*.txt"), ("EPUB 电子书", "*.epub"),
                           ("所有文件", "*.*")])
        finally:
            self.pause_hide = max(0, self.pause_hide - 1)
        if not paths:
            return
        for p in paths:
            self.load_book(p, take_last=(p == paths[-1]))

    def load_book(self, path, silent=False, chapter=None, top=None, take_last=True):
        try:
            b = core.Book(path).load()
        except Exception as e:
            if not silent:
                messagebox.showerror("打开失败", str(e), parent=self._dlg_parent())
            return False
        if not b.text.strip():
            if not silent:
                messagebox.showwarning("没有内容", "这个文件是空的。", parent=self._dlg_parent())
            return False

        self.store.shelf_add(b.fingerprint, b.name, b.path, b.kind,
                             len(b.chapters), b.total_chars)
        if not take_last:
            self.flash("已加入书架：%s" % b.name[:14])
            self._refresh_shelf()
            return True

        self.book = b
        self._body_cache = {}
        self._render_cache = {}
        rec = self.store.get_progress(b.fingerprint)
        if chapter is not None:
            self.ci = max(0, min(int(chapter), len(b.chapters) - 1))
            self._render(top=top)
        elif rec:
            self.ci = max(0, min(int(rec.get("chapter") or 0), len(b.chapters) - 1))
            self._render(top=rec.get("top") or "1.0")
        elif self.ci < len(b.chapters):
            self._render()
        else:
            self.ci = 0
            self._render()

        tip = "%s · %d 章 · %s" % (b.name[:14], len(b.chapters), b.encoding)
        if zhconv.has_traditional(b.text) and self.zh == "none":
            tip += "  (疑似繁体，Ctrl+, 可开繁转简)"
        self._enter_reading()
        self.flash(tip)
        self._save_progress()
        return True

    def cmd_import_url(self):
        self.pause_hide += 1
        try:
            url = simpledialog.askstring(
                "导入网址", "粘贴小说目录页的网址：\n（有很多章节链接的那个页面）",
                parent=self._dlg_parent())
        finally:
            self.pause_hide = max(0, self.pause_hide - 1)
        if not url:
            return
        url = url.strip()
        if not re.match(r'^https?://', url, re.I):
            url = "https://" + url
        self._load_web_async(url)

    def _load_web_async(self, url, restore=None):
        self._set_text("正在抓目录…\n\n%s" % url)
        self.show()

        def work():
            try:
                b = webimport.WebBook(url).load()
                err = None
            except Exception as e:
                b, err = None, str(e)
            self.root.after(0, lambda: self._on_web_loaded(b, err, restore))

        threading.Thread(target=work, daemon=True).start()

    def _on_web_loaded(self, book, err, restore):
        if err:
            if self.stage != "shelf":
                self._render()
            messagebox.showerror("抓取失败", err, parent=self._dlg_parent())
            return
        self.book = book
        self._body_cache = {}
        self._render_cache = {}
        self.store.shelf_add(book.fingerprint, book.name, book.path, "web",
                             len(book.chapters), 0)
        if restore:
            self.ci = max(0, min(int(restore.get("chapter") or 0), len(book.chapters) - 1))
        else:
            self.ci = 0
        self._render(top=(restore or {}).get("top"))
        self._enter_reading()
        self.flash("%s · %d 章" % (book.name[:14], len(book.chapters)))

    def goto_chapter(self, i, top=None):
        if not self.book:
            return
        self.ci = max(0, min(int(i), len(self.book.chapters) - 1))
        self._render(top=top)
        self._save_progress()
        if not top:
            try:
                self.flash("%s  (%d/%d)" % (self.book.chapters[self.ci][0][:18],
                                            self.ci + 1, len(self.book.chapters)))
            except Exception:
                pass

    def next_chapter(self):
        if self.book and self.ci < len(self.book.chapters) - 1:
            self.goto_chapter(self.ci + 1)
        else:
            self.flash("已经是最后一章了")

    def prev_chapter(self):
        if self.book and self.ci > 0:
            self.goto_chapter(self.ci - 1)

    # ------------------------------------------------------------ 目录

    def cmd_toc(self):
        if not self.book:
            self.flash("还没有书 · Ctrl+B 打开书架")
            return
        self.pause_hide += 1
        win = tk.Toplevel(self.root)
        win.title("目录")
        win.configure(bg="#1E1E1E")
        win.attributes("-topmost", True)
        w, h = 400, 540
        sw, sh = self._screen()
        x = max(0, min(self.pos[0] - w - 16, sw - w - 10))
        y = max(0, min(self.pos[1], sh - h - 40))
        win.geometry("%dx%d+%d+%d" % (w, h, x, y))

        ent = tk.Entry(win, bg="#2A2A2A", fg="#DDDDDD", insertbackground="#DDDDDD",
                       bd=0, relief="flat", font=("Microsoft YaHei", 11))
        ent.pack(fill="x", padx=10, pady=(10, 6), ipady=5)

        lb = tk.Listbox(win, bg="#1E1E1E", fg="#C8C8C8", bd=0, highlightthickness=0,
                        activestyle="none", selectbackground="#3C3C3C",
                        selectforeground="#FFFFFF", font=("Microsoft YaHei", 10))
        lb.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        index_map = []

        def fill(kw=""):
            lb.delete(0, "end")
            del index_map[:]
            kw = kw.strip().lower()
            for i, ch in enumerate(self.book.chapters):
                label = "%d. %s" % (i + 1, ch[0])
                if kw and kw not in label.lower():
                    continue
                lb.insert("end", label)
                index_map.append(i)
            if not index_map:
                lb.insert("end", "没有匹配的章节")
            else:
                for pos, ci in enumerate(index_map):
                    if ci == self.ci:
                        lb.selection_clear(0, "end")
                        lb.selection_set(pos)
                        lb.see(pos)
                        break

        def do_jump(_e=None):
            sel = lb.curselection()
            if not sel or sel[0] >= len(index_map):
                return
            self.goto_chapter(index_map[sel[0]])
            close()

        def close(_e=None):
            self.pause_hide = max(0, self.pause_hide - 1)
            try:
                win.destroy()
            except Exception:
                pass

        ent.bind("<KeyRelease>", lambda e: fill(ent.get()))
        ent.bind("<Return>", lambda e: fill(ent.get()))
        lb.bind("<Double-Button-1>", do_jump)
        lb.bind("<Return>", do_jump)
        win.bind("<Escape>", close)
        win.protocol("WM_DELETE_WINDOW", close)

        fill()
        ent.focus_set()

    # ------------------------------------------------------------ 书架 / 设置

    def open_shelf(self):
        if not self.book:
            # 没有书时书架就是主界面：状态跟着回去，关掉它才会走 idle 兜底
            self.stage = "shelf"
        if self._shelf_win is not None:
            try:
                self._shelf_win.win.deiconify()
                self._shelf_win.win.lift()
                self._shelf_win.win.focus_force()
                self._shelf_win.refresh()
                return
            except Exception:
                self._shelf_win = None
        self.pause_hide += 1
        self._shelf_win = shelf_mod.Bookshelf(self)
        self._shelf_win.win.protocol("WM_DELETE_WINDOW", self._close_shelf)

    def _close_shelf(self, _e=None):
        try:
            self._shelf_win.win.destroy()
        except Exception:
            pass
        self._shelf_win = None
        self.pause_hide = max(0, self.pause_hide - 1)
        # 还没选书就把书架关了：别让整个软件「消失」，至少露个提示窗在地上
        if self.stage == "shelf" and not self.book:
            self.stage = "idle"
            self._render()
            self.show()

    def _refresh_shelf(self):
        if self._shelf_win is not None:
            try:
                self._shelf_win.refresh()
            except Exception:
                pass

    def open_settings(self):
        if self._settings_win is not None:
            try:
                self._settings_win.win.deiconify()
                self._settings_win.win.lift()
                return
            except Exception:
                self._settings_win = None
        self.pause_hide += 1
        self._settings_win = settings_ui.SettingsWindow(self)
        self._settings_win.win.protocol("WM_DELETE_WINDOW", self._close_settings)

    def _close_settings(self):
        try:
            self._settings_win.win.destroy()
        except Exception:
            pass
        self._settings_win = None
        self.pause_hide = max(0, self.pause_hide - 1)

    def open_shelf_item(self, item, silent=False):
        path = item.get("path") or ""
        if re.match(r'^https?://', path):
            self._load_web_async(path)
        else:
            self.load_book(path, silent=silent)

    # ------------------------------------------------------------ 快捷键

    def _bind_fixed(self):
        r = self.root
        r.bind("<Control-o>", lambda e: self.cmd_import())
        r.bind("<Control-u>", lambda e: self.cmd_import_url())
        r.bind("<Control-b>", lambda e: self.open_shelf())
        r.bind("<Control-comma>", lambda e: self.open_settings())
        r.bind("<F1>", lambda e: self._help())
        r.bind("<F3>", lambda e: self.toggle_through())
        r.bind("<Control-p>", lambda e: self.toggle_lock())
        for w in (self.text, self.canvas_bar):
            w.bind("<Button-1>", self._on_press)
            w.bind("<B1-Motion>", self._on_drag)
            w.bind("<ButtonRelease-1>", self._on_release)
            w.bind("<Button-3>", self._on_menu)
            w.bind("<MouseWheel>", self._on_wheel)
            w.bind("<Control-MouseWheel>", self._on_wheel_alpha)
            w.bind("<Alt-MouseWheel>", self._on_wheel_fg)
        self.pct.bind("<Button-1>", self._on_menu)

    def refresh_bindings(self):
        for seq in self._bound_seqs:
            try:
                self.root.unbind(seq)
            except Exception:
                pass
        self._bound_seqs = []

        keys = self.store.get("keys") or {}
        actions = {
            "page_up": lambda e: self._page(-1),
            "page_down": lambda e: self._page(1),
            "chapter_up": lambda e: self.prev_chapter(),
            "chapter_down": lambda e: self.next_chapter(),
            "toc": lambda e: self.cmd_toc(),
            "auto_page": lambda e: self.toggle_auto_page(),
        }
        for name, cb in actions.items():
            for combo in (keys.get(name) or []):
                seq = to_tk_seq(combo)
                if not seq or seq in self._bound_seqs:
                    continue
                try:
                    self.root.bind(seq, cb)
                    self._bound_seqs.append(seq)
                except Exception:
                    pass

        # 固定辅助键（不参与自定义，避免占坑）
        for seq, cb in (("<Shift-Up>", lambda e: self._scroll(-1)),
                        ("<Shift-Down>", lambda e: self._scroll(1)),
                        ("<Prior>", lambda e: self._page(-1)),
                        ("<Next>", lambda e: self._page(1)),
                        ("<Home>", lambda e: self._to_top()),
                        ("<End>", lambda e: self._to_bottom()),
                        ("<Escape>", lambda e: self.boss_key())):
            try:
                self.root.bind(seq, cb)
                self._bound_seqs.append(seq)
            except Exception:
                pass

    def _page(self, d):
        try:
            if self.page_lines > 0:
                step = self.page_lines * d
            else:
                h = max(1, self.text.winfo_height())
                ls = max(1, getattr(self, "linespace", 18))
                step = max(1, int(h / float(ls)) - 1) * d
            if d > 0 and self.text.yview()[1] >= 0.999 and self.continuous:
                self.next_chapter()
                return
            self.text.yview_scroll(step, "units")
            self._update_progress()
        except Exception:
            pass

    def _scroll(self, d):
        try:
            self.text.yview_scroll(d, "units")
            self._update_progress()
        except Exception:
            pass

    def _to_top(self):
        self.text.yview_moveto(0)
        self._update_progress()

    def _to_bottom(self):
        self.text.yview_moveto(1.0)
        self._update_progress()

    def _on_wheel(self, e):
        now = time.time()
        if now - self._last_wheel < self.wheel_delay:
            return
        self._last_wheel = now
        try:
            up = e.delta > 0
            if self.wheel_invert:
                up = not up
            if up:
                if self.text.yview()[0] <= 0.001:
                    self.prev_chapter()
                    return
                self.text.yview_scroll(-3, "units")
            else:
                if self.text.yview()[1] >= 0.999:
                    if self.continuous:
                        self.next_chapter()
                    return
                self.text.yview_scroll(3, "units")
            self._update_progress()
        except Exception:
            pass

    FG_STEPS = ["#1F1F1F", "#2E2E2E", "#3A3A3A", "#4A4A4A", "#5A5A5A",
                "#6E6E6E", "#828282", "#969696", "#AAAAAA"]

    def _on_wheel_alpha(self, e):
        """Ctrl+滚轮：调窗口底色深浅。"""
        if self.bg_mode != "solid":
            self.flash("当前是「只留文字」模式，按 Ctrl+, 切成带底才能调")
            return
        d = 0.04 if e.delta > 0 else -0.04
        self.bg_alpha = max(0.25, min(1.0, round(self.bg_alpha + d, 2)))
        self.store.set("bg_alpha", self.bg_alpha)
        self.store.save()
        self._apply_alpha()
        self.flash("背景不透明度 %d%%" % int(self.bg_alpha * 100))

    def _on_wheel_fg(self, e):
        """Alt+滚轮：调文字深浅。"""
        steps = self.FG_STEPS
        cur = (self.fg or "").upper()
        idx = 2
        best = 999
        for i, c in enumerate(steps):
            try:
                v = int(c[1:3], 16)
            except ValueError:
                continue
            try:
                d = abs(int(cur[1:3], 16) - v)
            except ValueError:
                d = 999
            if d < best:
                best, idx = d, i
        idx = max(0, min(len(steps) - 1, idx + (1 if e.delta > 0 else -1)))
        self.fg = steps[idx]
        self.store.set("fg", self.fg)
        self.store.save()
        self._apply_theme()
        self.flash("文字深浅 %s" % self.fg)

    def _on_press(self, e):
        self._drag = {"x": e.x_root, "y": e.y_root,
                      "sx": self.pos[0], "sy": self.pos[1], "moved": False}

    def _on_drag(self, e):
        if not self._drag or not self.window_movable:
            return
        dx = e.x_root - self._drag["x"]
        dy = e.y_root - self._drag["y"]
        if abs(dx) > 3 or abs(dy) > 3:
            self._drag["moved"] = True
        nx = self._drag["sx"] + dx
        ny = self._drag["sy"] + dy
        self.pos = [nx, ny]
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        self.root.geometry("%dx%d+%d+%d" % (w, h, nx, ny))

    def _on_release(self, e):
        moved = bool(self._drag and self._drag.get("moved"))
        self._drag = None
        if moved:
            self.store.set("pos_x", self.pos[0])
            self.store.set("pos_y", self.pos[1])
            self.store.save()
            return
        if self.mouse_page:
            self._page(1)
        elif self.click_pin:
            self.toggle_lock()
        else:
            self._hint_click_once()

    # ------------------------------------------------------------ 自动翻页

    def _auto_page_loop(self):
        try:
            if self.auto_page > 0 and self.visible:
                if self.text.yview()[1] >= 0.999:
                    if self.continuous:
                        self.next_chapter()
                else:
                    self.text.yview_scroll(1, "units")
                    self._update_progress()
        except Exception:
            pass
        self.root.after(max(120, self.auto_page or 600), self._auto_page_loop)

    def toggle_auto_page(self):
        if self.auto_page > 0:
            self.store.set("auto_page", 0)
            self.auto_page = 0
            self.flash("自动翻页 关")
        else:
            self.store.set("auto_page", 1800)
            self.auto_page = 1800
            self.flash("自动翻页 开 · 1.8 秒一行")
        self.store.save()

    def _why_not_hidden(self):
        """自查：把当前挡住「自动隐藏」的原因直接说出来。"""
        now = time.time()
        why = []
        if self.locked:
            why.append("窗口被钉住了（Ctrl+P 松开）")
        if self.pause_hide > 0:
            why.append("有面板开着（书架/设置/目录/菜单）")
        if now < self._hold_until:
            why.append("刚选完书，还在 %.0f 秒保护期内" % (self._hold_until - now))
        if now < self._grace:
            why.append("%.0f 秒预热期" % (self._grace - now))
        if self._boss_hidden:
            why.append("按过老板键，要 Ctrl+Alt+Z 才回来")
        pt = self._pointer()
        if pt is None:
            why.append("读不到鼠标位置（锁屏/远程断开会这样）")
        elif self._in_hotzone(*pt):
            why.append("鼠标正停在屏幕角落热区里")
        elif self._in_window(*pt):
            why.append("鼠标还在窗口内（或窗口外 10 像素内）")
        elif self._in_keep_zone(*pt) and self.visible:
            why.append("鼠标在右下角保留区")
        if not why:
            why.append("没有东西挡着，移开应当 %.0f 毫秒内消失"
                       % int(self.store.get("leave_delay")))
        self.flash(" · ".join(why)[:52])

    # ------------------------------------------------------------ 菜单

    def _on_menu(self, e):
        if not self.visible:
            self.show()
        m = tk.Menu(self.root, tearoff=0, bg="#2A2A2A", fg="#DDDDDD",
                    activebackground="#3C3C3C", activeforeground="#FFFFFF",
                    bd=0, relief="flat", font=("Microsoft YaHei", 10))
        m.add_command(label="书架                  Ctrl+B", command=self.open_shelf)
        m.add_command(label="设置                  Ctrl+,", command=self.open_settings)
        m.add_command(label="目录                  Ctrl+G", command=self.cmd_toc)
        m.add_separator()
        m.add_command(label="导入书籍            Ctrl+O", command=self.cmd_import)
        m.add_command(label="导入网址              Ctrl+U", command=self.cmd_import_url)
        m.add_separator()
        m.add_command(label="自动翻页              Ctrl+R", command=self.toggle_auto_page)
        m.add_command(label="钉住 / 松开           Ctrl+P" +
                      ("（当前已钉住）" if self.locked else ""),
                      command=self.toggle_lock)
        m.add_command(label="为什么没自动隐藏？", command=self._why_not_hidden)
        m.add_command(label="鼠标穿透            F3", command=self.toggle_through)
        m.add_separator()
        m.add_command(label="清除阅读记录", command=self.cmd_clear)
        m.add_command(label="快捷键说明            F1", command=self._help)
        m.add_separator()
        m.add_command(label="隐藏", command=self.hide)
        m.add_command(label="退出", command=self.quit)

        self.pause_hide += 1
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()
        self.root.after(150, lambda: self._menu_watch(m))

    def _menu_watch(self, m):
        try:
            if m.winfo_ismapped():
                self.root.after(150, lambda: self._menu_watch(m))
                return
            m.destroy()
        except Exception:
            pass
        self.pause_hide = max(0, self.pause_hide - 1)

    def _help(self):
        keys = self.store.get("keys") or {}
        lines = [
            "书架            Ctrl+B",
            "设置            Ctrl+,",
            "导入书籍        Ctrl+O",
            "导入网址        Ctrl+U",
            "目录            Ctrl+G",
            "自动翻页        Ctrl+R",
            "",
            "上一页          %s" % " / ".join(keys.get("page_up") or ["-"]),
            "下一页          %s" % " / ".join(keys.get("page_down") or ["-"]),
            "上一章          %s" % " / ".join(keys.get("chapter_up") or ["-"]),
            "下一章          %s" % " / ".join(keys.get("chapter_down") or ["-"]),
            "",
            "单击正文        %s" % ("翻页" if self.mouse_page else
                                    ("钉住 / 松开" if self.click_pin else "不做事")),
            "钉住 / 松开     Ctrl+P  （钉住后移开鼠标也不会消失）",
            "鼠标穿透        F3   （穿透后能操作下层软件）",
            "Ctrl+滚轮       调背景深浅",
            "Alt+滚轮        调文字深浅",
            "Shift+↑/↓       逐行滚动",
            "滚轮            翻页",
            "",
            "全局（窗口隐藏时也生效）：",
            "%s   一键清屏" % str(self.store.get("boss_key")).upper(),
            "%s   手动唤出" % str(self.store.get("reveal_key")).upper(),
            "%s   鼠标穿透开关" % str(self.store.get("through_key")).upper(),
            "",
            "唤出热区：屏幕 %s 角 %dx%d 像素" % (
                {"top-right": "右上", "top-left": "左上",
                 "bottom-right": "右下"}.get(self.store.get("hotzone_corner"), "右上"),
                int(self.store.get("hotzone_w")),
                int(self.store.get("hotzone_h"))),
        ]
        messagebox.showinfo("快捷键", "\n".join(lines), parent=self._dlg_parent())

    def cmd_clear(self):
        if messagebox.askyesno("清除记录", "清空所有阅读进度？书和书架都保留。",
                               parent=self._dlg_parent()):
            self.store.clear_recent()
            self._saved_key = None
            self.flash("进度已清空")

    def quit(self):
        self._save_progress()
        self.store.save()
        for attr in ("_settings_win", "_shelf_win"):
            w = getattr(self, attr, None)
            try:
                if w:
                    w.win.destroy()
            except Exception:
                pass
        try:
            self.root.quit()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

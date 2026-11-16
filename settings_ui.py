# -*- coding: utf-8 -*-
"""设置面板：阅读器外观 / 阅读器功能 / 其他，三页签，改动即时生效。"""
import tkinter as tk
import tkinter.font as tkfont
from tkinter import colorchooser, simpledialog, messagebox
from tkinter import ttk

import wapi

# ---- 配色（面板自身用浅色，可读性优先）
C_BG = "#FFFFFF"
C_PANEL = "#F7F8FA"
C_HEAD = "#2F5C9E"
C_LINE = "#E6E8EC"
C_TEXT = "#2B2F36"
C_HINT = "#9AA0A8"
C_ACCENT = "#2F6FE4"
C_BTN = "#F2F4F7"

SHOW_FONT = ("Microsoft YaHei", 10)
SMALL_FONT = ("Microsoft YaHei", 9)

BG_PRESETS = [
    ("浅淡（白底页）", {"bg_mode": "solid", "bg": "#F4F5F7", "bg_alpha": 0.82,
                        "fg": "#3A3A3A"}),
    ("更淡（几乎隐形）", {"bg_mode": "solid", "bg": "#F4F5F7", "bg_alpha": 0.55,
                          "fg": "#4A4A4A"}),
    ("深淡（深色 IDE）", {"bg_mode": "solid", "bg": "#1B1B1B", "bg_alpha": 0.72,
                          "fg": "#D6D6D6"}),
    ("只留文字", {"bg_mode": "transparent", "fg": "#5A5A5A"}),
    ("只留文字 · 深色", {"bg_mode": "transparent", "fg": "#C8C8C8"}),
]


class Toggle(tk.Canvas):
    """自绘开关：44x22，圆角胶囊 + 滑块。"""

    def __init__(self, master, var, command=None, width=44, height=22):
        tk.Canvas.__init__(self, master, width=width, height=height,
                           bg=C_BG, bd=0, highlightthickness=0, cursor="hand2")
        self.var = var
        self.command = command
        self._wd = width
        self._ht = height
        self.bind("<Button-1>", self._click)
        if hasattr(var, "trace_add"):
            var.trace_add("write", lambda *a: self._draw())
        else:
            var.trace("w", lambda *a: self._draw())
        self._draw()

    def _click(self, _e=None):
        self.var.set(not bool(self.var.get()))
        if self.command:
            self.command()

    def _draw(self):
        self.delete("all")
        on = bool(self.var.get())
        h = self._ht
        r = h / 2.0
        w = self._wd
        track = C_ACCENT if on else "#CFD4DA"
        # 胶囊：两个圆 + 中间矩形
        self.create_oval(0, 0, h, h, fill=track, outline=track)
        self.create_oval(w - h, 0, w, h, fill=track, outline=track)
        self.create_rectangle(r, 0, w - r, h, fill=track, outline=track)
        cx = (w - r) if on else r
        pad = 2.5
        self.create_oval(cx - r + pad, pad, cx + r - pad, h - pad,
                         fill="#FFFFFF", outline="")


class Recorder(tk.Toplevel):
    """录制一个组合键。"""

    def __init__(self, master, on_done, current=""):
        tk.Toplevel.__init__(self, master)
        self.on_done = on_done
        self.title("录制快捷键")
        self.configure(bg=C_BG)
        self.resizable(False, False)
        self.attributes("-topmost", True)
        try:
            self.transient(master)
        except Exception:
            pass
        self.geometry("360x150+%d+%d" % (master.winfo_rootx() + 120,
                                         master.winfo_rooty() + 120))
        tk.Label(self, text="直接按下你要用的组合键", bg=C_BG, fg=C_TEXT,
                 font=("Microsoft YaHei", 11, "bold")).pack(pady=(22, 6))
        self.lbl = tk.Label(self, text=current.upper() or "等待按键…",
                            bg=C_BG, fg=C_ACCENT, font=("Consolas", 14))
        self.lbl.pack()
        tk.Label(self, text="Esc 取消 · 建议 Ctrl+Alt+某键，避免和软件冲突",
                 bg=C_BG, fg=C_HINT, font=SMALL_FONT).pack(pady=(8, 0))
        self.bind("<KeyPress>", self._key)
        self.focus_force()

    def _key(self, e):
        if e.keysym == "Escape":
            self.destroy()
            return
        mods = []
        st = e.state
        if st & 0x4:
            mods.append("ctrl")
        if st & 0x20000 or st & 0x8:
            mods.append("alt")
        if st & 0x1:
            mods.append("shift")
        k = e.keysym
        if k in ("Control_L", "Control_R", "Alt_L", "Alt_R",
                 "Shift_L", "Shift_R", "Win_L", "Win_R"):
            self.lbl.configure(text="+".join(mods + ["…"]).upper() if mods else "等待按键…")
            return
        name = k.lower()
        if len(name) > 1 and not (name.startswith("f") and name[1:].isdigit()):
            mapping = {"space": "space", "up": "up", "down": "down",
                       "left": "left", "right": "right", "tab": "tab",
                       "return": "enter", "escape": "esc", "prior": "pageup",
                       "next": "pagedown", "backspace": "backspace",
                       "grave": "`", "minus": "-", "equal": "=",
                       "bracketleft": "[", "bracketright": "]"}
            name = mapping.get(name, name)
        combo = "+".join(mods + [name])
        self.on_done(combo)
        self.destroy()


class SettingsWindow(object):

    def __init__(self, app):
        self.app = app
        self.store = app.store
        self.win = tk.Toplevel(app.root)
        self.win.title("阅读器设置")
        self.win.configure(bg=C_BG)
        self.win.attributes("-topmost", True)
        sw, sh = app.root.winfo_screenwidth(), app.root.winfo_screenheight()
        w, h = min(880, sw - 80), min(620, sh - 110)
        self.win.geometry("%dx%d+%d+%d" % (w, h, max(20, (sw - w) // 2),
                                           max(20, (sh - h) // 3)))
        self.win.minsize(720, 460)

        self.tab = "look"
        self._build_frame()

    # ------------------------------------------------------------ 骨架

    def _build_frame(self):
        w = self.win
        # 顶部
        head = tk.Frame(w, bg=C_HEAD, height=54)
        head.pack(fill="x")
        head.pack_propagate(False)

        self.prof_btn = tk.Label(head, text="≡  %s ▾" % self.store.active,
                                 bg=C_HEAD, fg="#FFFFFF",
                                 font=("Microsoft YaHei", 10), cursor="hand2",
                                 padx=12)
        self.prof_btn.pack(side="left", pady=14)
        self.prof_btn.bind("<Button-1>", self._profile_menu)

        tk.Label(head, text="阅读器设置", bg=C_HEAD, fg="#FFFFFF",
                 font=("Microsoft YaHei", 13, "bold")).pack(side="left", expand=True)

        help_lbl = tk.Label(head, text="?  关于老板键", bg=C_HEAD, fg="#D8E3F5",
                            font=SHOW_FONT, cursor="hand2", padx=12)
        help_lbl.pack(side="right", pady=14)
        help_lbl.bind("<Button-1>", lambda e: self._boss_help())

        # 页签
        tabbar = tk.Frame(w, bg=C_BG, height=44)
        tabbar.pack(fill="x")
        tabbar.pack_propagate(False)
        self._tabs = {}
        for key, label in (("look", "阅读器外观"), ("func", "阅读器功能"),
                           ("misc", "其他")):
            lb = tk.Label(tabbar, text=label, bg=C_BG, fg="#6B7280",
                          font=("Microsoft YaHei", 10), padx=26, cursor="hand2")
            lb.pack(side="left", fill="y")
            lb.bind("<Button-1>", lambda e, k=key: self._switch(k))
            self._tabs[key] = lb
        tk.Frame(w, bg=C_LINE, height=1).pack(fill="x")

        # 内容区（可滚动：小屏或内容多时底部按钮不会被挤出）
        self.body = tk.Frame(w, bg=C_BG)
        self.body.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(self.body, bg=C_BG, bd=0, highlightthickness=0)
        vsb = ttk.Scrollbar(self.body, orient="vertical", command=self.canvas.yview)
        vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.configure(yscrollcommand=vsb.set)

        self.inner = tk.Frame(self.canvas, bg=C_BG)
        self.winid = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(
            self.winid, width=e.width))
        self.canvas.bind_all("<MouseWheel>", self._on_wheel, add="+")

        # 底部
        tk.Frame(w, bg=C_LINE, height=1).pack(fill="x")
        foot = tk.Frame(w, bg=C_BG, height=62)
        foot.pack(fill="x")
        foot.pack_propagate(False)
        self._btn(foot, "恢复默认设置", self._reset, side="right", ghost=True)
        self._btn(foot, "保存并关闭", self._close, side="right")
        tk.Label(foot, text="改动即时生效，可先看效果再保存", bg=C_BG,
                 fg=C_HINT, font=SMALL_FONT).pack(side="left", padx=22)

        self._switch(self.tab)

    def _btn(self, parent, text, cmd, side="left", ghost=False):
        b = tk.Label(parent, text=text, bg=C_BTN if ghost else C_ACCENT,
                     fg=C_TEXT if ghost else "#FFFFFF",
                     font=("Microsoft YaHei", 10), padx=20, pady=8,
                     cursor="hand2")
        b.pack(side=side, padx=(0, 14), pady=12)
        b.bind("<Button-1>", lambda e: cmd())
        return b

    def _switch(self, key):
        self.tab = key
        for k, lb in self._tabs.items():
            if k == key:
                lb.configure(fg=C_ACCENT, font=("Microsoft YaHei", 10, "bold"))
            else:
                lb.configure(fg="#6B7280", font=("Microsoft YaHei", 10))
        self._rebuild()

    def _on_wheel(self, e):
        try:
            if not self.win.winfo_ismapped():
                return
            px, py = self.win.winfo_pointerxy()
            rx, ry = self.win.winfo_rootx(), self.win.winfo_rooty()
            if not (rx <= px <= rx + self.win.winfo_width()
                    and ry <= py <= ry + self.win.winfo_height()):
                return
            self.canvas.yview_scroll(-1 if e.delta > 0 else 1, "units")
        except Exception:
            pass

    def _rebuild(self):
        for ch in self.inner.winfo_children():
            ch.destroy()
        if self.tab == "look":
            self._tab_look()
        elif self.tab == "func":
            self._tab_func()
        else:
            self._tab_misc()
        try:
            self.canvas.yview_moveto(0)
            self.inner.update_idletasks()
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        except Exception:
            pass

    # ------------------------------------------------------------ 控件工厂

    def _grid(self, cols=4):
        f = tk.Frame(self.inner, bg=C_BG)
        f.pack(fill="both", expand=True, padx=26, pady=(14, 20))
        for c in (0, 2):
            f.grid_columnconfigure(c, minsize=86)
        f.grid_columnconfigure(1, weight=1, minsize=190)
        f.grid_columnconfigure(3, weight=1, minsize=190)
        return f

    def _label(self, parent, r, c, text, hint=None):
        box = tk.Frame(parent, bg=C_BG)
        box.grid(row=r, column=c, sticky="w", pady=9)
        tk.Label(box, text=text, bg=C_BG, fg=C_TEXT, font=SHOW_FONT).pack(side="left")
        if hint:
            q = tk.Label(box, text="?", bg="#E8EAEE", fg="#7A818C",
                         font=("Microsoft YaHei", 7), width=2, cursor="question_arrow")
            q.pack(side="left", padx=(5, 0))
            q.bind("<Enter>", lambda e, t=hint: self._tip(t))
            q.bind("<Leave>", lambda e: self._tip(""))
        return box

    def _tip(self, text):
        if not hasattr(self, "_tipwin"):
            self._tipwin = tk.Toplevel(self.win)
            self._tipwin.overrideredirect(True)
            self._tipwin.attributes("-topmost", True)
            self._tiplbl = tk.Label(self._tipwin, bg="#33383F", fg="#FFFFFF",
                                    font=SMALL_FONT, padx=10, pady=6, justify="left",
                                    wraplength=280)
            self._tiplbl.pack()
            self._tipwin.withdraw()
        if not text:
            self._tipwin.withdraw()
            return
        self._tiplbl.configure(text=text)
        x = self.win.winfo_pointerx() + 14
        y = self.win.winfo_pointery() + 16
        self._tipwin.geometry("+%d+%d" % (x, y))
        self._tipwin.deiconify()

    def _set(self, key, value, rebuild=False, retheme=True):
        self.store.set(key, value)
        self.store.save()
        if rebuild:
            self._rebuild()
        if retheme:
            self.app.apply_settings()

    def _entry(self, parent, r, c, key, width=8, suffix="", cast=int, lo=None, hi=None):
        var = tk.StringVar(value=str(self.store.get(key)))
        box = tk.Frame(parent, bg=C_BG)
        box.grid(row=r, column=c, sticky="w", pady=9)
        e = tk.Entry(box, textvariable=var, width=width, bg=C_BG, fg=C_TEXT,
                     bd=0, highlightthickness=1, highlightbackground=C_LINE,
                     highlightcolor=C_ACCENT, font=SHOW_FONT, justify="center")
        e.pack(side="left", ipady=5)

        def commit(_e=None):
            try:
                v = cast(var.get())
            except (TypeError, ValueError):
                return
            if lo is not None:
                v = max(lo, v)
            if hi is not None:
                v = min(hi, v)
            var.set(str(v))
            self._set(key, v)

        e.bind("<Return>", commit)
        e.bind("<FocusOut>", commit)
        if suffix:
            tk.Label(box, text=suffix, bg=C_BG, fg=C_HINT,
                     font=SMALL_FONT).pack(side="left", padx=(6, 0))
        return e

    def _slider(self, parent, r, c, key, lo, hi, res, suffix="", fmt=None, cast=float):
        var = tk.DoubleVar(value=float(self.store.get(key)))
        box = tk.Frame(parent, bg=C_BG)
        box.grid(row=r, column=c, sticky="w", pady=6)
        val = tk.StringVar()

        def show(v=None):
            v = var.get()
            if fmt:
                val.set(fmt(v))
            else:
                val.set(("%d" % int(v)) if cast is int else ("%.2f" % v))

        s = tk.Scale(box, from_=lo, to=hi, resolution=res, orient="horizontal",
                     variable=var, showvalue=0, length=150, bg=C_BG,
                     highlightthickness=0, bd=0, troughcolor="#DDE1E7",
                     activebackground=C_ACCENT, sliderrelief="flat",
                     command=lambda v: (show(), self._set(key, cast(float(v)))),
                     width=8)
        s.pack(side="left")
        lb = tk.Label(box, textvariable=val, bg=C_BG, fg=C_TEXT, font=SHOW_FONT,
                      width=6, anchor="w")
        lb.pack(side="left", padx=(6, 0))
        if suffix:
            tk.Label(box, text=suffix, bg=C_BG, fg=C_HINT,
                     font=SMALL_FONT).pack(side="left")
        show()
        return s

    def _combo(self, parent, r, c, key, values, width=16, cast=str, labels=None):
        cur = str(self.store.get(key))
        disp = cur
        if labels and cur in values:
            disp = labels[values.index(cur)]
        var = tk.StringVar(value=disp)
        box = tk.Frame(parent, bg=C_BG)
        box.grid(row=r, column=c, sticky="w", pady=9)
        shown = labels if (labels and len(labels) == len(values)) else values
        cb = ttk.Combobox(box, textvariable=var, values=shown, width=width,
                          state="readonly", font=SHOW_FONT)
        cb.pack(side="left")

        def commit(_e=None):
            raw = var.get()
            v = values[shown.index(raw)] if raw in shown else raw
            self._set(key, cast(v), retheme=(key in RETHEME_KEYS))
        cb.bind("<<ComboboxSelected>>", commit)
        return cb

    def _switch_row(self, parent, r, c, key, on_change=None):
        var = tk.BooleanVar(value=bool(self.store.get(key)))
        box = tk.Frame(parent, bg=C_BG)
        box.grid(row=r, column=c, sticky="w", pady=9)

        def cmd():
            v = bool(var.get())
            if on_change:
                on_change(v)
            else:
                self._set(key, v)

        tg = Toggle(box, var, command=cmd)
        tg.pack(side="left")
        return tg

    def _color(self, parent, r, c, key):
        box = tk.Frame(parent, bg=C_BG)
        box.grid(row=r, column=c, sticky="w", pady=9)
        swatch = tk.Label(box, bg=self.store.get(key), width=3, height=1,
                          bd=1, relief="solid", cursor="hand2")
        swatch.configure(borderwidth=0, highlightthickness=1,
                         highlightbackground="#C9CDD4")
        swatch.pack(side="left", ipady=4)
        txt = tk.Label(box, text=str(self.store.get(key)), bg=C_BG, fg=C_HINT,
                       font=("Consolas", 9), width=10, anchor="w")
        txt.pack(side="left", padx=(8, 0))

        def pick(_e=None):
            cur = self.store.get(key)
            rgb, hexv = colorchooser.askcolor(color=cur, parent=self.win,
                                              title="选择颜色")
            if not hexv:
                return
            hexv = hexv.upper()
            swatch.configure(bg=hexv)
            txt.configure(text=hexv)
            self._set(key, hexv)

        for w in (swatch, txt):
            w.bind("<Button-1>", pick)
        return swatch

    def _hotkey(self, parent, r, c, key):
        box = tk.Frame(parent, bg=C_BG)
        box.grid(row=r, column=c, sticky="w", pady=9)
        lb = tk.Label(box, text=str(self.store.get(key)).upper(), bg="#F2F4F7",
                      fg=C_TEXT, font=("Consolas", 9), padx=12, pady=5,
                      cursor="hand2")
        lb.pack(side="left")

        def rec(_e=None):
            def done(combo):
                lb.configure(text=combo.upper())
                self._set(key, combo)
                self.app.refresh_hotkeys()
            Recorder(self.win, done, str(self.store.get(key)))

        lb.bind("<Button-1>", rec)
        return lb

    def _key_list(self, parent, r, c, key):
        """一个动作可绑多个键位（截图里是 3 个槽）。"""
        box = tk.Frame(parent, bg=C_BG)
        box.grid(row=r, column=c, sticky="w", pady=9)
        cur = list(self.store.get(key) or [])

        def redraw():
            for ch in box.winfo_children():
                ch.destroy()
            vals = cur + [""] * (3 - len(cur))
            for i, k in enumerate(vals[:3]):
                lb = tk.Label(box, text=k or "—", bg="#F2F4F7", fg=C_TEXT,
                              font=("Consolas", 9), width=9, pady=5, cursor="hand2")
                lb.pack(side="left", padx=(0, 6))

                def rec(_e=None, idx=i):
                    def done(combo):
                        keys = [x for x in cur if x]
                        while len(keys) <= idx:
                            keys.append("")
                        keys[idx] = combo
                        self.store.set(key, [x for x in keys if x])
                        self.store.save()
                        self.app.refresh_bindings()
                        cur[:] = self.store.get(key) or []
                        redraw()
                    Recorder(self.win, done, k)
                lb.bind("<Button-1>", rec)
                lb.bind("<Button-3>", lambda e, idx=i: _clear(idx))

        def _clear(idx):
            keys = [x for x in cur]
            if idx < len(keys):
                keys.pop(idx)
            self.store.set(key, keys)
            self.store.save()
            self.app.refresh_bindings()
            cur[:] = keys
            redraw()

        redraw()
        return box

    # ------------------------------------------------------------ 外观页

    def _tab_look(self):
        f = self._grid()
        self._section(f, 0, "整体风格")

        r = 1
        self._label(f, r, 0, "快速预设")
        box = tk.Frame(f, bg=C_BG)
        box.grid(row=r, column=1, columnspan=3, sticky="w", pady=9)
        for name, preset in BG_PRESETS:
            b = tk.Label(box, text=name, bg="#F2F4F7", fg=C_TEXT, font=SMALL_FONT,
                         padx=10, pady=5, cursor="hand2")

            def apply_preset(_e=None, p=preset):
                for k, v in p.items():
                    self.store.set(k, v)
                self.store.save()
                self.app.apply_settings()
                self._rebuild()

            b.pack(side="left", padx=(0, 8))
            b.bind("<Button-1>", apply_preset)

        r += 1
        self._label(f, r, 0, "文字颜色", "越淡越不显眼，但看久了费眼。白底页建议 #3A3A3A～#5A5A5A。")
        self._color(f, r, 1, "fg")
        self._label(f, r, 2, "背景颜色", "仅「带底」模式生效；「只留文字」模式下背景被抠掉。")
        self._color(f, r, 3, "bg")

        r += 1
        self._label(f, r, 0, "背景透明度", "整窗透明度。越低越淡，文字也会跟着变淡。")
        self._slider(f, r, 1, "bg_alpha", 0.3, 1.0, 0.01, fmt=lambda v: "%d%%" % (v * 100))
        self._label(f, r, 2, "背景模式")
        self._combo(f, r, 3, "bg_mode", ["transparent", "solid"], width=14)

        self._section(f, r + 1, "排版")

        r += 2
        self._label(f, r, 0, "字体大小")
        self._slider(f, r, 1, "font_size", 9, 28, 1, suffix="px", cast=int)
        self._label(f, r, 2, "字体")
        fams = sorted(set(tkfont.families()))
        prefer = ["Microsoft YaHei", "微软雅黑", "SimSun", "宋体", "Consolas"]
        fams = [x for x in prefer if x in fams] + \
               [x for x in fams if x not in prefer and not x.startswith("@")]
        self._combo(f, r, 3, "font_family", fams, width=20)

        r += 1
        self._label(f, r, 0, "行间距", "倍数。1.4 适合小窗，1.8 以上更松散但占地方。")
        self._slider(f, r, 1, "line_spacing", 1.0, 3.0, 0.1, suffix="倍")
        self._label(f, r, 2, "段间距")
        self._slider(f, r, 3, "para_spacing", 0, 24, 1, suffix="px", cast=int)

        r += 1
        self._label(f, r, 0, "保留格式", "关掉后会把空行、段落合并，一段一段压紧，同样的窗口能放更多字。")
        self._switch_row(f, r, 1, "keep_format")
        self._label(f, r, 2, "展示百分比", "右下角显示全书进度百分比，小字灰色。")
        self._switch_row(f, r, 3, "show_percent")

        self._section(f, r + 1, "窗口")

        r += 2
        self._label(f, r, 0, "窗口宽度")
        self._entry(f, r, 1, "width", suffix="px", cast=int, lo=200, hi=4000)
        self._label(f, r, 2, "窗口高度")
        self._entry(f, r, 3, "height", suffix="px", cast=int, lo=40, hi=1200)

        r += 1
        self._label(f, r, 0, "顶部进度条", "窗口最上方一条 2px 细线，表示读到全书哪个位置。")
        self._switch_row(f, r, 1, "show_bar")
        self._label(f, r, 2, "每次翻页行数", "0 = 按窗口高度自适应（翻一整屏）。")
        self._entry(f, r, 3, "page_lines", suffix="行", cast=int, lo=0, hi=60)

    def _section(self, parent, r, text):
        box = tk.Frame(parent, bg=C_BG)
        box.grid(row=r, column=0, columnspan=4, sticky="w", pady=(14, 2))
        tk.Frame(box, bg=C_ACCENT, width=3, height=14).pack(side="left", padx=(0, 8))
        tk.Label(box, text=text, bg=C_BG, fg=C_TEXT,
                 font=("Microsoft YaHei", 10, "bold")).pack(side="left")

    # ------------------------------------------------------------ 功能页

    def _tab_func(self):
        f = self._grid()
        self._section(f, 0, "显隐")

        r = 1
        self._label(f, r, 0, "移入延迟", "鼠标移到热区后，等多久才显示。0 = 立刻。")
        self._entry(f, r, 1, "enter_delay", suffix="ms", cast=int, lo=0, hi=3000)
        self._label(f, r, 2, "移出延迟", "鼠标离开后等多久隐藏。0 = 立刻消失（默认），移回来又会显示。")
        self._entry(f, r, 3, "leave_delay", suffix="ms", cast=int, lo=0, hi=5000)

        r += 1
        self._label(f, r, 0, "右下角保留", "鼠标停在屏幕右下角这块区域时不隐藏，方便操作任务栏。0 = 关。")
        self._slider(f, r, 1, "hide_keep_br", 0, 30, 1, suffix="%", cast=int)
        self._label(f, r, 2, "切走自动隐藏", "切换到别的程序时自动收起。开着更稳，但看代码时可能误收。")
        self._switch_row(f, r, 3, "hide_on_blur")

        self._section(f, r + 1, "翻页")

        r += 2
        self._label(f, r, 0, "鼠标翻页", "开：单击正文向下翻页。")
        self._switch_row(f, r, 1, "mouse_page")
        self._label(f, r, 2, "单击钉住",
                    "开：单击正文就把窗口钉住（移开不消失，右下角会显示「已钉住」）。"
                    "默认关——太容易误触，一碰就再也不隐藏。也可以用 Ctrl+P。")
        self._switch_row(f, r, 3, "click_pin")

        r += 1
        self._label(f, r, 0, "窗口可移动", "关掉后窗口锁定，拖不动，避免手滑移走。")
        self._switch_row(f, r, 1, "window_movable")

        r += 1
        self._label(f, r, 0, "点击穿透",
                    "开着时：窗口照常显示，但鼠标可以穿过它去点下面的 Excel。"
                    "开着就点不到窗口本身了，要用穿透热键切回来。")
        self._switch_row(f, r, 1, "click_through",
                         on_change=lambda v: self.app.toggle_through(v))

        r += 1
        self._label(f, r, 0, "滚轮延迟", "两次滚轮翻页的最小间隔，太小会一滚飞好几页。")
        self._entry(f, r, 1, "wheel_delay", suffix="ms", cast=int, lo=0, hi=2000)
        self._label(f, r, 2, "滚轮方向反转")
        self._switch_row(f, r, 3, "wheel_invert")

        r += 1
        self._label(f, r, 0, "自动翻页", "每隔多久自动往下翻一行。0 = 关。")
        self._entry(f, r, 1, "auto_page", suffix="ms", cast=int, lo=0, hi=20000)
        self._label(f, r, 2, "连续翻页", "读到章末自动进下一章。")
        self._switch_row(f, r, 3, "continuous")

        self._section(f, r + 1, "文本")

        r += 2
        self._label(f, r, 0, "简繁转换", "源文是繁体就选「繁转简」。")
        self._combo(f, r, 1, "zh_convert", ["none", "t2s", "s2t"],
                    width=18, labels=["不转换", "繁转简", "简转繁"])

        self._section(f, r + 1, "快捷键（窗口显示时生效，可各绑 3 个键）")

        r += 2
        for i, (key, label) in enumerate((
                ("page_up", "上一页"), ("page_down", "下一页"),
                ("chapter_up", "上一章"), ("chapter_down", "下一章"))):
            col = (i % 2) * 2
            row = r + i // 2
            self._label(f, row, col, label)
            self._key_list(f, row, col + 1, key)

    # ------------------------------------------------------------ 其他页

    def _tab_misc(self):
        f = self._grid()
        self._section(f, 0, "全局热键（窗口隐藏时也生效）")

        r = 1
        self._label(f, r, 0, "老板键", "一键清屏：立刻隐藏并清空文字，再按恢复。")
        self._hotkey(f, r, 1, "boss_key")
        self._label(f, r, 2, "唤出键", "不用把鼠标移到角落，直接按出来。")
        self._hotkey(f, r, 3, "reveal_key")

        r += 1
        self._label(f, r, 0, "穿透键", "切换鼠标点击穿透。穿透状态下窗口收不到点击，只能靠这个键切回。")
        self._hotkey(f, r, 1, "through_key")
        self._label(f, r, 2, "隐藏任务栏图标", "开启后不在任务栏和 Alt-Tab 里出现，只能用热键唤出。")
        self._switch_row(f, r, 3, "hide_taskbar")

        self._section(f, r + 1, "唤出热区")

        r += 2
        self._label(f, r, 0, "角落位置")
        self._combo(f, r, 1, "hotzone_corner",
                    ["top-right", "top-left", "bottom-right"], width=16,
                    labels=["屏幕右上角", "屏幕左上角", "屏幕右下角"])
        self._label(f, r, 2, "热区宽度")
        self._entry(f, r, 3, "hotzone_w", suffix="px", cast=int, lo=20, hi=1200)

        r += 1
        self._label(f, r, 0, "热区高度")
        self._entry(f, r, 1, "hotzone_h", suffix="px", cast=int, lo=4, hi=200)

        self._section(f, r + 1, "数据")

        r += 2
        self._label(f, r, 0, "阅读记录")
        box = tk.Frame(f, bg=C_BG)
        box.grid(row=r, column=1, columnspan=3, sticky="w", pady=9)
        for text, fn in (("清除全部阅读进度", self._clear_progress),
                         ("打开数据目录", self._open_data),
                         ("重置当前配置", self._reset)):
            b = tk.Label(box, text=text, bg="#F2F4F7", fg=C_TEXT, font=SMALL_FONT,
                         padx=12, pady=6, cursor="hand2")
            b.pack(side="left", padx=(0, 8))
            b.bind("<Button-1>", lambda e, f2=fn: f2())

        r += 1
        self._label(f, r, 0, "说明")
        tk.Label(f, text="所有数据只存在本机 data 目录，程序不联网、不写注册表。\n"
                         "拷贝整个文件夹到别的电脑，书架和进度一起带走。",
                 bg=C_BG, fg=C_HINT, font=SMALL_FONT, justify="left", anchor="w"
                 ).grid(row=r, column=1, columnspan=3, sticky="w", pady=9)

    # ------------------------------------------------------------ 动作

    def _profile_menu(self, _e=None):
        m = tk.Menu(self.win, tearoff=0, font=SHOW_FONT)
        for name in self.store.profiles:
            m.add_command(
                label=("● " if name == self.store.active else "   ") + name,
                command=lambda n=name: self._use_profile(n))
        m.add_separator()
        m.add_command(label="新建配置…", command=self._new_profile)
        m.add_command(label="重命名当前配置…", command=self._rename_profile)
        m.add_command(label="删除当前配置", command=self._del_profile)
        m.tk_popup(self.prof_btn.winfo_rootx(), self.prof_btn.winfo_rooty() + 26)

    def _use_profile(self, name):
        self.store.switch_profile(name)
        self.prof_btn.configure(text="≡  %s ▾" % name)
        self.app.apply_settings()
        self._rebuild()

    def _new_profile(self):
        name = simpledialog.askstring("新建配置", "配置名称（例如：看文档 / 看代码）：",
                                      parent=self.win)
        if name and self.store.add_profile(name):
            self._use_profile(name)

    def _rename_profile(self):
        old = self.store.active
        name = simpledialog.askstring("重命名", "新名称：", initialvalue=old,
                                      parent=self.win)
        if name and self.store.rename_profile(old, name):
            self._use_profile(name)

    def _del_profile(self):
        if len(self.store.profiles) <= 1:
            messagebox.showinfo("不能删除", "至少保留一套配置。", parent=self.win)
            return
        if messagebox.askyesno("删除配置", "删除「%s」？" % self.store.active,
                               parent=self.win):
            self.store.del_profile(self.store.active)
            self._use_profile(self.store.active)

    def _reset(self):
        if messagebox.askyesno("恢复默认", "当前配置「%s」的所有参数恢复默认？"
                               % self.store.active, parent=self.win):
            self.store.reset_profile()
            self.app.apply_settings()
            self._rebuild()

    def _clear_progress(self):
        if messagebox.askyesno("清除进度", "清空所有书的阅读进度？（书架和书本身不删）",
                               parent=self.win):
            self.store.clear_recent()

    def _open_data(self):
        import os
        import subprocess
        d = os.path.dirname(self.store.path)
        try:
            subprocess.Popen(["explorer", d])
        except Exception:
            messagebox.showinfo("数据目录", d, parent=self.win)

    def _boss_help(self):
        messagebox.showinfo(
            "老板键怎么用",
            "1. 在「其他」页点老板键右侧的按钮，直接按下你要的组合键。\n"
            "2. 建议 Ctrl+Alt+Q 这类不常用的组合，避免和 VS Code、浏览器冲突。\n"
            "3. 老板键在任何程序里都生效，窗口隐藏时也能按。\n"
            "4. 按下后会隐藏窗口并清空文字（不是透明，是真的没有了），\n"
            "   再按一次就会恢复。\n\n"
            "注意：本程序不提供反截屏、进程伪装之类的功能。\n"
            "定时截屏抓到的是屏幕像素，任何窗口都躲不掉。",
            parent=self.win)

    def _close(self):
        self.store.save()
        self.app.apply_settings()
        try:
            self.win.destroy()
        except Exception:
            pass


RETHEME_KEYS = ("bg_mode", "fg", "bg", "bg_alpha", "font_size",
                "font_family", "line_spacing", "para_spacing",
                "keep_format", "show_percent", "show_bar", "zh_convert")

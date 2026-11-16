# -*- coding: utf-8 -*-
"""书架窗口：卡片网格、添加、排序、重命名、移除。"""
import os
import re
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import core
import wapi

C_BG = "#FFFFFF"
C_PANEL = "#F7F8FA"
C_LINE = "#E9EBEF"
C_TEXT = "#2B2F36"
C_SUB = "#737A85"
C_ACCENT = "#2F6FE4"
C_HINT = "#A2A8B3"

# 封面配色（浅色系，按书名散列取，比统一浅蓝好认）
COVERS = [
    ("#E3EDFD", "#2F62C4"), ("#DFF3E6", "#26744A"), ("#FBE2DF", "#A8332A"),
    ("#FDF0DC", "#9A6114"), ("#F0E3FD", "#5F35A0"), ("#D9F1F5", "#186A79"),
    ("#FCE0EF", "#9C2C66"), ("#E7EAF0", "#414A59"), ("#EAF5D8", "#4E6B18"),
    ("#FDEEE0", "#A6501A"), ("#DDEBF7", "#1F5B96"), ("#F3E9DC", "#7A5A2E"),
]

CARD_W, CARD_H = 128, 158


def cover_of(title, fp=""):
    """按指纹（更分散）取封面色；没有指纹时退回书名。"""
    seed = fp or title or "x"
    h = 7
    for ch in seed:
        h = (h * 131 + ord(ch)) & 0xFFFFFF
    return COVERS[h % len(COVERS)]


class Bookshelf(object):

    def __init__(self, app):
        self.app = app
        self.store = app.store
        self.sort = tk.StringVar(value="最近阅读")
        self.win = tk.Toplevel(app.root)
        self.win.title("我的书架")
        self.win.configure(bg=C_BG)
        sw, sh = app.root.winfo_screenwidth(), app.root.winfo_screenheight()
        w, h = min(1020, sw - 80), min(660, sh - 100)
        self.win.geometry("%dx%d+%d+%d" % (w, h, max(20, (sw - w) // 2),
                                           max(20, (sh - h) // 3)))
        self.win.minsize(720, 480)
        self.win.attributes("-topmost", True)
        self._build()
        self.refresh()

    # ------------------------------------------------------------ 骨架

    def _build(self):
        w = self.win

        # 顶栏
        bar = tk.Frame(w, bg=C_BG, height=56)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        tk.Label(bar, text="▤", bg=C_BG, fg=C_ACCENT,
                 font=("Microsoft YaHei", 15)).pack(side="left", padx=(20, 6))
        tk.Label(bar, text="我的书架", bg=C_BG, fg=C_TEXT,
                 font=("Microsoft YaHei", 13, "bold")).pack(side="left")

        self.topmost = tk.BooleanVar(value=True)
        self._mini_btn(bar, "⚙ 设置", lambda: self.app.open_settings(), right=True)
        self._mini_btn(bar, "隐藏阅读窗", lambda: self.app.hide(), right=True)
        self._mini_btn(bar, "开启窗口移动", self._toggle_move, right=True)
        self._mini_btn(bar, "退出程序", lambda: self.app.quit(), right=True)

        tk.Frame(w, bg=C_LINE, height=1).pack(fill="x")

        # 工具栏
        tb = tk.Frame(w, bg=C_BG, height=48)
        tb.pack(fill="x")
        tb.pack_propagate(False)

        tk.Label(tb, text="⇅", bg=C_BG, fg=C_SUB,
                 font=("Microsoft YaHei", 10)).pack(side="left", padx=(20, 4))
        cb = ttk.Combobox(tb, textvariable=self.sort, state="readonly", width=10,
                          values=["最近阅读", "最早添加", "按书名"], font=("Microsoft YaHei", 9))
        cb.pack(side="left", pady=10)
        cb.bind("<<ComboboxSelected>>", lambda e: self.refresh())

        self.count_lbl = tk.Label(tb, text="", bg=C_BG, fg=C_HINT,
                                  font=("Microsoft YaHei", 9))
        self.count_lbl.pack(side="left", padx=14)

        # 右起：添加 → 网址 → 继续
        self._mini_btn(tb, "＋ 添加", self.add_book, right=True, primary=True)
        self._mini_btn(tb, "＋ 网址", self.add_url, right=True)
        self.continue_btn = self._mini_btn(tb, "▶ 继续阅读", self._continue,
                                           right=True)

        tk.Frame(w, bg=C_LINE, height=1).pack(fill="x")

        # 滚动区
        wrap = tk.Frame(w, bg=C_BG)
        wrap.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(wrap, bg=C_BG, bd=0, highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.canvas.yview)
        sb.pack(side="right", fill="y")
        self.canvas.configure(yscrollcommand=sb.set)

        self.inner = tk.Frame(self.canvas, bg=C_BG)
        self.window_id = self.canvas.create_window((0, 0), window=self.inner,
                                                   anchor="nw")
        self.inner.bind("<Configure>", self._on_inner)
        self.canvas.bind("<Configure>", self._on_canvas)
        self.canvas.bind_all("<MouseWheel>", self._wheel, add="+")

        # 底部
        tk.Frame(w, bg=C_LINE, height=1).pack(fill="x")
        foot = tk.Frame(w, bg=C_BG, height=40)
        foot.pack(fill="x")
        foot.pack_propagate(False)
        tk.Label(foot, text="双击打开 · 右键改名或移除", bg=C_BG, fg=C_HINT,
                 font=("Microsoft YaHei", 9)).pack(side="left", padx=20)
        tk.Label(foot, text="数据只存本机，不联网", bg=C_BG, fg=C_HINT,
                 font=("Microsoft YaHei", 9)).pack(side="right", padx=20)

        # 书架是第一屏，这些键不用先点阅读窗也能用
        w.bind("<Control-o>", lambda e: self.add_book())
        w.bind("<Control-u>", lambda e: self.add_url())
        w.bind("<Control-comma>", lambda e: self.app.open_settings())
        w.bind("<Control-b>", lambda e: self.refresh())

    def _mini_btn(self, parent, text, cmd, right=False, primary=False):
        b = tk.Label(parent, text=text, bg=C_ACCENT if primary else "#F2F4F7",
                     fg="#FFFFFF" if primary else C_TEXT,
                     font=("Microsoft YaHei", 9), padx=14, pady=6, cursor="hand2")
        b.pack(side="right" if right else "left", padx=(0, 14), pady=10)
        b.bind("<Button-1>", lambda e: cmd())
        return b

    def _toggle_move(self):
        """切换阅读窗是否可拖动（对应参考产品的「开启窗口移动」）。"""
        cur = bool(self.store.get("window_movable"))
        self.store.set("window_movable", not cur)
        self.store.save()
        self.app.apply_settings(render=False)
        self.app.flash("阅读窗移动：%s" % ("开 · 可拖动" if not cur else "关 · 已锁定"))

    def _on_inner(self, _e=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas(self, e):
        self.canvas.itemconfigure(self.window_id, width=e.width)
        self._layout()

    def _wheel(self, e):
        try:
            if self.win.winfo_ismapped():
                self.canvas.yview_scroll(-1 if e.delta > 0 else 1, "units")
        except Exception:
            pass

    # ------------------------------------------------------------ 卡片

    def refresh(self):
        for ch in self.inner.winfo_children():
            ch.destroy()
        items = list(self.store.shelf())
        mode = self.sort.get()
        if mode == "按书名":
            items.sort(key=lambda x: x.get("title") or "")
        elif mode == "最早添加":
            items.sort(key=lambda x: x.get("added") or 0)
        else:
            books = self.store.data.get("books") or {}
            items.sort(key=lambda x: -((books.get(x.get("fp")) or {}).get("updated") or 0))

        self._cards = []
        for it in items:
            self._cards.append(("book", it))
        self._cards.append(("add", None))
        self.count_lbl.configure(text="共 %d 本" % len(items))
        self._layout()

    def _layout(self):
        if not hasattr(self, "_cards"):
            return
        for ch in self.inner.winfo_children():
            ch.destroy()
        try:
            width = self.canvas.winfo_width() or 980
        except Exception:
            width = 980
        pad = 18
        cols = max(2, int((width - pad * 2 + pad) / (CARD_W + pad)))
        for i, (kind, item) in enumerate(self._cards):
            r, c = divmod(i, cols)
            cell = tk.Frame(self.inner, bg=C_BG)
            cell.grid(row=r, column=c, padx=pad // 2, pady=(16 if r == 0 else 10, 4),
                      sticky="nw")
            if kind == "add":
                self._add_card(cell)
            else:
                self._book_card(cell, item)

    def _book_card(self, parent, item):
        title = item.get("title") or "未命名"
        fp = item.get("fp")
        rec = self.store.get_progress(fp) or {}
        bg, fg = cover_of(title, fp)

        cover = tk.Frame(parent, width=CARD_W, height=CARD_H, bg=bg,
                         cursor="hand2", highlightthickness=0)
        cover.pack()
        cover.pack_propagate(False)

        # 右上角类型角标
        k = item.get("kind") or "txt"
        kind = {"web": "url", "epub": "epub"}.get(k, "txt")
        color = {"url": "#3B82F6", "epub": "#10A37F"}.get(kind, "#3B82F6")
        badge = tk.Label(cover, text=kind, bg=color, fg="#FFFFFF",
                         font=("Consolas", 7), padx=4, pady=0)
        badge.place(relx=1.0, y=6, anchor="ne", x=-6)

        # 左上角「上次」：启动后第一眼就知道该点哪本
        last_mark = None
        if fp and fp == self.store.data.get("last"):
            last_mark = tk.Label(cover, text="上次", bg="#FFFFFF", fg=fg,
                                 font=("Microsoft YaHei", 7), padx=4, pady=0)
            last_mark.place(x=6, y=6, anchor="nw")

        # 书名（竖排效果：每行一两个字，靠窄宽度自动换行）
        name = tk.Label(cover, text=title, bg=bg, fg=fg, wraplength=CARD_W - 24,
                        font=("Microsoft YaHei", 10), justify="center")
        name.place(relx=0.5, rely=0.5, anchor="center")

        prog = rec.get("percent")
        if prog is not None:
            tk.Label(cover, text="%.1f%%" % (float(prog) * 100), bg=bg, fg=fg,
                     font=("Consolas", 7)).place(relx=0.5, rely=1.0,
                                                 anchor="s", y=-8)

        lbl = tk.Label(parent, text=title, bg=C_BG, fg=C_TEXT,
                       font=("Microsoft YaHei", 9), wraplength=CARD_W,
                       justify="center")
        lbl.pack(pady=(6, 0))

        sub = "%d 章 · %s" % (item.get("chapters") or 0,
                              core.nice_size(item.get("chars") or 0))
        tk.Label(parent, text=sub, bg=C_BG, fg=C_HINT,
                 font=("Microsoft YaHei", 8)).pack()

        for wgt in (cover, name, lbl, badge):
            wgt.bind("<Double-Button-1>", lambda e, it=item: self.open(it))
            wgt.bind("<Button-3>", lambda e, it=item: self._menu(e, it))
        if last_mark is not None:
            last_mark.bind("<Double-Button-1>", lambda e, it=item: self.open(it))

    def _add_card(self, parent):
        box = tk.Frame(parent, width=CARD_W, height=CARD_H, bg=C_BG,
                       highlightthickness=1, highlightbackground="#D5D9E0",
                       cursor="hand2")
        box.pack()
        box.pack_propagate(False)
        tk.Label(box, text="＋", bg=C_BG, fg=C_ACCENT,
                 font=("Microsoft YaHei", 22)).place(relx=0.5, rely=0.36,
                                                     anchor="center")
        tk.Label(box, text="添加本地书籍", bg=C_BG, fg=C_SUB,
                 font=("Microsoft YaHei", 9)).place(relx=0.5, rely=0.62,
                                                    anchor="center")
        tk.Label(parent, text="txt / epub", bg=C_BG, fg=C_HINT,
                 font=("Microsoft YaHei", 8)).pack(pady=(6, 0))
        box.bind("<Button-1>", lambda e: self.add_book())
        for ch in box.winfo_children():
            ch.bind("<Button-1>", lambda e: self.add_book())

    # ------------------------------------------------------------ 动作

    def add_book(self):
        paths = filedialog.askopenfilenames(
            parent=self.win, title="选择书籍（可多选）",
            filetypes=[("电子书", "*.txt *.epub"),
                       ("文本文件", "*.txt"), ("EPUB 电子书", "*.epub"),
                       ("所有文件", "*.*")])
        if not paths:
            return
        ok = 0
        last = None
        for p in paths:
            try:
                b = core.Book(p).load()
            except Exception:
                continue
            if not b.text.strip():
                continue
            self.store.shelf_add(b.fingerprint, b.name, b.path, b.kind,
                                 len(b.chapters), b.total_chars)
            ok += 1
            last = b
        self.refresh()
        if last and ok == 1:
            self.app.load_book(last.path)
        elif ok:
            self.app.flash("已加入 %d 本" % ok)

    def add_url(self):
        url = simpledialog.askstring(
            "导入网址", "粘贴小说目录页的网址：\n（有很多章节链接的那个页面）",
            parent=self.win)
        if not url:
            return
        url = url.strip()
        if not re.match(r'^https?://', url, re.I):
            url = "https://" + url
        self.app._load_web_async(url)

    def _continue(self):
        """接着上次读到的地方——省掉「在书架里找哪本没读完」。"""
        if not self.app.resume_last():
            messagebox.showinfo("还没有阅读记录",
                                "双击一本书就开始读了。", parent=self.win)

    def open(self, item):
        # 由 app 负责收起书架 + 切到阅读态
        self.app.open_shelf_item(item)

    def _menu(self, e, item):
        m = tk.Menu(self.win, tearoff=0, font=("Microsoft YaHei", 9))
        m.add_command(label="打开", command=lambda: self.open(item))
        m.add_command(label="重命名…", command=lambda: self._rename(item))
        m.add_separator()
        m.add_command(label="从书架移除", command=lambda: self._remove(item))
        m.tk_popup(e.x_root, e.y_root)

    def _rename(self, item):
        name = simpledialog.askstring("重命名", "书名：",
                                      initialvalue=item.get("title"),
                                      parent=self.win)
        if name:
            self.store.shelf_rename(item.get("fp"), name)
            self.refresh()

    def _remove(self, item):
        if messagebox.askyesno("移除", "从书架移除「%s」？\n（本地文件本身不会删）"
                               % item.get("title"), parent=self.win):
            self.store.shelf_remove(item.get("fp"))
            self.refresh()

# -*- coding: utf-8 -*-
"""解析层：TXT 编码识别、章节识别、书籍模型、多套配置与书架存储。

只依赖标准库，Python 3.7+。
"""
import os
import re
import copy
import json
import time
import hashlib

import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import epub as epub_mod

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(APP_DIR, "data")
STATE_FILE = os.path.join(DATA_DIR, "state.json")
CACHE_DIR = os.path.join(DATA_DIR, "cache")

MAX_CHAPTER_TITLE = 42


# ---------------------------------------------------------------- 编码识别

def _cjk_score(text):
    """给解码结果打分：汉字与中文标点加分，替换符与控制字符重罚。"""
    sample = text[:6000]
    if not sample:
        return -100.0
    good = 0
    bad = 0
    total = 0
    for ch in sample:
        o = ord(ch)
        total += 1
        if 0x4E00 <= o <= 0x9FFF:          # 汉字
            good += 2
        elif 0x3000 <= o <= 0x303F:        # 中文标点
            good += 1
        elif 0xFF01 <= o <= 0xFF5E:        # 全角字符
            good += 1
        elif o == 0xFFFD:                  # 替换符
            bad += 6
        elif o < 32 and ch not in "\n\r\t":
            bad += 6
        elif 0xE000 <= o <= 0xF8FF:        # 私用区，通常是错码
            bad += 4
    return (good - bad) / float(total)


def decode_text(raw):
    """返回 (text, encoding)。"""
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig", "replace"), "utf-8-sig"
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16", "replace"), "utf-16"

    best = None
    for enc in ("utf-8", "gb18030", "big5"):
        try:
            s = raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
        score = _cjk_score(s)
        if best is None or score > best[2]:
            best = (s, enc, score)
    if best is None:
        return raw.decode("utf-8", "replace"), "utf-8/lossy"
    return best[0], best[1]


def read_text_file(path):
    with open(path, "rb") as f:
        raw = f.read()
    return decode_text(raw)


# ---------------------------------------------------------------- 章节识别

_RULES = [
    # 第一章 / 第1章 / 第一百二十三回
    re.compile(r"^\s*第\s*[0-9０-９零〇一二三四五六七八九十百千万两]+\s*[章节回話话節节卷幕].*$"),
    # 正文 第一章
    re.compile(r"^\s*正文\s*第\s*[0-9０-９零〇一二三四五六七八九十百千万两]+\s*[章节回].*$"),
    # Chapter 12 / CHAPTER XII
    re.compile(r"^\s*(?:Chapter|CHAPTER|chapter)\s*[0-9IVXLCDMivxlcdm]+\b.*$"),
    # 卷三 / 卷二 少年
    re.compile(r"^\s*[卷部篇]\s*[0-9０-９零〇一二三四五六七八九十百]+.*$"),
    # 【第一章】xxx / （1）xxx
    re.compile(r"^\s*[（(【\[]\s*[0-9０-９零一二三四五六七八九十百千]+\s*[）)】\]]\s*\S.{0,30}$"),
    # 1. xxx / 001、xxx / 一、xxx
    re.compile(r"^\s*(?:[0-9]{1,4}|[一二三四五六七八九十百]{1,4})\s*[、.．]\s*\S.{0,30}$"),
]

_END_PUNCT = "。！？，；：、…\"'」』"


def _looks_like_title(line):
    s = line.strip()
    if not s or len(s) > MAX_CHAPTER_TITLE:
        return False
    if s[-1] in _END_PUNCT:
        return False
    # 太长且含句内标点，多半是正文
    if len(s) > 18 and (("，" in s) or ("。" in s)):
        return False
    for rgx in _RULES:
        if rgx.match(s):
            return True
    return False


def split_chapters(text):
    """返回 [(title, body), ...]。识别失败时按 3000 字切分。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")

    marks = []  # (line_index, title)
    for i, line in enumerate(lines):
        if _looks_like_title(line):
            # 前后需要有一定空间，避免正文里的对话被误判
            prev_blank = (i == 0) or (not lines[i - 1].strip())
            next_blank = (i == len(lines) - 1) or (not lines[i + 1].strip())
            if prev_blank or next_blank:
                marks.append((i, line.strip()))

    # 章节数太少 → 降级切分
    if len(marks) < 3:
        return _fallback_split(text)

    chapters = []
    # 第一个标记之前的内容作为"序"
    if marks[0][0] > 0:
        head = "\n".join(lines[: marks[0][0]]).strip()
        if len(head) > 200:
            chapters.append(("开始", head))

    for idx, (li, title) in enumerate(marks):
        end = marks[idx + 1][0] if idx + 1 < len(marks) else len(lines)
        body = "\n".join(lines[li + 1: end]).strip()
        chapters.append((_clean_title(title), body))

    return chapters


def _clean_title(t):
    t = re.sub(r"\s+", " ", t).strip()
    return t[:MAX_CHAPTER_TITLE]


def _fallback_split(text, size=3000):
    out = []
    n = len(text)
    i = 0
    idx = 1
    while i < n:
        end = min(i + size, n)
        if end < n:
            # 尽量在段落边界断
            cut = text.rfind("\n", i + size // 2, end)
            if cut > i:
                end = cut
        out.append(("第 %d 段（自动分页）" % idx, text[i:end].strip()))
        i = end
        idx += 1
    return out or [("全书", text)]


# ---------------------------------------------------------------- 书籍模型

class Book(object):
    def __init__(self, path):
        self.path = path
        self.name = os.path.splitext(os.path.basename(path))[0]
        self.text = ""
        self.encoding = ""
        self.chapters = []      # [(title, body)]
        self.total_chars = 0
        self.kind = "epub" if epub_mod.is_epub(path) else "txt"
        self.is_remote = False

    def load(self):
        if self.kind == "epub":
            title, chapters, enc = epub_mod.read_epub(self.path)
            if title:
                self.name = title
            self.chapters = chapters
            self.encoding = enc
            self.text = "\n".join(b for _, b in chapters)
        else:
            self.text, self.encoding = read_text_file(self.path)
            self.chapters = split_chapters(self.text)

        # 只有一章且特别长（EPUB 常把整本书塞进一个 XHTML）→ 自动分页
        if len(self.chapters) == 1 and len(self.chapters[0][1]) > 12000:
            parts = _fallback_split(self.chapters[0][1])
            head = self.chapters[0][0]
            self.chapters = [("%s · %s" % (head[:22], t[:14]) if i else t, b)
                             for i, (t, b) in enumerate(parts)]

        self.total_chars = sum(len(b) for _, b in self.chapters)
        return self

    @property
    def fingerprint(self):
        """内容指纹：取路径 + 大小 + 头部哈希，避免大文件全量计算。"""
        h = hashlib.md5()
        try:
            size = os.path.getsize(self.path)
            with open(self.path, "rb") as f:
                head = f.read(65536)
            h.update(head)
            h.update(str(size).encode("ascii"))
        except OSError:
            h.update(self.path.encode("utf-8", "ignore"))
        return h.hexdigest()[:24]


# ---------------------------------------------------------------- 默认参数
# 说明：bg_mode=transparent 时用颜色键抠掉背景，屏幕上只剩文字；
#       bg_mode=solid 时整窗 alpha 半透明 + 实色底（近似 rgba 效果）。

DEFAULT_KEYS = {
    "page_up": ["Up"],
    "page_down": ["Down"],
    "chapter_up": ["Left"],
    "chapter_down": ["Right"],
    "toc": ["Control-g"],
    "auto_page": ["Control-r"],
    "boss_local": ["Escape"],
}

DEFAULTS = {
    # ---- 外观（默认对齐「浅淡」：白底页上极淡的底 + 淡灰字）
    "font_family": "Microsoft YaHei",
    "font_size": 13,
    "fg": "#3A3A3A",
    "bg": "#F4F5F7",
    "bg_alpha": 0.82,
    "bg_mode": "solid",           # solid 带底半透明 | transparent 只留文字
    "line_spacing": 1.45,         # 行间距倍数
    "para_spacing": 6,            # 段间距 px
    "keep_format": True,          # 保留段落缩进与空行
    "show_percent": True,         # 右下角显示进度百分比
    "show_bar": False,            # 顶部进度条
    "page_lines": 0,              # 0=按窗口高度自适应；>0=每次翻 n 行
    "width": 560,
    "height": 132,
    "pos_x": None,
    "pos_y": None,
    # ---- 行为
    "window_movable": True,       # 允许拖动窗口
    "enter_delay": 120,           # 移入多久后显示
    "leave_delay": 0,             # 移出多久后隐藏（0=立刻）
    "hide_keep_br": 0,            # 鼠标在屏幕右下角该百分比区域时不隐藏
    "mouse_page": False,          # 单击翻页（关掉则单击不做事）
    "click_pin": False,           # 单击正文钉住（默认关：太容易误触，一碰就再也不隐藏）
    "wheel_delay": 160,           # 滚轮两次翻页最小间隔 ms
    "wheel_lines": 1,             # 滚轮一次滚几行（窗口很矮，默认 1 行，别再大了）
    "wheel_invert": False,        # 滚轮方向反转
    "auto_page": 0,               # 自动翻页间隔 ms，0=关
    "continuous": True,           # 章末自动进入下一章
    "zh_convert": "none",         # none | t2s | s2t
    "hide_on_blur": False,        # 切走应用自动隐藏
    "click_through": False,       # 鼠标点击穿透（能操作下层软件）
    "hide_taskbar": True,         # 不在任务栏/Alt-Tab 出现
    # ---- 热键与热区
    "keys": DEFAULT_KEYS,
    "boss_key": "ctrl+alt+q",
    "reveal_key": "ctrl+alt+z",
    "through_key": "ctrl+alt+e",
    "hotzone_w": 220,
    "hotzone_h": 16,
    "hotzone_corner": "top-right",
}


def _defaults():
    return copy.deepcopy(DEFAULTS)


class Store(object):
    """v2 结构：多套配置 profiles + 书架 shelf + 每本书进度 books。"""

    VERSION = 2

    def __init__(self, path=STATE_FILE):
        self.path = path
        self.data = {
            "version": self.VERSION,
            "active": "配置1",
            "profiles": {"配置1": _defaults()},
            "books": {},
            "shelf": [],
            "last": None,
        }
        self.load()

    # ---- 读写
    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, ValueError):
            return
        if not isinstance(raw, dict):
            return

        self.data["books"] = raw.get("books") or {}
        self.data["last"] = raw.get("last")
        self.data["shelf"] = raw.get("shelf") or []

        profiles = raw.get("profiles")
        if isinstance(profiles, dict) and profiles:
            # v2
            fixed = {}
            for name, prof in profiles.items():
                base = _defaults()
                if isinstance(prof, dict):
                    base.update(prof)
                # keys 是嵌套字典，缺失项补齐
                k = _defaults()["keys"]
                k.update(base.get("keys") or {})
                base["keys"] = k
                fixed[name] = base
            self.data["profiles"] = fixed
            self.data["active"] = raw.get("active") or list(fixed)[0]
        else:
            # v1 迁移：旧 settings 平铺 → 配置1
            base = _defaults()
            base.update(raw.get("settings") or {})
            k = _defaults()["keys"]
            k.update(base.get("keys") or {})
            base["keys"] = k
            self.data["profiles"] = {"配置1": base}
            self.data["active"] = "配置1"

        if self.data["active"] not in self.data["profiles"]:
            self.data["active"] = list(self.data["profiles"])[0]

        self._migrate_leave_delay()

    def _migrate_leave_delay(self):
        """v2.3：移出延迟改成「立刻隐藏」，把老配置里的 700ms 默认值一起改掉。

        只动「等于旧默认 700」的那一档——用户自己调过的值保留。
        """
        if self.data.get("mig_leave_fast"):
            return
        for prof in self.data["profiles"].values():
            try:
                if int(prof.get("leave_delay", 0)) == 700:
                    prof["leave_delay"] = 0
            except (TypeError, ValueError):
                pass
        self.data["mig_leave_fast"] = True
        self.save()

    def save(self):
        try:
            if not os.path.isdir(DATA_DIR):
                os.makedirs(DATA_DIR)
            tmp = self.path + ".tmp"
            self.data["version"] = self.VERSION
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            if os.path.exists(self.path):
                os.remove(self.path)
            os.rename(tmp, self.path)
        except OSError:
            pass

    # ---- 配置（多套）
    @property
    def profiles(self):
        return self.data["profiles"]

    @property
    def active(self):
        return self.data["active"]

    @property
    def prof(self):
        name = self.data["active"]
        profs = self.data["profiles"]
        if name not in profs:
            profs[name] = _defaults()
        p = profs[name]
        for k, v in DEFAULTS.items():
            if k not in p:
                p[k] = copy.deepcopy(v)
        return p

    def switch_profile(self, name):
        if name in self.data["profiles"]:
            self.data["active"] = name
            self.save()
            return True
        return False

    def add_profile(self, name):
        name = (name or "").strip()
        if not name or name in self.data["profiles"]:
            return False
        self.data["profiles"][name] = copy.deepcopy(self.prof)
        self.data["active"] = name
        self.save()
        return True

    def del_profile(self, name):
        if len(self.data["profiles"]) <= 1:
            return False
        if name in self.data["profiles"]:
            del self.data["profiles"][name]
            if self.data["active"] == name:
                self.data["active"] = list(self.data["profiles"])[0]
            self.save()
            return True
        return False

    def rename_profile(self, old, new):
        new = (new or "").strip()
        if not new or new in self.data["profiles"] or old not in self.data["profiles"]:
            return False
        self.data["profiles"][new] = self.data["profiles"].pop(old)
        if self.data["active"] == old:
            self.data["active"] = new
        self.save()
        return True

    # ---- 设置项
    def get(self, key, default=None):
        return self.prof.get(key, DEFAULTS.get(key, default))

    def set(self, key, value):
        self.prof[key] = value

    def reset_profile(self):
        self.data["profiles"][self.data["active"]] = _defaults()
        self.save()

    # ---- 进度
    def get_progress(self, fp):
        return self.data["books"].get(fp) if fp else None

    def set_progress(self, fp, title, path, chapter, top_index, percent):
        self.data["books"][fp] = {
            "title": title,
            "path": path,
            "chapter": int(chapter),
            "top": top_index,
            "percent": round(float(percent), 4),
            "updated": int(time.time()),
        }
        self.data["last"] = fp
        self.save()

    # ---- 书架
    def shelf(self):
        return self.data["shelf"]

    def shelf_find(self, fp):
        for it in self.data["shelf"]:
            if it.get("fp") == fp:
                return it
        return None

    def shelf_add(self, fp, title, path, kind="txt", chapters=0, chars=0,
                  rename=False):
        cur = self.shelf_find(fp)
        if cur:
            # 已存在：默认保留用户改过的书名，只更新统计
            if rename and title:
                cur["title"] = title
            cur["chapters"] = chapters or cur.get("chapters", 0)
            cur["chars"] = chars or cur.get("chars", 0)
            return cur
        item = {
            "fp": fp,
            "title": title or "未命名",
            "path": path,
            "kind": kind,
            "chapters": int(chapters or 0),
            "chars": int(chars or 0),
            "added": time.time(),
        }
        self.data["shelf"].append(item)
        self.save()
        return item

    def shelf_remove(self, fp):
        self.data["shelf"] = [x for x in self.data["shelf"] if x.get("fp") != fp]
        self.data["books"].pop(fp, None)
        if self.data["last"] == fp:
            self.data["last"] = None
        self.save()

    def shelf_rename(self, fp, title):
        it = self.shelf_find(fp)
        if it:
            it["title"] = title
            self.save()
            return True
        return False

    def clear_recent(self):
        self.data["books"] = {}
        self.data["last"] = None
        self.save()


# ---------------------------------------------------------------- 排版

_INDENT_RE = re.compile(r"^[\u3000\s]{2,}")


def format_body(text, keep_format=True, indent=True):
    """把章节正文整理成适合窄窗口阅读的样子。

    keep_format=False 时去掉空行、合并段落；indent=True 时给段落加两个全角空格。
    """
    if not text:
        return ""
    lines = [ln.rstrip() for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    if keep_format:
        out = [ln for ln in lines if ln.strip()]
        if indent:
            out = ["\u3000\u3000" + _INDENT_RE.sub("", ln) for ln in out]
        return "\n".join(out)

    paras = []
    buf = ""
    for ln in lines:
        if not ln.strip():
            if buf:
                paras.append(buf)
                buf = ""
            continue
        if buf and (buf[-1] in "。！？…」』\"'" ):
            paras.append(buf)
            buf = ln.strip()
        else:
            buf += ln.strip()
    if buf:
        paras.append(buf)
    if indent:
        paras = ["\u3000\u3000" + p for p in paras]
    return "\n".join(paras)


def nice_size(n):
    """字数 → 万字/千字描述。"""
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "-"
    if n >= 10000:
        return "%.1f 万字" % (n / 10000.0)
    return "%d 字" % n


def fmt_time(ts):
    try:
        return time.strftime("%m-%d %H:%M", time.localtime(float(ts)))
    except (TypeError, ValueError):
        return "-"

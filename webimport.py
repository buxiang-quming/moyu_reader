# -*- coding: utf-8 -*-
"""网址导入：抓目录、抓正文、磁盘缓存。纯标准库实现。

边界：只提供"把网页正文提取到阅读窗口"的通用解析能力。
不内置书源、不预置站点规则、不批量下载。内容来源与版权由使用者自行负责。
"""
import os
import re
import gzip
import ssl
import html as htmlmod
import hashlib
import urllib.request
import urllib.parse
import urllib.error

import core

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
TIMEOUT = 15

LINK_RE = re.compile(r'<a\s[^>]*?href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.I | re.S)
TAG_RE = re.compile(r'<[^>]+>')

CONTENT_PATTERNS = [
    r'<div[^>]+id=["\'](?:content|chaptercontent|content1|booktext|chapter_content|nr1|htmlContent)["\'][^>]*>(.*?)</div>',
    r'<div[^>]+class=["\'][^"\']*(?:content|chapter-content|article-content|read-content|txt)[^"\']*["\'][^>]*>(.*?)</div>',
    r'<article[^>]*>(.*?)</article>',
    r'<section[^>]+class=["\'][^"\']*(?:content|read)[^"\']*["\'][^>]*>(.*?)</section>',
]

TOC_CONTAINERS = [
    r'<div[^>]+id=["\'](?:list|chapterlist|chapter-list|play_0|catalog|mulu)["\'][^>]*>(.*?)</div>',
    r'<div[^>]+class=["\'][^"\']*(?:chapterlist|chapter-list|listmain|catalog|mulu)["\'][^"\']*["\'][^>]*>(.*?)</div>',
    r'<dl[^>]*>(.*?)</dl>',
    r'<ul[^>]+class=["\'][^"\']*(?:chapter|list|catalog)[^"\']*["\'][^>]*>(.*?)</ul>',
]

_AD_WORDS = (
    "笔趣阁", "请记住本站", "最新网址", "手机版阅读", "本章未完", "点击下一页",
    "章节错误", "求收藏", "求推荐", "加入书签", "投推荐票", "https://", "http://",
    "www.", ".com", ".net", ".cc", "全文阅读", "无弹窗",
)


# ------------------------------------------------------------------ HTTP

def _charset_from(raw, ctype):
    m = re.search(r'charset=([\w\-]+)', ctype or "", re.I)
    if m:
        cs = m.group(1).lower()
        return "gb18030" if cs in ("gb2312", "gbk") else cs
    head = raw[:4096]
    m = re.search(rb'charset=["\']?([\w\-]+)', head, re.I)
    if m:
        cs = m.group(1).decode("ascii", "ignore").lower()
        return "gb18030" if cs in ("gb2312", "gbk") else cs
    return None


def fetch(url, timeout=TIMEOUT):
    """返回解码后的 HTML 文本。"""
    if not re.match(r'^https?://', url, re.I):
        url = "https://" + url
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Encoding": "gzip",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.URLError as e:
        if "CERTIFICATE" not in str(e).upper():
            raise
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        resp = urllib.request.urlopen(req, timeout=timeout, context=ctx)

    with resp:
        raw = resp.read()
        if (resp.headers.get("Content-Encoding") or "").lower() == "gzip":
            try:
                raw = gzip.decompress(raw)
            except OSError:
                pass
        cs = _charset_from(raw, resp.headers.get("Content-Type"))

    if cs:
        try:
            return raw.decode(cs, "replace")
        except LookupError:
            pass
    text, _enc = core.decode_text(raw)
    return text


# ------------------------------------------------------------------ 清洗

def to_text(fragment):
    fragment = re.sub(r'<(script|style|iframe)[^>]*>.*?</\1>', "", fragment,
                      flags=re.I | re.S)
    fragment = re.sub(r'<br\s*/?>', "\n", fragment, flags=re.I)
    fragment = re.sub(r'</(p|div|h\d|li|dd|tr)>', "\n\n", fragment, flags=re.I)
    fragment = TAG_RE.sub("", fragment)
    fragment = htmlmod.unescape(fragment)
    fragment = fragment.replace("\u3000", "  ").replace("\xa0", " ")

    lines = []
    for line in fragment.split("\n"):
        s = line.strip()
        if not s:
            lines.append("")
            continue
        low = s.lower()
        if len(s) < 60 and any(w.lower() in low for w in _AD_WORDS):
            continue
        lines.append(s)

    text = "\n".join(lines)
    text = re.sub(r'\n{3,}', "\n\n", text)
    return text.strip()


def _inline_text(fragment):
    s = TAG_RE.sub("", fragment)
    s = htmlmod.unescape(s)
    return re.sub(r'\s+', " ", s).strip()


# ------------------------------------------------------------------ 解析

def parse_toc(html_text, base_url):
    """返回 (书名, [(章节名, 绝对URL), ...])。"""
    title = ""
    m = re.search(r'<h1[^>]*>(.*?)</h1>', html_text, re.I | re.S)
    if not m:
        m = re.search(r'<title[^>]*>(.*?)</title>', html_text, re.I | re.S)
    if m:
        title = _inline_text(m.group(1))
        title = re.split(r'[_\-|—]', title)[0].strip()

    links = []
    for pat in TOC_CONTAINERS:
        for cm in re.finditer(pat, html_text, re.I | re.S):
            block = cm.group(1)
            if len(block) < 50:
                continue
            for lm in LINK_RE.finditer(block):
                href, label = lm.group(1), _inline_text(lm.group(2))
                if _valid_link(href, label):
                    links.append((label, urllib.parse.urljoin(base_url, href)))
        if len(links) >= 3:
            break

    if len(links) < 3:
        links = []
        for lm in LINK_RE.finditer(html_text):
            href, label = lm.group(1), _inline_text(lm.group(2))
            if _valid_link(href, label):
                links.append((label, urllib.parse.urljoin(base_url, href)))

    seen = set()
    out = []
    for label, url in links:
        if url in seen:
            continue
        seen.add(url)
        out.append((label, url))
    return title, out


def _valid_link(href, label):
    if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
        return False
    if not label or len(label) < 2 or len(label) > 40:
        return False
    return core._looks_like_title(label)


def parse_content(html_text):
    """返回正文纯文本。"""
    best = ""
    for pat in CONTENT_PATTERNS:
        for cm in re.finditer(pat, html_text, re.I | re.S):
            t = to_text(cm.group(1))
            if len(t) > len(best):
                best = t
        if len(best) > 400:
            return best

    # 兜底：把 body 按块切开，取块内文字最多的那个
    body = re.search(r'<body[^>]*>(.*?)</body>', html_text, re.I | re.S)
    scope = body.group(1) if body else html_text
    scope = re.sub(r'<(script|style|nav|header|footer)[^>]*>.*?</\1>', "",
                   scope, flags=re.I | re.S)
    for cm in re.finditer(r'<div[^>]*>(.*?)</div>', scope, re.I | re.S):
        t = to_text(cm.group(1))
        if len(t) > len(best):
            best = t
    return best


# ------------------------------------------------------------------ 书籍对象

class WebBook(core.Book):
    """远程书：目录一次抓取，正文按章按需抓取并缓存。"""

    is_remote = True

    def __init__(self, toc_url):
        core.Book.__init__(self, toc_url)
        self.toc_url = toc_url
        self.name = toc_url
        self.encoding = "web"
        self.is_remote = True

    def load(self):
        html_text = fetch(self.toc_url)
        title, links = parse_toc(html_text, self.toc_url)
        if len(links) < 2:
            raise ValueError(
                "这个页面上没找到目录。\n\n"
                "建议直接粘贴「目录页」网址（列表里有很多章节链接的那个页面），"
                "而不是某一章的正文页。")
        self.name = title or "网页小说"
        self.chapters = links
        self.total_chars = 0
        return self

    @property
    def fingerprint(self):
        h = hashlib.md5()
        h.update(("web:" + self.toc_url).encode("utf-8"))
        return h.hexdigest()[:24]

    def fetch_chapter(self, i):
        name, url = self.chapters[i]
        cache_dir = os.path.join(core.DATA_DIR, "cache")
        key = hashlib.md5(url.encode("utf-8")).hexdigest()
        cache = os.path.join(cache_dir, key + ".txt")
        if os.path.exists(cache):
            try:
                with open(cache, "r", encoding="utf-8") as f:
                    return f.read()
            except OSError:
                pass

        body = parse_content(fetch(url))
        if not body or len(body) < 30:
            body = "（这一章没提到正文。可能是页面结构变了，或者站点要验证码。）"

        text = "【%s】\n\n%s" % (name, body)
        try:
            if not os.path.isdir(cache_dir):
                os.makedirs(cache_dir)
            with open(cache, "w", encoding="utf-8") as f:
                f.write(text)
        except OSError:
            pass
        return text

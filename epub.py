# -*- coding: utf-8 -*-
"""EPUB 解析（纯标准库）。

结构：zip → META-INF/container.xml → *.opf（manifest + spine）→ 若干 XHTML。

策略
1. 按 spine 顺序遍历 XHTML，这是出版社认定的阅读顺序，比按文件名排序可靠。
2. 单个 XHTML 就是一章（绝大多数 EPUB 都这样）；若一个文件里出现 2 个以上
   标题标签，按标题再切成多章。
3. 章节标题优先取文件内 <h1>~<h3>；没有标题时回落到 NCX / EPUB3 nav 的目录名；
   再没有就用「第 N 节」。
4. 图片、CSS、字体一律跳过——阅读窗只显示文字。
"""

import os
import re
import posixpath
import zipfile
import urllib.parse
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

MAX_MEMBER = 8 * 1024 * 1024      # 单个 XHTML 最大读取量，防 zip 炸弹
MAX_TITLE_LEN = 42

_HTML_TYPES = ("application/xhtml+xml", "text/html", "application/xml", "")
_SKIP_TAGS = {"script", "style", "head", "svg", "math"}
_HEAD_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")
_BLOCK_TAGS = {
    "p", "div", "br", "li", "ul", "ol", "tr", "td", "th", "table", "tbody",
    "section", "article", "blockquote", "pre", "dd", "dt", "dl", "figure",
    "figcaption", "header", "footer", "nav", "main", "aside", "body", "html",
    "hr", "address", "center",
}

# 两个汉字之间的换行/空格要去掉，否则排版会出现「中 文」这种缝
_CJK = "\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
_CJK_GAP = re.compile(r"(?<=[%s])[ \t\u3000]+(?=[%s])" % (_CJK, _CJK))


# ---------------------------------------------------------------- XML 辅助

def _local(tag):
    """去掉命名空间，返回小写本地名。"""
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1].lower()


def _text_of(el):
    return re.sub(r"\s+", " ", "".join(el.itertext())).strip()


def _norm_join(base_dir, href):
    """把 opf 里的相对 href 变成 zip 内的绝对路径（去锚点、解 URL 转义）。"""
    if not href:
        return ""
    href = urllib.parse.unquote(href.split("#")[0])
    if href.startswith("/"):
        return posixpath.normpath(href.lstrip("/"))
    return posixpath.normpath(posixpath.join(base_dir, href))


# ---------------------------------------------------------------- OPF

def _find_opf(z):
    try:
        raw = z.read("META-INF/container.xml")
    except KeyError:
        # 容器文件缺失时兜底：扫第一个 .opf
        for n in z.namelist():
            if n.lower().endswith(".opf"):
                return n
        return None
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return None
    for el in root.iter():
        if _local(el.tag) == "rootfile":
            p = el.get("full-path")
            if p:
                return p
    return None


def _parse_opf(z, opf_path):
    """返回 (书名, [(zip内路径, media-type, properties), ...] 按 spine 顺序)。"""
    try:
        root = ET.fromstring(z.read(opf_path))
    except (KeyError, ET.ParseError):
        return "", []

    base = posixpath.dirname(opf_path)
    title = ""
    manifest = {}
    spine_ids = []

    for el in root.iter():
        n = _local(el.tag)
        if n == "title":
            if not title:
                title = _text_of(el)
        elif n == "item":
            iid = el.get("id")
            if iid:
                manifest[iid] = (el.get("href") or "",
                                 (el.get("media-type") or "").lower(),
                                 (el.get("properties") or "").lower())
        elif n == "itemref":
            ref = el.get("idref")
            if ref:
                spine_ids.append(ref)

    order = []
    for ref in spine_ids:
        item = manifest.get(ref)
        if not item:
            continue
        href, mtype, props = item
        if mtype not in _HTML_TYPES:
            continue
        if "nav" in props:                 # 纯目录页，没有正文
            continue
        p = _norm_join(base, href)
        if p:
            order.append((p, mtype, props))
    return title, order


# ---------------------------------------------------------------- 目录名（NCX / nav）

def _nav_names(z, opf_path):
    """从 toc.ncx 或 EPUB3 nav 里取「文件路径 → 章节名」。

    只做文件名级映射（锚点忽略），够用来给没有标题标签的 XHTML 起名。
    """
    try:
        root = ET.fromstring(z.read(opf_path))
    except (KeyError, ET.ParseError):
        return {}

    base = posixpath.dirname(opf_path)
    target = None
    for el in root.iter():
        if _local(el.tag) == "item":
            props = (el.get("properties") or "").lower()
            if "nav" in props:
                target = _norm_join(base, el.get("href") or "")
                break

    names = {}
    if target:
        # EPUB3 nav：<nav epub:type="toc"> 里的 <a href>文本</a>
        names.update(_nav_from_html(z, target, base))
    if names:
        return names

    # EPUB2：toc.ncx
    ncx = None
    try:
        for el in root.iter():
            if _local(el.tag) == "item":
                href = (el.get("href") or "").lower()
                if href.endswith(".ncx"):
                    ncx = _norm_join(base, el.get("href"))
                    break
    except Exception:
        ncx = None
    if not ncx:
        for n in z.namelist():
            if n.lower().endswith(".ncx"):
                ncx = n
                break
    if not ncx:
        return {}

    try:
        nroot = ET.fromstring(z.read(ncx))
    except (KeyError, ET.ParseError):
        return {}
    nbase = posixpath.dirname(ncx)
    for point in nroot.iter():
        if _local(point.tag) != "navpoint":
            continue
        label = ""
        src = ""
        for ch in point:
            n = _local(ch.tag)
            if n == "navlabel":
                for t in ch.iter():
                    if _local(t.tag) == "text":
                        label = _text_of(t)
                        break
            elif n == "content":
                src = ch.get("src") or ""
        if label and src:
            p = _norm_join(nbase, src)
            if p and p not in names:
                names[p] = label
    return names


def _nav_from_html(z, nav_path, base):
    class _Nav(HTMLParser):
        def __init__(self):
            HTMLParser.__init__(self, convert_charrefs=True)
            self.links = []
            self._href = None
            self._buf = []

        def handle_starttag(self, tag, attrs):
            if tag.lower() == "a":
                d = dict(attrs)
                href = d.get("href")
                if href:
                    self._href = href
                    self._buf = []

        def handle_data(self, data):
            if self._href is not None:
                self._buf.append(data)

        def handle_endtag(self, tag):
            if tag.lower() == "a" and self._href is not None:
                txt = re.sub(r"\s+", " ", "".join(self._buf)).strip()
                if txt:
                    self.links.append((self._href, txt))
                self._href = None
                self._buf = []

    try:
        raw = z.read(nav_path)
    except KeyError:
        return {}
    try:
        txt = raw.decode("utf-8")
    except UnicodeDecodeError:
        txt = raw.decode("gb18030", "replace")
    p = _Nav()
    try:
        p.feed(txt)
    except Exception:
        return {}
    out = {}
    nbase = posixpath.dirname(nav_path)
    for href, label in p.links:
        key = _norm_join(nbase, href)
        if key and key not in out:
            out[key] = label
    return out


# ---------------------------------------------------------------- HTML 取文

class _BlockParser(HTMLParser):
    """把 XHTML 拆成 [(标签, 文字)]，块级元素之间断开。"""

    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.blocks = []
        self._skip = 0
        self._buf = []
        self._tag = None

    def handle_starttag(self, tag, attrs):
        t = tag.lower()
        if t in _SKIP_TAGS:
            self._skip += 1
            return
        if t in _HEAD_TAGS:
            self._flush()
            self._tag = t
        elif t in _BLOCK_TAGS:
            self._flush()
            if self._tag is None:
                self._tag = "p"

    def handle_startendtag(self, tag, attrs):
        if tag.lower() == "br":
            self._flush()

    def handle_endtag(self, tag):
        t = tag.lower()
        if t in _SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
            return
        if t in _BLOCK_TAGS or t in _HEAD_TAGS:
            self._flush()

    def handle_data(self, data):
        if self._skip:
            return
        if self._tag is None:
            self._tag = "p"
        self._buf.append(data)

    def _flush(self):
        raw = "".join(self._buf)
        self._buf = []
        tag = self._tag or "p"
        self._tag = None
        if not raw.strip():
            return
        txt = re.sub(r"\s+", " ", raw).strip()
        if tag in _HEAD_TAGS:
            # 标题保留分隔空格（「第一章　起风」不能粘成「第一章起风」），
            # 只把连续空白压成一个普通空格
            txt = txt.replace("\u3000", " ")
            txt = re.sub(r" {2,}", " ", txt).strip()
        else:
            txt = _CJK_GAP.sub("", txt)
        if txt:
            self.blocks.append((tag, txt))

    def close(self):
        try:
            HTMLParser.close(self)
        except Exception:
            pass
        self._flush()


def _decode(raw):
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    for enc in ("utf-8", "gb18030", "big5"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", "replace")


def _blocks_of(z, path):
    try:
        info = z.getinfo(path)
    except KeyError:
        return []
    if info.file_size > MAX_MEMBER:
        return []
    try:
        raw = z.read(path)
    except (KeyError, OSError, zipfile.BadZipFile):
        return []

    doc = _decode(raw)
    # 去掉 XML 声明和 doctype，HTMLParser 对它们不友好但也不致命
    doc = re.sub(r"<\?xml[^>]*\?>", "", doc)
    doc = re.sub(r"<!DOCTYPE[^>]*>", "", doc, flags=re.I)

    p = _BlockParser()
    try:
        p.feed(doc)
        p.close()
    except Exception:
        return p.blocks
    return p.blocks


def _join(blocks):
    return "\n".join(t for _, t in blocks).strip()


def _split_blocks(blocks, fallback_title):
    """把一个 XHTML 的块序列切成 [(标题, 正文)]。"""
    heads = []
    for i, (tag, txt) in enumerate(blocks):
        if tag in _HEAD_TAGS and len(txt) <= 60:
            heads.append((i, txt))

    if len(heads) >= 2:
        out = []
        pre = _join(blocks[:heads[0][0]])
        for idx, (i, txt) in enumerate(heads):
            end = heads[idx + 1][0] if idx + 1 < len(heads) else len(blocks)
            body = _join(blocks[i + 1:end])
            if idx == 0 and pre:
                body = (pre + "\n" + body).strip()
            if body:
                out.append((txt, body))
        if out:
            return out

    # 单章：整篇一块
    title = fallback_title
    body = ""
    if heads and heads[0][0] == 0:
        title = heads[0][1]
        body = _join(blocks[1:])
    else:
        body = _join(blocks)
    if not body:
        return []
    return [(title or "正文", body)]


def _clean_title(t):
    t = re.sub(r"\s+", " ", t or "").strip()
    t = t.strip("　 ·-—|")
    return t[:MAX_TITLE_LEN]


# ---------------------------------------------------------------- 对外接口

def read_epub(path):
    """返回 (书名, [(章节名, 正文), ...], 编码标识)。失败抛异常。"""
    if not zipfile.is_zipfile(path):
        raise ValueError("不是有效的 EPUB 文件（zip 结构损坏）")

    with zipfile.ZipFile(path) as z:
        opf = _find_opf(z)
        if not opf:
            raise ValueError("EPUB 缺少 container.xml 或 opf，无法定位正文")

        title, order = _parse_opf(z, opf)
        names = _nav_names(z, opf)

        chapters = []
        for idx, (p, _mtype, _props) in enumerate(order):
            blocks = _blocks_of(z, p)
            if not blocks:
                continue
            label = names.get(p) or ""
            # 兜底名按「已收章节数 + 1」编号。用 idx（spine 下标）会导致
            # 第一章叫「第 2 节」——封面之类被跳过时序号就错位了。
            for ctitle, body in _split_blocks(blocks, label or "第 %d 节" % (len(chapters) + 1)):
                ctitle = _clean_title(ctitle) or "第 %d 节" % (len(chapters) + 1)
                chapters.append((ctitle, body))

    if not chapters:
        raise ValueError("这本 EPUB 里没有可提取的文字（可能是纯图片扫描版）")

    if not title:
        title = os.path.splitext(os.path.basename(path))[0]
    return _clean_title(title), chapters, "epub"


def is_epub(path):
    return os.path.splitext(path)[1].lower() == ".epub"

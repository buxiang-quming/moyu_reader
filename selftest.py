# -*- coding: utf-8 -*-
"""离线自检：不启动 GUI，验证解析层、配置层、书架层。"""
import os
import sys
import json
import tempfile

import core
import zhconv

FAIL = []


def ck(name, cond, extra=""):
    if cond:
        print("  PASS  %s" % name)
    else:
        print("  FAIL  %s  %s" % (name, extra))
        FAIL.append(name)


print("== 1. 简繁转换 ==")
ck("配对标定无错位", len(zhconv.S2T) > 500 and len(zhconv.T2S) > 500,
   "s2t=%d t2s=%d" % (len(zhconv.S2T), len(zhconv.T2S)))
s = zhconv.convert("这个国家的大门被打开了", "s2t")
ck("简转繁", s == "這個國家的大門被打開了", s)
t = zhconv.convert("這個國家的大門被打開了", "t2s")
ck("繁转简", t == "这个国家的大门被打开了", t)
ck("简繁往返稳定", zhconv.convert(t, "s2t") == s)
ck("识别繁体文本", zhconv.has_traditional("這是一個測試，我們都會開門說話") is True)
ck("识别简体文本", zhconv.has_traditional("这是一个测试，我们都会开门说话") is False)

print("== 2. 编码识别 ==")
gbk = "第一章 出发\n\n他把门推开，外面在下雨。\n" * 40
raw = gbk.encode("gbk")
txt, enc = core.decode_text(raw)
ck("GBK 解码", enc in ("gb18030", "gbk") and "门推开" in txt, enc)
raw = gbk.encode("utf-8")
txt, enc = core.decode_text(raw)
ck("UTF-8 解码", enc == "utf-8" and "门推开" in txt, enc)
raw = b"\xef\xbb\xbf" + gbk.encode("utf-8")
txt, enc = core.decode_text(raw)
ck("UTF-8 BOM", enc == "utf-8-sig" and txt.startswith("第一章"), enc)

print("== 3. 章节识别 ==")
book = "\n".join(["第一章 开始", "正文一" * 30, "", "第二章 转折",
                  "正文二" * 30, "", "第三章 结局", "正文三" * 30]) 
chs = core.split_chapters(book)
ck("识别 3 章", len(chs) == 3, len(chs))
ck("章名正确", chs[1][0] == "第二章 转折", chs[1][0])
noch = "随便一段话。" * 800
chs2 = core.split_chapters(noch)
ck("无目录时降级分页", len(chs2) >= 2 and "自动分页" in chs2[0][0], chs2[0][0])

print("== 4. 正文排版 ==")
body = "第一行内容。\n第二行内容。\n\n第三段内容。"
f1 = core.format_body(body, keep_format=True, indent=True)
ck("保留格式：每行一段 + 缩进", f1.count("\n") == 2 and f1.startswith("\u3000\u3000"), repr(f1[:20]))
# txt 里一段被硬换行拆开：行尾无标点时应合并
wrap = "他推开门，看见雨还在\n下，于是又退了回去。"
f2 = core.format_body(wrap, keep_format=False, indent=True)
ck("硬换行被合并成一段", f2.count("\n") == 0 and "雨还在下" in f2, repr(f2))
f3 = core.format_body(wrap, keep_format=True, indent=True)
ck("保留格式时不合并", f3.count("\n") == 1, repr(f3))

print("== 5. 配置与书架 ==")
tmp = os.path.join(tempfile.gettempdir(), "moyu_test_state.json")
if os.path.exists(tmp):
    os.remove(tmp)
st = core.Store(tmp)
ck("默认只有一套配置", len(st.profiles) == 1 and st.active == "配置1", list(st.profiles))
st.set("font_size", 22)
st.save()
st2 = core.Store(tmp)
ck("配置持久化", int(st2.get("font_size")) == 22, st2.get("font_size"))
st2.add_profile("看代码")
ck("新建配置继承当前值", int(st2.get("font_size")) == 22)
st2.set("font_size", 12)
st2.switch_profile("配置1")
ck("配置切换隔离", int(st2.get("font_size")) == 22, st2.get("font_size"))
ck("keys 默认值完整", len(st2.get("keys")) >= 7, st2.get("keys"))

st2.shelf_add("fp1", "测试书A", "C:/a.txt", "txt", 10, 20000)
st2.shelf_add("fp2", "测试书B", "C:/b.txt", "txt", 20, 60000)
ck("书架添加 2 本", len(st2.shelf()) == 2)
st2.shelf_add("fp1", "测试书A2", "C:/a.txt", "txt", 10, 20000)
ck("重复添加不重复", len(st2.shelf()) == 2)
ck("重复添加保留用户改的书名", st2.shelf_find("fp1")["title"] == "测试书A",
   st2.shelf_find("fp1")["title"])
st2.shelf_add("fp1", "测试书A2", "C:/a.txt", "txt", 10, 20000, rename=True)
ck("rename=True 时更新书名", st2.shelf_find("fp1")["title"] == "测试书A2")
st2.set_progress("fp1", "测试书A2", "C:/a.txt", 3, "2.0", 0.0012)
st2.shelf_remove("fp2")
ck("移除同时清进度", len(st2.shelf()) == 1 and st2.get_progress("fp2") is None)

print("== 6. 旧版数据迁移 ==")
old = {"version": 1, "settings": {"font_size": 18, "alpha": 0.7},
       "books": {"x": {"title": "旧书", "path": "C:/old.txt", "chapter": 1,
                       "top": "1.0", "percent": 0.1}},
       "last": "x"}
tmp2 = os.path.join(tempfile.gettempdir(), "moyu_test_old.json")
with open(tmp2, "w", encoding="utf-8") as f:
    json.dump(old, f, ensure_ascii=False)
st3 = core.Store(tmp2)
ck("v1 迁移成配置1", st3.active == "配置1" and int(st3.get("font_size")) == 18,
   st3.get("font_size"))
ck("v1 进度保留", (st3.get_progress("x") or {}).get("title") == "旧书")

print("== 7. 热键转换 ==")
import app as appmod
ck("ctrl+alt+q", appmod.to_tk_seq("ctrl+alt+q") == "<Control-Alt-q>",
   appmod.to_tk_seq("ctrl+alt+q"))
ck("ArrowUp", appmod.to_tk_seq("Up") == "<Up>", appmod.to_tk_seq("Up"))
ck("Control-g", appmod.to_tk_seq("Control-g") == "<Control-g>",
   appmod.to_tk_seq("Control-g"))
ck("空值安全", appmod.to_tk_seq("") is None)

print("== 8. EPUB 解析 ==")
import epub
import _gen_epub

ep = os.path.join(tempfile.gettempdir(), "moyu_test.epub")
_gen_epub.build(ep)
etitle, echs, eenc = epub.read_epub(ep)
ck("读书名", etitle == "测试书 第一卷", repr(etitle))
ck("按 spine 顺序（ch1→ch3→ch2）",
   [t for t, _ in echs] == ["第一章 起风", "第二章 落雨", "第二章 续", "第三章 天晴"],
   repr([t for t, _ in echs]))
ck("单文件多标题自动切章", len(echs) == 4, len(echs))
ck("标题保留分隔空格", " " in echs[0][0], repr(echs[0][0]))
ck("实体与正文正常", "第一个字是「夜」" in echs[0][1], echs[0][1][:20])
ck("<script> 已剔除", "var x" not in "".join(b for _, b in echs))
ck("<style> 已剔除", "text-indent" not in "".join(b for _, b in echs))
ck("图片条目已跳过", all(b.strip() for _, b in echs))

eb = core.Book(ep).load()
ck("Book 识别 epub", eb.kind == "epub" and eb.encoding == "epub", eb.kind)
ck("书名取自 dc:title", eb.name == "测试书 第一卷", repr(eb.name))
ck("字数统计", eb.total_chars == sum(len(b) for _, b in echs), eb.total_chars)

bad = os.path.join(tempfile.gettempdir(), "moyu_bad.epub")
with open(bad, "wb") as f:
    f.write(b"not a zip at all")
try:
    epub.read_epub(bad)
    ck("非 zip 文件报错", False, "没有抛异常")
except ValueError as e:
    ck("非 zip 文件报错", "EPUB" in str(e), str(e))

for p in (tmp, tmp2, ep, bad):
    try:
        os.remove(p)
    except OSError:
        pass

print("")
if FAIL:
    print("失败 %d 项：%s" % (len(FAIL), ", ".join(FAIL)))
    sys.exit(1)
print("全部通过")

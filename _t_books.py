# -*- coding: utf-8 -*-
"""真实书籍功能验收：书架上每本书都真打开一遍。

检查：能打开、章节数合理、章名可读、正文能渲染、跳章正确、
进度能存能还原、简繁转换不炸、目录能拉出来。
"""
import io
import json
import os
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

import wapi
wapi.set_dpi_aware()

import tkinter as tk
from app import ReaderApp

FAIL = []


def ck(name, cond, extra=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else "  " + str(extra)))
    if not cond:
        FAIL.append(name)


def pump(root, ms):
    end = time.time() + ms / 1000.0
    while time.time() < end:
        root.update()
        time.sleep(0.005)


def norm(s):
    """去掉所有空白，用来比对「渲染结果」和「原文」——排版会插缩进和换行。"""
    return "".join(str(s).split())


# 备份配置，测完还原，别把用户的阅读进度搞乱
STATE = os.path.join(BASE, "data", "state.json")
BAK = STATE + ".baktmp"
with io.open(STATE, encoding="utf-8") as f:
    ORIG = f.read()
with io.open(BAK, "w", encoding="utf-8") as f:
    f.write(ORIG)

root = tk.Tk()
app = ReaderApp(root)
pump(root, 800)
items = app.store.shelf()
print("书架上 %d 本书" % len(items))

for idx, it in enumerate(items):
    title = it.get("title") or "?"
    path = it.get("path") or ""
    kind = it.get("kind") or "txt"
    print("")
    print("[%d] %s  (%s)" % (idx + 1, title, kind))
    if kind == "web":
        print("  -- 网址书跳过本地打开（需要联网）")
        continue
    if not os.path.exists(path):
        ck("%s 文件存在" % title, False, path)
        continue

    t0 = time.time()
    try:
        ok = app.load_book(path, silent=True, chapter=0)
    except Exception as e:
        ck("%s 能打开" % title, False, repr(e))
        continue
    cost = time.time() - t0
    ck("%s 能打开（%.2fs）" % (title[:12], cost), ok and app.book is not None)
    b = app.book
    if b is None:
        continue
    print("  · %d 章 / %d 字 / 编码 %s" % (len(b.chapters), b.total_chars, b.encoding))
    ck("%s 有章节" % title[:12], len(b.chapters) >= 1, len(b.chapters))
    # chapters 是 [(标题, 正文)] 元组列表
    ck("%s 章名可读" % title[:12],
       bool(b.chapters) and len(str(b.chapters[0][0] or "").strip()) > 0,
       (b.chapters[0][0] if b.chapters else None))
    ck("%s 打开耗时可接受（<5s）" % title[:12], cost < 5.0, cost)

    pump(root, 250)
    body = app.text.get("1.0", "end").strip()
    # 有些书的章节本来就是卷首页（只有「第一卷」几个字），不能一律要求 20 字以上。
    # 判据改成：渲染结果和该章正文一致（比之前先去掉所有空白，排除缩进/换行差异）。
    want = norm(b.chapters[app.ci][1])
    ck("%s 正文渲染出来" % title[:12],
       bool(body) or not want, (len(body), len(want)))
    ck("%s 渲染内容与该章一致" % title[:12],
       not want or want[:24] in norm(body), (norm(body)[:24], want[:24]))

    # 跳章：中间、最后一章、再回到第一
    for ci in (len(b.chapters) // 2, len(b.chapters) - 1, 0):
        app.goto_chapter(ci)
        pump(root, 200)
        ck("%s 跳到第 %d 章" % (title[:12], ci + 1), app.ci == ci, app.ci)
    if len(b.chapters) > 3:
        app.goto_chapter(2)
        pump(root, 200)
        got = norm(app.text.get("1.0", "end"))
        want2 = norm(b.chapters[2][1])
        ck("%s 跳章后渲染的是第 3 章" % title[:12],
           app.ci == 2 and (not want2 or want2[:24] in got), (app.ci, got[:24]))

    # 进度：存 → 改 → 从记录还原
    app.goto_chapter(min(5, len(b.chapters) - 1))
    pump(root, 150)
    want_ci = app.ci
    app._save_progress()
    rec = app.store.get_progress(b.fingerprint)
    ck("%s 进度已存" % title[:12], rec is not None and int(rec.get("chapter", -1)) == want_ci,
       rec)
    app.goto_chapter(0)
    pump(root, 150)
    app.load_book(path, silent=True, chapter=rec.get("chapter"), top=rec.get("top"))
    pump(root, 200)
    ck("%s 进度能还原到第 %d 章" % (title[:12], want_ci + 1), app.ci == want_ci, app.ci)

    # 简繁转换不该炸
    try:
        app.zh = "t2s"
        app._render_cache = {}
        app._render()
        pump(root, 200)
        ck("%s 繁转简模式可用" % title[:12], app.text.get("1.0", "end").strip() != "")
        app.zh = "none"
        app._render_cache = {}
        app._render()
        pump(root, 150)
    except Exception as e:
        ck("%s 繁转简模式可用" % title[:12], False, repr(e))

    # 目录
    try:
        lines = ["%d %s" % (i + 1, c[0]) for i, c in enumerate(b.chapters)]
        ck("%s 目录可生成" % title[:12], len(lines) == len(b.chapters) and len(lines) > 0)
        ck("%s 目录条目非空" % title[:12], all(x.strip().split(" ", 1)[-1] for x in lines[:20]))
    except Exception as e:
        ck("%s 目录可生成" % title[:12], False, repr(e))

print("")
print("=" * 52)
print("失败 %d 项" % len(FAIL) if FAIL else "全部通过")
root.destroy()

# 还原配置
with io.open(BAK, encoding="utf-8") as f:
    back = f.read()
with io.open(STATE, "w", encoding="utf-8", newline="\n") as f:
    f.write(back)
os.remove(BAK)
print("配置已还原")

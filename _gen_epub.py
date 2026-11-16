# -*- coding: utf-8 -*-
"""生成一本用于自检的 EPUB（含 container.xml / opf / ncx / 3 个 XHTML）。"""
import os
import sys
import zipfile

CONTAINER = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

OPF = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="bid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>测试书 第一卷</dc:title>
    <dc:creator>测试作者</dc:creator>
  </metadata>
  <manifest>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    <item id="c1" href="Text/ch01.xhtml" media-type="application/xhtml+xml"/>
    <item id="c2" href="Text/ch02.xhtml" media-type="application/xhtml+xml"/>
    <item id="c3" href="Text/ch03.xhtml" media-type="application/xhtml+xml"/>
    <item id="cover" href="Images/cover.jpg" media-type="image/jpeg"/>
  </manifest>
  <spine toc="ncx">
    <itemref idref="c1"/>
    <itemref idref="c3"/>
    <itemref idref="c2"/>
  </spine>
</package>
"""

NCX = """<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head><meta name="dtb:uid" content="bid"/></head>
  <docTitle><text>测试书</text></docTitle>
  <navMap>
    <navPoint id="n1" playOrder="1"><navLabel><text>第一章　起风</text></navLabel>
      <content src="Text/ch01.xhtml"/></navPoint>
    <navPoint id="n3" playOrder="2"><navLabel><text>第二章　落雨</text></navLabel>
      <content src="Text/ch03.xhtml#p2"/></navPoint>
    <navPoint id="n2" playOrder="3"><navLabel><text>第三章　天晴</text></navLabel>
      <content src="Text/ch02.xhtml"/></navPoint>
  </navMap>
</ncx>
"""

CH1 = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>第一章</title><style>p{text-indent:2em}</style></head>
<body>
  <h2>第一章　起风</h2>
  <p>他把光标停在表格最后一列，&#x7B2C;一个字是「夜」。</p>
  <p>窗外风很大，<br/>玻璃上贴着一张便签。</p>
</body>
</html>
"""

CH2 = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<body>
  <h2>第三章　天晴</h2>
  <p>雨停了。</p>
  <p>他把窗口挪到右边，继续看第一行。</p>
</body>
</html>
"""

# 一个文件里塞两章，用于验证「按标题再切分」
CH3 = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<body>
  <h2>第二章　落雨</h2>
  <p>雨下了一整夜，键盘声被盖住了。</p>
  <h2>第二章　续</h2>
  <p>天亮时雨小了。<script>var x=1;</script>他合上电脑。</p>
</body>
</html>
"""


def build(path):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("META-INF/container.xml", CONTAINER)
        z.writestr("OEBPS/content.opf", OPF)
        z.writestr("OEBPS/toc.ncx", NCX)
        z.writestr("OEBPS/Text/ch01.xhtml", CH1)
        z.writestr("OEBPS/Text/ch02.xhtml", CH2)
        z.writestr("OEBPS/Text/ch03.xhtml", CH3)
    return path


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "data/_test.epub"
    build(out)
    print("built", out, os.path.getsize(out), "bytes")

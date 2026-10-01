#!/usr/bin/env python3
"""tools/pdf_extract_images.py 的单元测试。

覆盖不依赖真实 PDF 的纯函数：front matter 读取、pdfimages -list 解析、
处理根目录定位。真实提取由 ``make extract-images`` 在材料处理阶段验证。
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.pdf_extract_images import (
    find_processing_root,
    parse_pdfimages_list,
    read_front_matter,
)

SAMPLE_LIST = """page   num  type   width height color comp bpc  enc interp  object ID x-ppi y-ppi size ratio
--------------------------------------------------------------------------------------------
   1     0 image    4157   192  rgb     3   8  jpeg   no        29  0   600   600 22.8K 1.0%
   1     1 image     547   142  rgb     3   8  jpeg   no        40  0   600   600 11.3K 5.0%
   2     5 image     685   190  gray    1   8  jpeg   no        71  0   300   300 15.2K 4.0%
"""


class TestParsePdfimagesList(unittest.TestCase):
    def test_parses_rows(self):
        rows = parse_pdfimages_list(SAMPLE_LIST)
        self.assertEqual(len(rows), 3)
        first = rows[0]
        self.assertEqual(first["page"], 1)
        self.assertEqual(first["num"], 0)
        self.assertEqual(first["width"], 4157)
        self.assertEqual(first["height"], 192)
        self.assertEqual(first["color"], "rgb")
        self.assertEqual(first["enc"], "jpeg")
        self.assertEqual((first["xppi"], first["yppi"]), (600, 600))

    def test_empty(self):
        self.assertEqual(parse_pdfimages_list(""), [])


class TestReadFrontMatter(unittest.TestCase):
    def test_reads_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "output.md"
            p.write_text(
                "---\n"
                'title: "3.1_重力与弹力_第1课时_教师版"\n'
                'source: "3.1_重力与弹力_第1课时_教师版.pdf"\n'
                "pages: 12\n"
                "---\n\n正文\n",
                encoding="utf-8",
            )
            fm = read_front_matter(p)
        self.assertEqual(fm["source"], "3.1_重力与弹力_第1课时_教师版.pdf")
        self.assertEqual(fm["pages"], "12")

    def test_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "output.md"
            p.write_text("no front matter\n", encoding="utf-8")
            self.assertEqual(read_front_matter(p), {})


class TestFindProcessingRoot(unittest.TestCase):
    def test_finds_root(self):
        p = Path("/x/材料处理/2026/湖北")
        self.assertEqual(find_processing_root(p).name, "材料处理")
        p2 = Path("/x/材料处理/2025/湖北")
        self.assertEqual(find_processing_root(p2).name, "材料处理")

    def test_none(self):
        self.assertIsNone(find_processing_root(Path("/x/y/z")))


if __name__ == "__main__":
    unittest.main()

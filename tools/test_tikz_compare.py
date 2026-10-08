#!/usr/bin/env python3
"""tools/tikz_compare.py 的单元测试（孤儿 TikZ 推断、默认出图与 --no-orphans）。"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from tools import tikz_compare


def _img(path: Path, size=(40, 30)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (255, 255, 255)).save(path)
    return path


class TestTikzCompare(unittest.TestCase):
    def test_tikz_sources_lists_tex_stems(self):
        with tempfile.TemporaryDirectory() as tmp:
            lesson = Path(tmp) / "卷"
            (lesson / "TikZ").mkdir(parents=True)
            (lesson / "TikZ" / "b.tex").write_text("x", encoding="utf-8")
            (lesson / "TikZ" / "a.tex").write_text("x", encoding="utf-8")
            (lesson / "TikZ" / "a.pdf").write_bytes(b"%PDF")
            self.assertEqual(tikz_compare.tikz_sources(lesson), ["a", "b"])

    def test_infer_original_priority_and_svg(self):
        with tempfile.TemporaryDirectory() as tmp:
            lesson = Path(tmp) / "卷"
            _img(lesson / "TikZ" / "originals" / "A.png")
            _img(lesson / "figs" / "A.png")
            e = tikz_compare._infer_original(lesson, "A")
            self.assertTrue(str(e["original"]).endswith("TikZ/originals/A.png"), e)
            # 只有 SVG 时也能推断
            lesson2 = Path(tmp) / "卷2"
            (lesson2 / "figs").mkdir(parents=True)
            (lesson2 / "figs" / "B.svg").write_text("<svg/>", encoding="utf-8")
            e2 = tikz_compare._infer_original(lesson2, "B")
            self.assertTrue(str(e2["original"]).endswith("figs/B.svg"), e2)
            self.assertIsNone(tikz_compare._infer_original(lesson2, "C"))

    def test_default_generates_orphan_sheet(self):
        # 默认（不带任何 flag）即处理“只上传 TikZ 文件夹”的孤儿源。
        with tempfile.TemporaryDirectory() as tmp:
            lesson = Path(tmp) / "卷"
            (lesson / "TikZ").mkdir(parents=True)
            (lesson / "TikZ" / "A.tex").write_text(r"\documentclass{standalone}", encoding="utf-8")
            (lesson / "TikZ" / "A.pdf").write_bytes(b"%PDF-1.4\n")
            _img(lesson / "figs" / "A.png")
            (lesson / "doc.tex").write_text("题干，无图引用", encoding="utf-8")

            def fake_render(pdf, out_png, dpi):
                Image.new("RGB", (40, 30), (255, 255, 255)).save(out_png)
                return out_png.exists()

            with mock.patch.object(tikz_compare, "render_tikz", fake_render):
                rc = tikz_compare.main([str(lesson)])
            self.assertEqual(rc, 0)
            out = lesson / "tikz_compare" / f"{lesson.name}_未引用TikZ_重绘前后.png"
            self.assertTrue(out.exists(), "默认应为未引用 TikZ 生成对比图")

    def test_referenced_mapping_figs_original(self):
        # 标准路径：正文引用 + tikz_sources.json 登记，original 指向 figs/ 同名图。
        with tempfile.TemporaryDirectory() as tmp:
            lesson = Path(tmp) / "卷"
            (lesson / "TikZ").mkdir(parents=True)
            (lesson / "TikZ" / "07e.tex").write_text(r"\documentclass{standalone}", encoding="utf-8")
            (lesson / "TikZ" / "07e.pdf").write_bytes(b"%PDF-1.4\n")
            _img(lesson / "figs" / "07e.png")
            (lesson / "TikZ" / "tikz_sources.json").write_text(
                json.dumps({"entries": [{"tikz": "07e",
                                         "original": str(lesson / "figs" / "07e.png")}]},
                           ensure_ascii=False), encoding="utf-8")
            (lesson / "doc.tex").write_text(r"\onepicture{TikZ/07e.pdf}", encoding="utf-8")

            def fake_render(pdf, out_png, dpi):
                Image.new("RGB", (40, 30), (255, 255, 255)).save(out_png)
                return out_png.exists()

            with mock.patch.object(tikz_compare, "render_tikz", fake_render):
                rc = tikz_compare.main([str(lesson)])
            self.assertEqual(rc, 0)
            self.assertTrue((lesson / "tikz_compare" / "doc_重绘前后.png").exists())

    def test_registered_unreferenced_not_treated_as_orphan(self):
        # 已登记但未引用：不算孤儿（留给 check_tikz 报“可删除该登记”），不生成未引用对比图。
        with tempfile.TemporaryDirectory() as tmp:
            lesson = Path(tmp) / "卷"
            (lesson / "TikZ").mkdir(parents=True)
            (lesson / "TikZ" / "A.tex").write_text(r"\documentclass{standalone}", encoding="utf-8")
            (lesson / "TikZ" / "A.pdf").write_bytes(b"%PDF-1.4\n")
            _img(lesson / "figs" / "A.png")
            (lesson / "TikZ" / "tikz_sources.json").write_text(
                json.dumps({"entries": [{"tikz": "A",
                                         "original": str(lesson / "figs" / "A.png")}]},
                           ensure_ascii=False), encoding="utf-8")
            (lesson / "doc.tex").write_text("题干，无图引用", encoding="utf-8")
            rc = tikz_compare.main([str(lesson)])
            self.assertEqual(rc, 0)
            self.assertFalse((lesson / "tikz_compare").exists())

    def test_no_orphans_skips(self):
        with tempfile.TemporaryDirectory() as tmp:
            lesson = Path(tmp) / "卷"
            (lesson / "TikZ").mkdir(parents=True)
            (lesson / "TikZ" / "A.tex").write_text(r"\documentclass{standalone}", encoding="utf-8")
            _img(lesson / "figs" / "A.png")
            (lesson / "doc.tex").write_text("题干", encoding="utf-8")
            rc = tikz_compare.main([str(lesson), "--no-orphans"])
            self.assertEqual(rc, 0)
            self.assertFalse((lesson / "tikz_compare").exists())


if __name__ == "__main__":
    unittest.main()

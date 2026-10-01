#!/usr/bin/env python3
"""tools/match_figures.py 的单元测试（相似度 / 面板缓存 / 端到端匹配 / 多源 PDF 分域）。"""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image, ImageDraw

from tools import match_figures as mf


def _pattern(kind: str, size=(220, 220)) -> Image.Image:
    im = Image.new("L", size, 255)
    d = ImageDraw.Draw(im)
    if kind == "square":
        d.rectangle([30, 30, 190, 190], outline=0, width=8)
    elif kind == "circle":
        d.ellipse([30, 30, 190, 190], outline=0, width=8)
    elif kind == "cross":
        d.line([30, 30, 190, 190], fill=0, width=8)
        d.line([190, 30, 30, 190], fill=0, width=8)
    return im


class TestScore(unittest.TestCase):
    def test_identical_high(self):
        a = mf._norm(_pattern("square"))
        self.assertGreater(mf._score(a, a), 0.99)

    def test_different_lower(self):
        s = mf._score(mf._norm(_pattern("square")), mf._norm(_pattern("cross")))
        self.assertLess(s, 0.9)


class TestPanelCache(unittest.TestCase):
    def test_cached(self):
        im = _pattern("square")
        mf._PANEL_CACHE.clear()
        with mock.patch.object(mf, "splitpicture_panels", return_value=[(0, 0, 100, 100)]) as mk:
            p1 = mf._panels("/nonexistent/x.jpg", im, "splitpicture")
            p2 = mf._panels("/nonexistent/x.jpg", im, "splitpicture")
        self.assertEqual(p1, p2)
        self.assertEqual(mk.call_count, 1)


class TestPrefetchPanels(unittest.TestCase):
    def test_batch_fills_cache_and_skips_duplicate_stems(self):
        mf._PANEL_CACHE.clear()

        class _Proc:
            returncode = 0
            stdout = "{}"
            stderr = ""

        def fake_run(cmd, **kwargs):
            d = Path(cmd[cmd.index("-d") + 1])
            for i, arg in enumerate(cmd):
                if arg != "-i":
                    continue
                sub = d / Path(cmd[i + 1]).stem
                sub.mkdir(parents=True, exist_ok=True)
                (sub / "rects.json").write_text(
                    json.dumps([{"x": 0, "y": 0, "w": 10, "h": 10}]), encoding="utf-8")
            return _Proc()

        files = ["/a/p1.jpg", "/b/p1.jpg", "/c/p2.jpg"]
        with mock.patch.object(mf.subprocess, "run", side_effect=fake_run):
            mf._prefetch_panels(files, "splitpicture")
        # 重名 stem 的两张不批量（避免 --per-file-subdir 互相覆盖），仅唯一 stem 入缓存
        self.assertNotIn("/a/p1.jpg", mf._PANEL_CACHE)
        self.assertNotIn("/b/p1.jpg", mf._PANEL_CACHE)
        self.assertEqual(mf._PANEL_CACHE["/c/p2.jpg"], [(0, 0, 10, 10)])

    def test_prefetch_passes_tight(self):
        mf._PANEL_CACHE.clear()
        seen = {}

        class _Proc:
            returncode = 0
            stdout = "{}"
            stderr = ""

        def fake_run(cmd, **kwargs):
            seen["cmd"] = list(cmd)
            return _Proc()

        with mock.patch.object(mf.subprocess, "run", side_effect=fake_run):
            mf._prefetch_panels(["/c/p2.jpg"], "splitpicture", tight=True)
        self.assertIn("--tight", seen["cmd"])


class TestMatchEndToEnd(unittest.TestCase):
    def _make_proc(self, root: Path, name: str, img: Image.Image, page: int = 3):
        proc = root / name
        (proc / "ovis" / "images").mkdir(parents=True)
        (proc / "pdfimages").mkdir(parents=True)
        img.save(proc / "pdfimages" / f"p{page}_0.jpg")
        # OCR 裁切图：文件名含页码，内容与内嵌图相同
        img.save(proc / "ovis" / "images" / f"page_{page}_bbox_10_10_200_200.jpg")
        return proc

    def _make_section(self, root: Path, old: Image.Image):
        sec = root / "lesson"
        (sec / "figs" / ".ocr_before").mkdir(parents=True)
        (sec / "lesson.tex").write_text(
            r"\onepicture[w=3cm]{figs/foo.jpg}", encoding="utf-8")
        old.save(sec / "figs" / ".ocr_before" / "foo.jpg")
        old.save(sec / "figs" / "foo.jpg")
        return sec

    def test_single_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = _pattern("square")
            sec = self._make_section(root, old)
            proc = self._make_proc(root, "proc1", old)
            with contextlib.redirect_stdout(io.StringIO()):
                res = mf.match(sec, [(proc, proc / "pdfimages")], 110, "splitpicture")
        self.assertEqual(res["foo"]["source"], "p3_0.jpg")
        self.assertEqual(res["foo"]["page"], 3)
        self.assertGreaterEqual(res["foo"]["score"], 0.99)

    def test_multi_pdf_scoping(self):
        """两个源 PDF 的同一页码不会串图：应命中内容相同的那个源。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = _pattern("circle")
            sec = self._make_section(root, old)
            p1 = self._make_proc(root, "proc1", _pattern("cross"), page=3)
            p2 = self._make_proc(root, "proc2", old, page=3)
            with contextlib.redirect_stdout(io.StringIO()):
                res = mf.match(sec, [(p1, p1 / "pdfimages"), (p2, p2 / "pdfimages")],
                               110, "splitpicture")
        self.assertIn("proc2", res["foo"]["source_rel"])
        self.assertNotIn("proc1", res["foo"]["source_rel"])


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""tools/check_tikz.py 的单元测试（tikz_sources.json 结构与引用一致性校验）。"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from tools.check_tikz import check_lesson, referenced_tikz


def _img(path: Path, size=(40, 30)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (255, 255, 255)).save(path)
    return path


def _lesson(d: Path, refs, entries, tex_name="doc.tex"):
    d.joinpath(tex_name).write_text(
        "\n".join(f"\\onepicture{{TikZ/{t}.pdf}}" for t in refs), encoding="utf-8")
    (d / "TikZ").mkdir(exist_ok=True)
    for t in refs:
        (d / "TikZ" / f"{t}.pdf").write_bytes(b"%PDF-1.4\n")
    (d / "TikZ" / "tikz_sources.json").write_text(
        json.dumps({"entries": entries}, ensure_ascii=False), encoding="utf-8")


class TestCheckTikz(unittest.TestCase):
    def test_referenced_tikz_dedup_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "d.tex"
            p.write_text(r"\onepicture{TikZ/b.pdf}\onepicture{TikZ/a.pdf}"
                         r"\onepicture{TikZ/b.pdf}", encoding="utf-8")
            self.assertEqual(referenced_tikz(p), ["b", "a"])

    def test_valid_lesson(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _img(d / "figs" / "o.png")
            _lesson(d, ["A"], [{"tikz": "A", "original": "figs/o.png"}])
            errors, _warnings, n = check_lesson(d, root=d)
            self.assertEqual(errors, [])
            self.assertEqual(n, 1)

    def test_missing_mapping_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "doc.tex").write_text(r"\onepicture{TikZ/A.pdf}", encoding="utf-8")
            errors, _w, _n = check_lesson(d, root=d)
            self.assertTrue(any("缺" in e or " tikz_sources" in e for e in errors), errors)

    def test_referenced_not_registered(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _lesson(d, ["A", "B"], [{"tikz": "A", "original": None}])
            errors, _w, _n = check_lesson(d, root=d)
            self.assertTrue(any("未在 tikz_sources.json 登记" in e for e in errors), errors)

    def test_null_original_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _lesson(d, ["A"], [{"tikz": "A", "original": None}])
            errors, _w, n = check_lesson(d, root=d)
            self.assertEqual(errors, [])
            self.assertEqual(n, 0)

    def test_missing_original_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _lesson(d, ["A"], [{"tikz": "A", "original": "figs/none.png"}])
            errors, _w, _n = check_lesson(d, root=d)
            self.assertTrue(any("original 不存在" in e for e in errors), errors)

    def test_duplicate_tikz(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _lesson(d, ["A"], [{"tikz": "A", "original": None},
                               {"tikz": "A", "original": None}])
            errors, _w, _n = check_lesson(d, root=d)
            self.assertTrue(any("重复" in e for e in errors), errors)

    def test_unused_mapping_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _img(d / "figs" / "o.png")
            _lesson(d, ["A"], [{"tikz": "A", "original": "figs/o.png"},
                               {"tikz": "Z", "original": "figs/o.png"}])
            errors, warnings, _n = check_lesson(d, root=d)
            self.assertEqual(errors, [])
            self.assertTrue(any("未在任何 .tex 中引用" in w and "Z" in w for w in warnings), warnings)

    def test_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "doc.tex").write_text(r"\onepicture{TikZ/A.pdf}", encoding="utf-8")
            (d / "TikZ").mkdir()
            (d / "TikZ" / "tikz_sources.json").write_text("{not json", encoding="utf-8")
            errors, _w, _n = check_lesson(d, root=d)
            self.assertTrue(any("JSON" in e for e in errors), errors)

    def test_orphan_source_warns_when_unreferenced(self):
        # 典型半成品 PR：只上传 TikZ/*.tex，正文未引用、无登记文件。
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "TikZ").mkdir()
            (d / "TikZ" / "A.tex").write_text(r"\documentclass{standalone}", encoding="utf-8")
            (d / "doc.tex").write_text("题干", encoding="utf-8")
            errors, warnings, n = check_lesson(d, root=d)
            self.assertEqual(errors, [])
            self.assertTrue(any("TikZ/A.tex" in w for w in warnings), warnings)

    def test_orphan_source_warns_alongside_valid_ref(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _img(d / "figs" / "o.png")
            _lesson(d, ["A"], [{"tikz": "A", "original": "figs/o.png"}])
            (d / "TikZ" / "B.tex").write_text(r"\documentclass{standalone}", encoding="utf-8")
            errors, warnings, _n = check_lesson(d, root=d)
            self.assertEqual(errors, [])
            self.assertTrue(any("TikZ/B.tex" in w for w in warnings), warnings)

    def test_referenced_missing_tex_source_warns(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _img(d / "figs" / "o.png")
            _lesson(d, ["A"], [{"tikz": "A", "original": "figs/o.png"}])
            errors, warnings, _n = check_lesson(d, root=d)
            self.assertEqual(errors, [])
            self.assertTrue(any("缺少 TikZ/A.tex" in w for w in warnings), warnings)
            # 补上 .tex 源后不再提示
            (d / "TikZ" / "A.tex").write_text(r"\documentclass{standalone}", encoding="utf-8")
            _e, warnings2, _n2 = check_lesson(d, root=d)
            self.assertFalse(any("缺少 TikZ/A.tex" in w for w in warnings2), warnings2)

    def test_orphan_name_match_note(self):
        # 同名 figs/ 原图存在 → 提示“可自动对比”，不应出现“未找到同名原图”
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "TikZ").mkdir()
            (d / "TikZ" / "A.tex").write_text(r"\documentclass{standalone}", encoding="utf-8")
            _img(d / "figs" / "A.png")
            (d / "doc.tex").write_text("题干", encoding="utf-8")
            _e, warnings, _n = check_lesson(d, root=d)
            self.assertTrue(any("TikZ/A.tex" in w for w in warnings), warnings)
            self.assertFalse(any("未找到同名原图" in w for w in warnings), warnings)
        # 无同名 figs/ → 提示名字必须一致
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "TikZ").mkdir()
            (d / "TikZ" / "B.tex").write_text(r"\documentclass{standalone}", encoding="utf-8")
            (d / "doc.tex").write_text("题干", encoding="utf-8")
            _e, warnings, _n = check_lesson(d, root=d)
            self.assertTrue(any("未找到同名原图" in w for w in warnings), warnings)


if __name__ == "__main__":
    unittest.main()

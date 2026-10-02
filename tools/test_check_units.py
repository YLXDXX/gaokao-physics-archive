"""tools/test_check_units.py —— check_units 单位宏检查测试。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools import check_units


def _write(tmp: Path, text: str) -> Path:
    p = tmp / "t.tex"
    p.write_text(text, encoding="utf-8")
    return p


class TestCheckUnits(unittest.TestCase):
    def test_defined_ok(self):
        with tempfile.TemporaryDirectory() as d:
            tex = _write(Path(d), "速度 $2\\Ums$，质量 $3\\Ukg$。")
            errs, _ = check_units.check_file(tex, {"Ums", "Ukg"})
            self.assertEqual(errs, [])

    def test_undefined_macro(self):
        with tempfile.TemporaryDirectory() as d:
            tex = _write(Path(d), "速度 $2\\Uks$。")
            errs, _ = check_units.check_file(tex, {"Ums"})
            self.assertTrue(any("Uks" in e for e in errs))

    def test_suggest_bare_unit(self):
        with tempfile.TemporaryDirectory() as d:
            tex = _write(Path(d), "速度 10 m/s。")
            _, warns = check_units.check_file(tex, {"Ums"}, suggest=True)
            self.assertTrue(any("Ums" in w for w in warns))

    def test_comment_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            tex = _write(Path(d), "% \\Uks 注释里不算\n速度 $2\\Ums$。")
            errs, _ = check_units.check_file(tex, {"Ums"})
            self.assertEqual(errs, [])


if __name__ == "__main__":
    unittest.main()

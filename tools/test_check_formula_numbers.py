"""tools/test_check_formula_numbers.py —— 公式编号检查单元测试。"""
from __future__ import annotations

import unittest

from tools import check_formula_numbers as c


def _blk(memo: str) -> str:
    return ("%% number: 1\n%% body:\n题干\n%% answer:\n%% memo:\n"
            "\\memoanswer{" + memo + "}\n")


class TestFormulaNumbers(unittest.TestCase):
    def test_contiguous_ok(self):
        errs, _ = c.check_text(_blk(r"由 $a=b$ ①，$c=d$ ②，联立①②式"))
        self.assertEqual(errs, [])

    def test_gap_error(self):
        errs, _ = c.check_text(_blk(r"由 $a=b$ ①，$c=d$ ③，联立①③式"))
        self.assertTrue(any("②" in e for e in errs))

    def test_figure_labels_ignored(self):
        # “图象为②/图③/选项②”不是公式编号，不应触发缺号
        errs, _ = c.check_text(_blk(r"故 $E$ 的图象为②，速度图象为③。"))
        self.assertEqual(errs, [])

    def test_subitem_labels_ignored(self):
        # 行首/括号后紧跟汉字的 ①③ 是小问条目标签，不是公式编号
        errs, _ = c.check_text(_blk(r"（1）①根据原理可知；③当 $m=460$ 时。"))
        self.assertEqual(errs, [])

    def test_orphan_reference_warn(self):
        _, warns = c.check_text(_blk(r"由①式得 $x=1$"))
        self.assertTrue(any("①" in w for w in warns))

    def test_paren_style_ok(self):
        # 宁夏风格：（①）（②）（③）
        errs, _ = c.check_text(_blk(r"$R=d\sin\varphi$（①），$mg=ma$（②）。"))
        self.assertEqual(errs, [])


if __name__ == "__main__":
    unittest.main()

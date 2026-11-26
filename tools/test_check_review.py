"""tools/test_check_review.py —— 引用风格（交叉校对 --ref-audit）纯函数测试。"""
from __future__ import annotations

import unittest

from tools import check_review as cr


class TestRefSpacing(unittest.TestCase):
    def test_good_spacing(self):
        text = "如图 \\ref{2026云南08a} 所示；图~\\ref{2026云南08b}~中。"
        self.assertEqual(cr.collect_ref_style_issues(text), [])

    def test_missing_space_before_and_after(self):
        issues = cr.collect_ref_style_issues("如图\\ref{2026云南08a}所示")
        hard = [msg for _, msg, is_hard in issues if is_hard]
        self.assertEqual(len(hard), 2)

    def test_eqref_and_pageref(self):
        issues = cr.collect_ref_style_issues("由式\\eqref{eq:1}可知，见\\pageref{sec:1}。")
        hard = [msg for _, msg, is_hard in issues if is_hard]
        self.assertEqual(len(hard), 3)  # eqref 前后各 1，pageref 前 1

    def test_punctuation_is_separator(self):
        issues = cr.collect_ref_style_issues("（图 \\ref{a}）与图 \\ref{b}、图 \\ref{c}。")
        self.assertEqual(issues, [])

    def test_manual_figure_number_is_soft(self):
        issues = cr.collect_ref_style_issues("如图甲所示，图 1 中电流方向如图A。")
        self.assertEqual(len(issues), 3)
        self.assertTrue(all(not is_hard for _, _, is_hard in issues))

    def test_ref_before_manual_like_text_not_matched(self):
        issues = cr.collect_ref_style_issues("图~\\ref{2026云南08a} 中。")
        self.assertEqual(issues, [])

    def test_comments_ignored(self):
        text = "% 图\\ref{a}中，图甲所示\n如图 \\ref{a} 所示"
        self.assertEqual(cr.collect_ref_style_issues(text), [])


if __name__ == "__main__":
    unittest.main()

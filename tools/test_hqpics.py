"""tools/test_hqpics.py —— HighQualityPic 命名/重写纯函数测试。"""
from __future__ import annotations

import unittest

from tools import hqpics as h


class TestNaming(unittest.TestCase):
    def test_norm_folder(self):
        self.assertEqual(h._norm_folder(1978, "全国", "全国", False, "exact"), "1978_全国")
        self.assertEqual(h._norm_folder(1978, "全国", "全国", True, "alias"), "1978_全国_答案")
        self.assertEqual(h._norm_folder(2024, None, "黑吉辽", False, "uncertain"), "2024_黑吉辽")

    def test_norm_file(self):
        self.assertEqual(h._norm_file("1978_全国", "1978年全国卷物理_p0_Fm5.pdf"),
                         "1978_全国_Fm5.pdf")
        self.assertEqual(h._norm_file("2010_四川理综", "2010年四川卷物理_p0_Fm11_2.pdf"),
                         "2010_四川理综_Fm11_2.pdf")
        # 天利按页编号：保留页号，避免跨页重名
        self.assertEqual(h._norm_file("2025_1月浙江", "2025_1月浙江_p02_f01.pdf"),
                         "2025_1月浙江_p02_Fm01.pdf")
        self.assertEqual(h._norm_file("2026_全国理综", "2026_全国理综_p10_f12.pdf"),
                         "2026_全国理综_p10_Fm12.pdf")

    def test_hq_source(self):
        self.assertEqual(h._hq_source(2024), ("zhu", "朱玉亮"))
        self.assertEqual(h._hq_source(2025), ("tian", "天利38套"))
        self.assertEqual(h._hq_source(2026), ("tian", "天利38套"))

    def test_fig_kind(self):
        self.assertEqual(h._fig_kind("07_an"), "answer")
        self.assertEqual(h._fig_kind("11an"), "answer")
        self.assertEqual(h._fig_kind("14an1"), "answer")
        self.assertEqual(h._fig_kind("05a"), "question")
        self.assertEqual(h._fig_kind("plan"), "question")


class TestApplyGuard(unittest.TestCase):
    def test_same_stem_allows_new_pdf(self):
        self.assertFalse(h._has_unrewritten_refs(r"\onepicture{figs/09.pdf}", "09", "09"))

    def test_same_stem_blocks_other_extension(self):
        text = r"\onepicture{figs/09.pdf}\twopicture{figs/09.png}{figs/10.png}"
        self.assertTrue(h._has_unrewritten_refs(text, "09", "09"))

    def test_different_stem_blocks_old_pdf(self):
        self.assertTrue(h._has_unrewritten_refs(r"\onepicture{figs/09.pdf}", "09", "09a"))

    def test_does_not_match_sibling_stem(self):
        self.assertFalse(h._has_unrewritten_refs(r"\onepicture{figs/09a.pdf}", "09", "09"))
        self.assertFalse(h._has_unrewritten_refs(r"\onepicture{figs/09_an.pdf}", "09", "09"))


class TestRewrite(unittest.TestCase):
    def test_take_braced(self):
        s = r"\x{a{b}c}{d}"
        arg, j = h._take_braced(s, 2)
        self.assertEqual(arg, "a{b}c")
        self.assertEqual(s[j:], "{d}")

    def test_onepicture_png(self):
        s = r"\onepicture[align=right, w=3.80cm]{figs/06.png}"
        out, n = h._rewrite_onepicture(s, "06", "06", 4.34, 2.43)
        self.assertEqual(n, 1)
        self.assertIn(r"figs/06.pdf", out)
        self.assertIn("w=4.34cm", out)
        self.assertIn("h=2.43cm", out)
        self.assertNotIn("3.80cm", out)

    def test_onepicture_svg(self):
        s = r"\onepicture[h=4.57cm]{\includesvg{figs/11}}"
        out, n = h._rewrite_onepicture(s, "11", "11", 4.80, 3.03)
        self.assertEqual(n, 1)
        self.assertIn(r"figs/11.pdf", out)
        self.assertNotIn("includesvg", out)

    def test_onepicture_no_match(self):
        s = r"\onepicture{figs/07.png}"
        out, n = h._rewrite_onepicture(s, "06", "06", 1, 1)
        self.assertEqual(n, 0)
        self.assertEqual(out, s)

    def test_fourpicture(self):
        s = (r"\fourpicture[wA=3.01cm, wB=3.02cm]{figs/05a.png}{figs/05b.png}"
             r"{figs/05c.png}{figs/05d.png}")
        out, n = h._rewrite_multi(s, "fourpicture", 4, "05b", "05b", 3.39, 3.14)
        self.assertEqual(n, 1)
        self.assertIn(r"figs/05b.pdf", out)
        self.assertIn(r"{figs/05a.png}", out)
        self.assertIn("wA=3.01cm", out)
        self.assertIn("wB=3.39cm", out)
        self.assertIn("hB=3.14cm", out)

    def test_dispatch_prefers_onepicture(self):
        s = r"\onepicture{figs/06.png}"
        out, n = h._rewrite_figure_refs(s, "06", "06", 1, 2)
        self.assertEqual(n, 1)
        self.assertIn("figs/06.pdf", out)

    def test_replace_inner_keeps_sibling_stem(self):
        self.assertEqual(h._replace_inner(r"figs/19_an.png", "19", "19"),
                         r"figs/19_an.png")
        self.assertEqual(h._replace_inner(r"figs/19.png", "19", "19"),
                         r"figs/19.pdf")

    def test_strip_size_opts(self):
        self.assertEqual(h._strip_size_opts("align=right, w=3cm, h=2cm, num=1"),
                         "align=right, num=1")

    def test_split_opts_keeps_braced_commas(self):
        opts = "ispicture=true, descA={甲, 乙}, wA=3cm, answer=C"
        self.assertEqual(h._split_opts(opts),
                         ["ispicture=true", "descA={甲, 乙}", "wA=3cm", "answer=C"])
        out = h._set_per_image_size(opts, "A", 4, 2)
        self.assertIn("descA={甲, 乙}", out)
        self.assertNotIn("wA=3cm", out)
        self.assertIn("wA=4.00cm", out)


if __name__ == "__main__":
    unittest.main()

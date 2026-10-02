"""tools/test_html2latex.py —— HTML→LaTeX 转换器单元测试。

覆盖移植自 texgen 的核心行为：数学片段合并、文本转义、上下标/变量、
公式内汉字、表格、图片注册。"""
from __future__ import annotations

import unittest

from tools import html2latex as h


class TestMergeMathSegments(unittest.TestCase):
    def test_adjacent_merge(self):
        self.assertEqual(h._merge_math_segments(r"$Rc$$\left( x \right)$"),
                         r"$Rc\left( x \right)$")
        self.assertEqual(h._merge_math_segments(r"$m$$v$"), r"$mv$")

    def test_operator_gap_merge(self):
        self.assertEqual(h._merge_math_segments(r"$P$ = $UI$"), r"$P = UI$")
        self.assertEqual(h._merge_math_segments(r"$a$ + $b$"), r"$a + b$")

    def test_chain_and_supsub(self):
        self.assertEqual(h._merge_math_segments(r"$m$$v$$_{0}$ + $mgt$"),
                         r"$mv_{0} + mgt$")
        self.assertEqual(h._merge_math_segments(r"$^{18}$$_{9}$"), r"$^{18}_{9}$")

    def test_no_merge_across_punctuation(self):
        self.assertEqual(h._merge_math_segments(r"$a$, $b$"), r"$a$, $b$")


class TestTextToLatex(unittest.TestCase):
    def test_escapes(self):
        self.assertEqual(h.text_to_latex("a_b"), r"a\_b")
        self.assertEqual(h.text_to_latex("50%"), r"50\%")
        self.assertEqual(h.text_to_latex("A&B"), r"A\&B")

    def test_symbols(self):
        self.assertIn(r"$\times$", h.text_to_latex("3×4"))
        self.assertIn(r"$\alpha$", h.text_to_latex("α 粒子"))


class TestHtmlToLatex(unittest.TestCase):
    def test_em_sub(self):
        self.assertEqual(h.HtmlToLatex().convert("<p><em>a</em><sub>1</sub></p>"),
                         r"$a_{1}$")

    def test_sup_number(self):
        out = h.HtmlToLatex().convert("<p>10<sup>23</sup></p>")
        self.assertIn("10", out)
        self.assertIn("^{23}", out)

    def test_strong_u_br(self):
        out = h.HtmlToLatex().convert("<p><strong>注意</strong><u>空</u></p>")
        self.assertIn(r"\textbf{注意}", out)
        self.assertIn(r"\CJKunderline", out)

    def test_math_cjk_wrapped(self):
        out = h.HtmlToLatex().convert(r"<p>功率 \(P_{总}\)</p>")
        self.assertIn(r"\text{总}", out)

    def test_inline_math(self):
        self.assertEqual(h.HtmlToLatex().convert(r"<p>速度 \(v\) 恒定</p>"),
                         r"速度 $v$ 恒定")

    def test_table(self):
        out = h.HtmlToLatex().convert(
            "<table><tr><td>a</td><td>b</td></tr>"
            "<tr><td>1</td><td>2</td></tr></table>")
        self.assertIn(r"\begin{tabular}", out)
        self.assertIn("a & b", out)


class TestImageRegistry(unittest.TestCase):
    def test_naming_and_dedup(self):
        import tempfile, os
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "x.png"), "wb") as fh:
                fh.write(b"png")
            reg = h.ImageRegistry(d)
            self.assertEqual(reg.register("x.png"), "01.png")
            self.assertEqual(reg.register("x.png"), "01.png")  # 去重
            self.assertIsNone(reg.register("missing.png"))


if __name__ == "__main__":
    unittest.main()

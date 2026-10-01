"""tools/textfix/test_textfix.py

``tools/textfix`` 模块单元测试。

运行方式（任选其一）::

    python3 tools/textfix/test_textfix.py
    python3 -m unittest tools.textfix.test_textfix
    python3 -m pytest tools/textfix/test_textfix.py
"""
import sys
import tempfile
import unittest
from pathlib import Path

try:  # 作为包导入
    from .rules import RULES, apply_rules, scan_text
    from .textfix import fix_file, fix_text, iter_target_files
except ImportError:  # 直接运行脚本
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from rules import RULES, apply_rules, scan_text
    from textfix import fix_file, fix_text, iter_target_files


class TestColonRule(unittest.TestCase):
    """规则 digit-colon-digit：数字之间的全角冒号改半角。"""

    def assert_fixed(self, src, expected):
        out, _ = fix_text(src)
        self.assertEqual(out, expected)

    # -- 应当命中 ---------------------------------------------------------
    def test_time_basic(self):
        self.assert_fixed("上课时间 8：00 为时刻。", "上课时间 8:00 为时刻。")

    def test_time_multiple(self):
        self.assert_fixed("19：26、12：21", "19:26、12:21")

    def test_time_with_seconds(self):
        self.assert_fixed("8：00：00", "8:00:00")

    def test_ratio(self):
        self.assert_fixed("两数之比为 1：2", "两数之比为 1:2")

    def test_math_mode(self):
        self.assert_fixed(r"$t=8：00$", r"$t=8:00$")

    def test_mixed_sentence(self):
        self.assert_fixed("时间是：8 点，而 8：00 是时刻。",
                          "时间是：8 点，而 8:00 是时刻。")

    # -- 不应命中 ---------------------------------------------------------
    def test_chinese_colon_kept(self):
        self.assert_fixed("注意：这是重点。", "注意：这是重点。")

    def test_chinese_colon_before_digit_kept(self):
        self.assert_fixed("时间是：8 点", "时间是：8 点")

    def test_digit_colon_chinese_kept(self):
        self.assert_fixed("8：上课", "8：上课")

    def test_latex_commands_untouched(self):
        self.assert_fixed(r"\tkanswer{√}\xzanswer{×}", r"\tkanswer{√}\xzanswer{×}")

    # -- 统计与幂等 -------------------------------------------------------
    def test_change_count(self):
        _, changes = fix_text("8：00 和 9：30")
        self.assertEqual(changes, [("digit-colon-digit", 2)])

    def test_no_change(self):
        _, changes = fix_text("8:00")
        self.assertEqual(changes, [])

    def test_idempotent(self):
        once, _ = fix_text("8：00、9：30")
        twice, changes = fix_text(once)
        self.assertEqual(once, twice)
        self.assertEqual(changes, [])


class TestMathHyphenRule(unittest.TestCase):
    """规则 math-hyphen-merge：$A$-$B$ → $A-B$。"""

    def assert_fixed(self, src, expected):
        out, _ = fix_text(src)
        self.assertEqual(out, expected)

    # -- 应当命中 ---------------------------------------------------------
    def test_basic(self):
        self.assert_fixed("$x$-$t$ 图像", "$x-t$ 图像")

    def test_velocity(self):
        self.assert_fixed("理解 $v$-$t$ 图像的物理意义", "理解 $v-t$ 图像的物理意义")

    def test_chain(self):
        self.assert_fixed("$a$-$b$-$c$", "$a-b-c$")

    def test_no_space_after(self):
        self.assert_fixed("$x$-$t$图像", "$x-t$图像")

    def test_multiple_in_line(self):
        self.assert_fixed("$x$-$t$ 与 $v$-$t$ 图像", "$x-t$ 与 $v-t$ 图像")

    # -- 不应命中 ---------------------------------------------------------
    def test_no_hyphen(self):
        self.assert_fixed("$x$ 与 $t$", "$x$ 与 $t$")

    def test_leading_minus(self):
        self.assert_fixed("位移为 $-5\\Um$", "位移为 $-5\\Um$")

    def test_hyphen_before_text(self):
        self.assert_fixed("$a$-b", "$a$-b")

    def test_text_hyphen(self):
        self.assert_fixed("这是一段中文-中文", "这是一段中文-中文")

    def test_across_lines(self):
        self.assert_fixed("$x$\n-$t$", "$x$\n-$t$")

    # -- 统计与幂等 -------------------------------------------------------
    def test_change_count(self):
        _, changes = fix_text("$x$-$t$ 与 $v$-$t$")
        self.assertEqual(changes, [("math-hyphen-merge", 2)])

    def test_idempotent(self):
        once, _ = fix_text("$x$-$t$")
        twice, changes = fix_text(once)
        self.assertEqual(once, "$x-t$")
        self.assertEqual(once, twice)
        self.assertEqual(changes, [])


class TestDfracRule(unittest.TestCase):
    """规则 dfrac-to-frac：\\dfrac → \\frac。"""

    def assert_fixed(self, src, expected):
        out, _ = fix_text(src)
        self.assertEqual(out, expected)

    # -- 应当命中 ---------------------------------------------------------
    def test_basic(self):
        self.assert_fixed(r"$\dfrac{3}{2}\pi R$", r"$\frac{3}{2}\pi R$")

    def test_formula(self):
        self.assert_fixed(r"$a=\dfrac{v-v_0}{t}$", r"$a=\frac{v-v_0}{t}$")

    def test_multiple_in_line(self):
        self.assert_fixed(
            r"$a=\dfrac{\Delta v}{t}=\dfrac{v-v_0}{t}$",
            r"$a=\frac{\Delta v}{t}=\frac{v-v_0}{t}$",
        )

    def test_with_space(self):
        self.assert_fixed(r"\dfrac {1}{2}", r"\frac {1}{2}")

    # -- 不应命中 ---------------------------------------------------------
    def test_tfrac_kept(self):
        self.assert_fixed(r"$\tfrac{1}{2}$", r"$\tfrac{1}{2}$")

    def test_similar_command_kept(self):
        self.assert_fixed(r"\dfracX", r"\dfracX")

    def test_frac_kept(self):
        self.assert_fixed(r"$\frac{1}{2}$", r"$\frac{1}{2}$")

    # -- 统计与幂等 -------------------------------------------------------
    def test_change_count(self):
        _, changes = fix_text(r"$\dfrac{1}{2}$ 和 $\dfrac{3}{4}$")
        self.assertEqual(changes, [("dfrac-to-frac", 2)])

    def test_idempotent(self):
        once, _ = fix_text(r"$\dfrac{1}{2}$")
        twice, changes = fix_text(once)
        self.assertEqual(once, r"$\frac{1}{2}$")
        self.assertEqual(once, twice)
        self.assertEqual(changes, [])


class TestScanText(unittest.TestCase):
    def test_line_numbers(self):
        text = "第一行\n上课时间 8：00\n无问题\n8：30 上课"
        hits = scan_text(text)
        self.assertEqual(
            hits,
            [(2, "digit-colon-digit", "8：00"),
             (4, "digit-colon-digit", "8：30")],
        )

    def test_empty(self):
        self.assertEqual(scan_text("没有任何问题"), [])


class TestFixFile(unittest.TestCase):
    def test_write(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.tex"
            p.write_text("8：00", encoding="utf-8")
            changed, _ = fix_file(p, write=True)
            self.assertTrue(changed)
            self.assertEqual(p.read_text(encoding="utf-8"), "8:00")

    def test_no_write_keeps_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.tex"
            p.write_text("8：00", encoding="utf-8")
            changed, _ = fix_file(p, write=False)
            self.assertTrue(changed)
            self.assertEqual(p.read_text(encoding="utf-8"), "8：00")

    def test_iter_target_files(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "a.tex").write_text("x", encoding="utf-8")
            (Path(d) / "b.txt").write_text("x", encoding="utf-8")
            files = iter_target_files([d], extensions=(".tex",))
            self.assertEqual([f.name for f in files], ["a.tex"])


class TestFixtures(unittest.TestCase):
    """端到端：修正前样例 → 修正后样例。"""

    FIXTURES = Path(__file__).resolve().parent / "fixtures"

    def test_before_after(self):
        before = (self.FIXTURES / "sample_before.tex").read_text(encoding="utf-8")
        after = (self.FIXTURES / "sample_after.tex").read_text(encoding="utf-8")
        fixed, _ = fix_text(before)
        self.assertEqual(fixed, after)

    def test_after_is_stable(self):
        after = (self.FIXTURES / "sample_after.tex").read_text(encoding="utf-8")
        fixed, changes = fix_text(after)
        self.assertEqual(fixed, after)
        self.assertEqual(changes, [])


class TestRulesRegistry(unittest.TestCase):
    def test_rules_unique_and_compiled(self):
        names = [r.name for r in RULES]
        self.assertEqual(len(names), len(set(names)), "规则名必须唯一")
        for rule in RULES:
            self.assertTrue(rule.name and rule.description)
            self.assertTrue(hasattr(rule.pattern, "subn"))

    def test_apply_rules_matches_fix_text(self):
        text = "8：00"
        self.assertEqual(apply_rules(text), fix_text(text))


if __name__ == "__main__":
    unittest.main(verbosity=2)

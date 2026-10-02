"""tools/test_check_answers.py —— check_answers 非选择题答案对应测试。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools import check_answers

HEAD = "\\chapter{2000年测试}\n\\begin{enumerate}\n"

BODY2 = """\\item
%% number: 1
%% typeId: 6
%% type: 计算题
%% body:
题干
\\begin{enumerate}
\\item
求 a
\\item
求 b
\\end{enumerate}
%% answer:
"""


def _write(tmp: Path, text: str) -> Path:
    p = tmp / "t.tex"
    p.write_text(text, encoding="utf-8")
    return p


class TestCheckAnswers(unittest.TestCase):
    def test_ok(self):
        text = HEAD + BODY2 + (
            "\\jdanswer{\n\\begin{enumerate}\n\\item\n甲\n\\item\n乙\n\\end{enumerate}\n}\n"
            "%% memo:\n\\memoanswer{解}\n\\end{enumerate}\n")
        with tempfile.TemporaryDirectory() as d:
            errs, warns = check_answers.check_file(_write(Path(d), text))
            self.assertEqual(errs, [])

    def test_missing_jdanswer(self):
        # 有 \tkanswer 但多小问缺 \jdanswer
        text = HEAD + BODY2 + (
            "\\tkanswer{甲}\n%% memo:\n\\memoanswer{解}\n\\end{enumerate}\n")
        with tempfile.TemporaryDirectory() as d:
            errs, _ = check_answers.check_file(_write(Path(d), text))
            self.assertTrue(any("缺 \\jdanswer" in e for e in errs))

    def test_single_fill_tkanswer_ok(self):
        text = HEAD + (
            "\\item\n%% number: 1\n%% typeId: 3\n%% type: 填空题\n%% body:\n"
            "质量为 \\tkanswer{2}\\Ug。\n%% answer: 2\n%% memo:\n\\memoanswer{解}\n"
            "\\end{enumerate}\n")
        with tempfile.TemporaryDirectory() as d:
            errs, _ = check_answers.check_file(_write(Path(d), text))
            self.assertEqual(errs, [])

    def test_no_answer_command(self):
        text = HEAD + (
            "\\item\n%% number: 1\n%% typeId: 6\n%% type: 计算题\n%% body:\n题干\n"
            "%% answer:\n%% memo:\n\\memoanswer{解}\n\\end{enumerate}\n")
        with tempfile.TemporaryDirectory() as d:
            errs, _ = check_answers.check_file(_write(Path(d), text))
            self.assertTrue(any("缺答案命令" in e for e in errs))


if __name__ == "__main__":
    unittest.main()

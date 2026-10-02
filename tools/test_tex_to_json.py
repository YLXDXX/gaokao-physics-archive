"""tools/test_tex_to_json.py —— tex_to_json 反向抽取测试。"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools import tex_to_json

TEX = """\\ifdefined\\gkver\\else\\def\\gkver{student}\\fi
\\documentclass[\\gkver]{gaokaozhenti}
\\begin{document}
\\chapter{2000年测试}
\\begin{enumerate}
\\item
%% number: 1
%% paperName: 2000年测试第 1 题 4 分
%% typeId: 1
%% type: 单选题
%% chapter: 光学
%% point: 光电效应
%% method: 无
%% score: 4
%% degree: 600
%% duplicateId: 0
%% body:
题干（  ）
\\fourchoices[answer=B]
{甲}
{乙}
{丙}
{丁}
%% answer: B
%% memo:
\\memoanswer{解一}
\\item
%% number: 2
%% paperName: 2000年测试第 2 题 10 分
%% typeId: 6
%% type: 计算题
%% chapter: 力学
%% point: 牛顿定律
%% method: 无
%% score: 10
%% degree: 500
%% duplicateId: 0
%% body:
题干二
\\begin{enumerate}
\\item
求 a
\\end{enumerate}
%% answer:
\\jdanswer{a}
%% memo:
\\memoanswer{解二}
\\end{enumerate}
\\end{document}
"""


class TestTexToJson(unittest.TestCase):
    def _parse(self, text: str) -> dict:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "测试.tex"
            p.write_text(text, encoding="utf-8")
            return tex_to_json.parse_paper(p)

    def test_items(self):
        data = self._parse(TEX)
        self.assertEqual(data["chapter"], "2000年测试")
        self.assertEqual(len(data["items"]), 2)
        q1 = data["items"][0]
        self.assertEqual(q1["number"], "1")
        self.assertIn("题干", q1["body"])
        self.assertIn("\\fourchoices", q1["body"])
        self.assertIn("解一", q1["memo"])
        q2 = data["items"][1]
        self.assertIn("\\jdanswer", q2["answer"])

    def test_compare_ok(self):
        data = self._parse(TEX)
        with tempfile.TemporaryDirectory() as d:
            ref = Path(d) / "ref.json"
            ref.write_text(json.dumps({"items": [
                {"number": 1, "paperName": "2000年测试第 1 题 4 分", "typeId": 1,
                 "type": "单选题", "chapter": "光学", "point": "光电效应", "method": "无",
                 "score": 4, "degree": 600, "duplicateId": 0, "answer": "<p>B</p>"},
                {"number": 2, "paperName": "2000年测试第 2 题 10 分", "typeId": 6,
                 "type": "计算题", "chapter": "力学", "point": "牛顿定律", "method": "无",
                 "score": 10, "degree": 500, "duplicateId": 0, "answer": "a"},
            ]}, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(tex_to_json.compare(data, ref), [])

    def test_compare_mismatch(self):
        data = self._parse(TEX)
        with tempfile.TemporaryDirectory() as d:
            ref = Path(d) / "ref.json"
            ref.write_text(json.dumps({"items": [
                {"number": 1, "paperName": "x", "typeId": 1, "type": "单选题",
                 "chapter": "光学", "point": "光电效应", "method": "无", "score": 4,
                 "degree": 600, "duplicateId": 0, "answer": "<p>B</p>"},
            ]}, ensure_ascii=False), encoding="utf-8")
            errs = tex_to_json.compare(data, ref)
            self.assertTrue(any("paperName" in e for e in errs))


if __name__ == "__main__":
    unittest.main()

"""tools/test_check_meta.py —— check_meta 元数据/JSON 一致性校验测试。"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools import check_meta

TEX = """\\chapter{{2000年测试}}
\\begin{{enumerate}}
\\item
%% number: 1
%% paperName: {pname}
%% typeId: 1
%% type: 单选题
%% chapter: 力学
%% point: 速度
%% method: 无
%% score: {score}
%% degree: 600
%% duplicateId: 0
%% body:
题干（  ）
%% answer: {ans}
%% memo:
\\memoanswer{{解}}
\\end{{enumerate}}
"""


RENUM_TEX = """\\chapter{2000年测试}
%% sourceNumbers: 17, 19
\\begin{enumerate}
\\item
%% number: 1
%% paperName: 2000年测试第 17 题 4 分
%% typeId: 2
%% type: 多选题
%% chapter: 力学
%% point: 速度
%% method: 无
%% score: 4
%% degree: 600
%% duplicateId: 0
%% body:
题干（  ）
%% answer: AD
%% memo:
\\memoanswer{解}
\\item
%% number: 2
%% paperName: 2000年测试第 19 题 6 分
%% typeId: 1
%% type: 单选题
%% chapter: 电学
%% point: 电流
%% method: 无
%% score: 6
%% degree: 500
%% duplicateId: 0
%% body:
题干（  ）
%% answer: C
%% memo:
\\memoanswer{解}
\\end{enumerate}
"""


class TestCheckMeta(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        (self.tmp / "试卷/2000/测试").mkdir(parents=True)
        (self.tmp / "JSON/2000").mkdir(parents=True)
        self.tex = self.tmp / "试卷/2000/测试/测试.tex"
        self._old_root = check_meta.ROOT
        check_meta.ROOT = self.tmp

    def tearDown(self):
        check_meta.ROOT = self._old_root
        self._tmp.cleanup()

    def _write(self, score="4", ans="B", pname="2000年测试第 1 题 4 分",
               json_score=4, json_ans="<p>B</p>", json_pname="2000年测试第 1 题 4 分"):
        self.tex.write_text(TEX.format(pname=pname, score=score, ans=ans), encoding="utf-8")
        item = dict(number=1, paperName=json_pname, typeId=1, type="单选题", chapter="力学",
                    point="速度", method="无", score=json_score, degree=600,
                    duplicateId=0, answer=json_ans, body="", memo="")
        (self.tmp / "JSON/2000/2000_测试.json").write_text(
            json.dumps({"items": [item]}, ensure_ascii=False), encoding="utf-8")

    def test_ok(self):
        self._write()
        errs, _ = check_meta.check_file(self.tex)
        self.assertEqual(errs, [])

    def test_score_mismatch(self):
        self._write(score="5", json_score=4)
        errs, _ = check_meta.check_file(self.tex)
        self.assertTrue(any("score" in e for e in errs))

    def test_answer_html_tags_ignored(self):
        self._write(json_ans='<p><span style="font-family:Book Antiqua">B</span></p>')
        errs, _ = check_meta.check_file(self.tex)
        self.assertEqual(errs, [])

    def test_answer_mismatch(self):
        self._write(ans="A", json_ans="<p>B</p>")
        errs, _ = check_meta.check_file(self.tex)
        self.assertTrue(any("answer" in e for e in errs))

    def test_missing_json(self):
        self.tex.write_text(TEX.format(pname="x", score="4", ans="B"), encoding="utf-8")
        errs, warns = check_meta.check_file(self.tex)
        self.assertEqual(errs, [])
        self.assertTrue(warns)

    def test_source_numbers_mapping(self):
        """--renumber：tex %% number=1..N，按 %% sourceNumbers 映射回 JSON 原题号。"""
        self.tex.write_text(RENUM_TEX, encoding="utf-8")
        its = [
            dict(number=17, paperName="2000年测试第 17 题 4 分", typeId=2, type="多选题",
                 chapter="力学", point="速度", method="无", score=4, degree=600,
                 duplicateId=0, answer="<p>AD</p>", body="", memo=""),
            dict(number=19, paperName="2000年测试第 19 题 6 分", typeId=1, type="单选题",
                 chapter="电学", point="电流", method="无", score=6, degree=500,
                 duplicateId=0, answer="<p>C</p>", body="", memo=""),
        ]
        (self.tmp / "JSON/2000/2000_测试.json").write_text(
            json.dumps({"items": its}, ensure_ascii=False), encoding="utf-8")
        errs, _ = check_meta.check_file(self.tex)
        self.assertEqual(errs, [])

    def test_source_numbers_missing_item(self):
        self.tex.write_text(RENUM_TEX, encoding="utf-8")
        (self.tmp / "JSON/2000/2000_测试.json").write_text(
            json.dumps({"items": [dict(number=17, paperName="x", typeId=1, type="单选题",
                                       chapter="", point="", method="", score=4,
                                       degree=600, duplicateId=0, answer="<p>AD</p>",
                                       body="", memo="")]}, ensure_ascii=False),
            encoding="utf-8")
        errs, _ = check_meta.check_file(self.tex)
        self.assertTrue(any("19" in e for e in errs))


if __name__ == "__main__":
    unittest.main()

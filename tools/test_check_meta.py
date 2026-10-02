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


if __name__ == "__main__":
    unittest.main()

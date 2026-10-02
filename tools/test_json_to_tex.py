"""tools/test_json_to_tex.py —— json_to_tex 初稿生成的单元测试。"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools import json_to_tex


def _build(tmp: Path, items: list[dict], imgs: dict[str, bytes] | None = None) -> tuple[Path, Path]:
    """在 tmp 下构造 JSON/2000/2000_测试.json 与图片，返回 (json_path, out_dir)。"""
    jdir = tmp / "JSON" / "2000"
    jdir.mkdir(parents=True, exist_ok=True)
    for rel, data in (imgs or {}).items():
        f = jdir / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(data)
    jp = jdir / "2000_测试.json"
    jp.write_text(json.dumps({"items": items}, ensure_ascii=False), encoding="utf-8")
    out = tmp / "试卷" / "2000" / "测试"
    return jp, out


def _gen(tmp: Path, items, imgs=None, **kw) -> str:
    jp, out = _build(tmp, items, imgs)
    json_to_tex.process_paper(jp, out, force=True, **kw)
    return (out / "测试.tex").read_text(encoding="utf-8")


def _choice(**kw) -> dict:
    d = dict(number=1, paperName="第 1 题", typeId=1, type="单选题", chapter="",
             point="", method="", score=4, degree=600, duplicateId=0,
             body="", answer="<p>B</p>", memo="<p>解</p>")
    d.update(kw)
    return d


class TestJsonToTex(unittest.TestCase):
    def test_missing_memo_placeholder(self):
        with tempfile.TemporaryDirectory() as d:
            tex = _gen(Path(d), [_choice(memo=None,
                        body="<p>题干（  ）</p><p>（A）甲</p><p>（B）乙</p><p>（C）丙</p><p>（D）丁</p>")])
            self.assertIn("\\memoanswer{", tex)
            self.assertIn(json_to_tex.MEMO_PLACEHOLDER, tex)

    def test_nonchoice_jdanswer_enumerate(self):
        with tempfile.TemporaryDirectory() as d:
            it = dict(number=2, paperName="第 2 题", typeId=6, type="计算题", chapter="",
                      point="", method="", score=10, degree=500, duplicateId=0,
                      body="<p>题干</p><p>（1）求 a</p><p>（2）求 b</p>",
                      answer="<p>（1）甲</p><p>（2）乙</p>", memo="<p>解</p>")
            tex = _gen(Path(d), [it])
            self.assertIn("\\jdanswer{", tex)
            self.assertIn("\\begin{enumerate}", tex)
            self.assertIn("甲", tex)

    def test_image_options(self):
        img = b"x"
        imgs = {f"2000_测试/tiku_images/{n}": img for n in ["a.png", "b.png", "c.png", "d.png"]}
        body = ("<p>题干（  ）</p>"
                + "".join(f'<p>（{L}）<img src="2000_测试/tiku_images/{f}"></p>'
                          for L, f in zip("ABCD", ["a.png", "b.png", "c.png", "d.png"])))
        with tempfile.TemporaryDirectory() as d:
            tex = _gen(Path(d), [_choice(answer="<p>C</p>", body=body)], imgs)
            self.assertIn("ispicture=true", tex)
            self.assertIn("\\fourchoices[answer=C", tex)

    def test_multi_figure_twopicture(self):
        imgs = {"2000_测试/tiku_images/a.png": b"x", "2000_测试/tiku_images/b.png": b"x"}
        body = ('<p>题干<img src="2000_测试/tiku_images/a.png">'
                '<img src="2000_测试/tiku_images/b.png">（  ）</p>'
                "<p>（A）甲</p><p>（B）乙</p><p>（C）丙</p><p>（D）丁</p>")
        with tempfile.TemporaryDirectory() as d:
            tex = _gen(Path(d), [_choice(body=body)], imgs)
            self.assertIn("\\twopicture", tex)

    def test_renumber_and_source(self):
        with tempfile.TemporaryDirectory() as d:
            items = [_choice(number=17, body="<p>题（  ）</p><p>（A）甲</p><p>（B）乙</p>"
                                                "<p>（C）丙</p><p>（D）丁</p>"),
                     _choice(number=19, typeId=2, type="多选题", answer="<p>AD</p>",
                             body="<p>题（  ）</p><p>（A）甲</p><p>（B）乙</p>"
                                  "<p>（C）丙</p><p>（D）丁</p>")]
            tex = _gen(Path(d), items, renumber=True)
            self.assertIn("%% number: 1", tex)
            self.assertIn("%% number: 2", tex)
            self.assertIn("%% sourceNumbers: 17, 19", tex)

    def test_math_conversion(self):
        with tempfile.TemporaryDirectory() as d:
            tex = _gen(Path(d), [_choice(body="<p>速度 \\(v\\) 与 <em>a</em><sub>1</sub> （  ）</p>"
                                              "<p>（A）甲</p><p>（B）乙</p>")])
            self.assertIn("$v$", tex)
            self.assertIn("$a_{1}$", tex)

    def test_fullwidth_options(self):
        with tempfile.TemporaryDirectory() as d:
            tex = _gen(Path(d), [_choice(answer="<p>D</p>",
                        body="<p>题（  ）</p><p>（A）甲</p><p>（B）乙</p>"
                             "<p>（C）丙</p><p>（D）丁</p>")])
            self.assertIn("\\fourchoices[answer=D]", tex)
            self.assertIn("{丁}", tex)


if __name__ == "__main__":
    unittest.main()

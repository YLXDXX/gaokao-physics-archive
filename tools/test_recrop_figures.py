#!/usr/bin/env python3
"""tools/recrop_figures.py 的单元测试（纯函数：子图分割 / 文档引用解析）。"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image, ImageDraw

from tools import recrop_figures as rf
from tools.recrop_figures import (cmd_apply, cmd_labels, cmd_preview,
                                  make_sheets, referenced_figs,
                                  split_subfigures, splitpicture_detect,
                                  splitpicture_features, splitpicture_panels)


class _FakeProc:
    def __init__(self, returncode=0, stdout="{}", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _detect_json(figures=None, labels=None):
    return json.dumps({
        "count": len(figures or []),
        "rects": [{"x": x, "y": y, "w": w, "h": h} for (x, y, w, h) in (figures or [])],
        "labels": labels or [],
        "written": [],
    })


def _img_with_blocks(blocks, size=(800, 400)):
    im = Image.new("L", size, 255)
    d = ImageDraw.Draw(im)
    for (x, y, w, h) in blocks:
        d.rectangle([x, y, x + w, y + h], fill=0)
    return im


class TestSplitSubfigures(unittest.TestCase):
    def test_two_in_a_row(self):
        im = _img_with_blocks([(40, 60, 150, 200), (450, 60, 150, 200)])
        boxes = split_subfigures(im, min_gap=25, min_size=80)
        self.assertEqual(len(boxes), 2)
        self.assertLess(boxes[0][0], boxes[1][0])  # 从左到右

    def test_two_by_two(self):
        im = _img_with_blocks([(40, 30, 150, 120), (450, 30, 150, 120),
                              (40, 250, 150, 120), (450, 250, 150, 120)])
        boxes = split_subfigures(im, min_gap=20, min_size=60)
        self.assertEqual(len(boxes), 4)
        # 阅读顺序：上排左、上排右、下排左、下排右
        self.assertLess(boxes[0][1], boxes[2][1])

    def test_single(self):
        im = _img_with_blocks([(100, 100, 200, 200)])
        boxes = split_subfigures(im, min_gap=25, min_size=80)
        self.assertEqual(len(boxes), 1)


class TestReferencedFigs(unittest.TestCase):
    def test_parses(self):
        with tempfile.TemporaryDirectory() as tmp:
            tex = Path(tmp) / "a.tex"
            tex.write_text(
                r"\onepicture[w=3cm]{figs/a.jpg}" "\n"
                r"\fourpicture{figs/b.jpg}{figs/c.png}" "\n"
                r"\onepicture{TikZ/x.pdf}" "\n",
                encoding="utf-8",
            )
            refs = referenced_figs(tex)
        self.assertEqual(refs, ["a", "b", "c"])


class TestSplitpictureDetect(unittest.TestCase):
    def test_parses_figures_and_labels(self):
        payload = _detect_json(
            figures=[(1, 2, 3, 4)],
            labels=[{"x": 10, "y": 20, "w": 30, "h": 40,
                     "kind": "label", "text": "甲"}],
        )
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return _FakeProc(stdout=payload)

        with mock.patch.object(rf.subprocess, "run", side_effect=fake_run):
            res = splitpicture_detect(Path("p.jpg"), "splitpicture", mode="panels")

        self.assertEqual(res["figures"], [(1, 2, 3, 4)])
        self.assertEqual(res["labels"][0]["text"], "甲")
        self.assertIn("--panels", captured["cmd"])
        self.assertIn("--json", captured["cmd"])

    def test_options_mode(self):
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return _FakeProc(stdout=_detect_json())

        with mock.patch.object(rf.subprocess, "run", side_effect=fake_run):
            splitpicture_detect(Path("p.jpg"), "splitpicture", mode="options")
        self.assertIn("--options", captured["cmd"])

    def test_failure_returns_none(self):
        with mock.patch.object(rf.subprocess, "run",
                               return_value=_FakeProc(returncode=1)):
            self.assertIsNone(splitpicture_detect(Path("p.jpg"), "splitpicture"))

    def test_panels_wrapper(self):
        def fake_run(cmd, **kwargs):
            return _FakeProc(stdout=_detect_json(figures=[(5, 6, 7, 8)]))

        with mock.patch.object(rf.subprocess, "run", side_effect=fake_run):
            self.assertEqual(splitpicture_panels(Path("p.jpg"), "splitpicture"),
                             [(5, 6, 7, 8)])


class TestCmdLabels(unittest.TestCase):
    def test_writes_labels_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "s.png"
            Image.new("L", (120, 120), 255).save(src)
            out = Path(tmp) / "labels.json"
            payload = _detect_json(
                figures=[(1, 2, 3, 4)],
                labels=[{"x": 10, "y": 20, "w": 30, "h": 40,
                         "kind": "label", "text": ""}],
            )
            with mock.patch.object(rf.subprocess, "run",
                                   return_value=_FakeProc(stdout=payload)):
                rc = cmd_labels(src, "panels", out, None, "splitpicture")
            self.assertEqual(rc, 0)
            saved = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(saved, [{"x": 10, "y": 20, "w": 30, "h": 40}])


def _fake_split_factory(seen=None, all_white=False):
    """模拟 ``splitpicture split --json``：先按 --labels-file 把标签框涂白（原生擦除），
    再按 --rects-file 逐矩形裁剪 -i 并写 output，返回带 items 的 JSON（与 v0.3 一致）。
    all_white=True 时模拟 --trim 跳过全白块。"""
    def fake_split(cmd, **kwargs):
        if seen is not None:
            seen["cmd"] = list(cmd)
        if "--capabilities" in cmd:  # P3 能力预检
            return _FakeProc(stdout=json.dumps(
                {"version": "0.4", "features": ["json-items", "labels-file", "panels", "tight"]}))
        src_arg = Path(cmd[cmd.index("-i") + 1])
        rects = json.loads(Path(cmd[cmd.index("--rects-file") + 1]).read_text(encoding="utf-8"))
        labels = []
        if "--labels-file" in cmd:
            labels = json.loads(
                Path(cmd[cmd.index("--labels-file") + 1]).read_text(encoding="utf-8"))
        if seen is not None:
            seen["rects"] = rects
            seen["labels"] = labels
        items, written = [], []
        if all_white:
            for r in rects:
                items.append({"rect": [r["x"], r["y"], r["w"], r["h"]],
                              "output": "", "skipped": True, "ok": False})
            return _FakeProc(stdout=json.dumps(
                {"count": 0, "written": [], "items": items}))
        im = Image.open(src_arg).convert("RGB")
        if labels:
            dd = ImageDraw.Draw(im)
            for r in labels:
                dd.rectangle([r["x"], r["y"], r["x"] + r["w"], r["y"] + r["h"]],
                             fill=(255, 255, 255))
        for r in rects:
            out = Path(r["output"])
            out.parent.mkdir(parents=True, exist_ok=True)
            im.crop((r["x"], r["y"], r["x"] + r["w"], r["y"] + r["h"])).save(out)
            items.append({"rect": [r["x"], r["y"], r["w"], r["h"]],
                          "output": str(out), "skipped": False, "ok": True})
            written.append(str(out))
        im.close()
        return _FakeProc(stdout=json.dumps(
            {"count": len(written), "written": written, "items": items}))
    return fake_split


class TestCmdApplyEraseLabels(unittest.TestCase):
    def _make_source(self, root: Path) -> Path:
        img = Image.new("L", (200, 200), 255)
        ImageDraw.Draw(img).rectangle([50, 50, 70, 70], fill=0)  # “标签”
        src = root / "src.png"
        img.save(src)
        return src

    def test_erase_labels_merges_and_pads(self):
        with tempfile.TemporaryDirectory() as tmp:
            troot = Path(tmp)
            src = self._make_source(troot)

            recipe = {
                "entries": [{
                    "source": str(src),           # 绝对路径
                    "erase": [[5, 5, 4, 4]],       # 手工擦除
                    "erase_labels": "panels",      # 自动检测标签
                    "crops": [{"rect": [0, 0, 200, 200], "target": "figs/out.png"}],
                }]
            }
            recipe_path = troot / ".recrop.json"
            recipe_path.write_text(json.dumps(recipe), encoding="utf-8")

            detected = {"figures": [(0, 0, 200, 200)],
                        "labels": [{"x": 50, "y": 50, "w": 20, "h": 20,
                                    "kind": "label", "text": ""}]}
            seen = {}
            with mock.patch.object(rf, "ROOT", troot), \
                 mock.patch.object(rf, "splitpicture_detect", return_value=detected), \
                 mock.patch.object(rf.subprocess, "run",
                                   side_effect=_fake_split_factory(seen=seen)):
                rc = cmd_apply(recipe_path, "splitpicture")

            self.assertEqual(rc, 0)
            out = troot / "figs" / "out.png"
            self.assertTrue(out.is_file())
            # 原生擦除：splitpicture 收到 --labels-file = 手工框 + 外扩后的自动标签框
            self.assertEqual(seen["labels"],
                             [{"x": 5, "y": 5, "w": 4, "h": 4},
                              {"x": 46, "y": 46, "w": 28, "h": 28}])
            # 标签处及其外扩边应被擦白
            with Image.open(out) as im:
                self.assertEqual(im.convert("L").getpixel((60, 60)), 255)
                self.assertEqual(im.convert("L").getpixel((46, 60)), 255)

    def test_output_extension_matches_target(self):
        """逐矩形 output 保留目标扩展名，避免 PNG 字节写进 .jpg。"""
        with tempfile.TemporaryDirectory() as tmp:
            troot = Path(tmp)
            src = self._make_source(troot)
            # 源为 PNG、目标为 .jpg：过去会写出 PNG 字节到 .jpg
            recipe = {"entries": [{
                "source": str(src),
                "crops": [{"rect": [0, 0, 200, 200], "target": "figs/out.jpg"}],
            }]}
            recipe_path = troot / ".recrop.json"
            recipe_path.write_text(json.dumps(recipe), encoding="utf-8")
            seen = {}
            with mock.patch.object(rf, "ROOT", troot), \
                 mock.patch.object(rf.subprocess, "run",
                                   side_effect=_fake_split_factory(seen=seen)):
                rc = cmd_apply(recipe_path, "splitpicture")

            self.assertEqual(rc, 0)
            # splitpicture 收到的 output 应以 .jpg 结尾（编码器据此选择）
            self.assertTrue(seen["rects"][0]["output"].endswith(".jpg"))
            self.assertTrue((troot / "figs" / "out.jpg").is_file())

    def test_all_white_skip_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            troot = Path(tmp)
            src = self._make_source(troot)
            recipe = {"entries": [{
                "source": str(src),
                "crops": [{"rect": [0, 0, 200, 200], "target": "figs/out.png"}],
            }]}
            recipe_path = troot / ".recrop.json"
            recipe_path.write_text(json.dumps(recipe), encoding="utf-8")
            with mock.patch.object(rf, "ROOT", troot), \
                 mock.patch.object(rf.subprocess, "run",
                                   side_effect=_fake_split_factory(all_white=True)):
                rc = cmd_apply(recipe_path, "splitpicture")
            self.assertEqual(rc, 1)
            self.assertFalse((troot / "figs" / "out.png").is_file())

    def test_trim_passes_flag_to_splitpicture(self):
        with tempfile.TemporaryDirectory() as tmp:
            troot = Path(tmp)
            src = self._make_source(troot)
            recipe = {
                "trim": {"padding": 6, "threshold": 230},
                "entries": [{
                    "source": str(src),
                    "crops": [{"rect": [0, 0, 200, 200], "target": "figs/out.png"}],
                }],
            }
            recipe_path = troot / ".recrop.json"
            recipe_path.write_text(json.dumps(recipe), encoding="utf-8")
            seen = {}

            with mock.patch.object(rf, "ROOT", troot), \
                 mock.patch.object(rf.subprocess, "run",
                                   side_effect=_fake_split_factory(seen=seen)):
                rc = cmd_apply(recipe_path, "splitpicture")

            self.assertEqual(rc, 0)
            self.assertIn("--trim", seen["cmd"])
            self.assertIn("--white-padding", seen["cmd"])
            self.assertEqual(seen["cmd"][seen["cmd"].index("--white-padding") + 1], "6")
            self.assertEqual(seen["cmd"][seen["cmd"].index("--threshold") + 1], "230")


class TestCmdPreview(unittest.TestCase):
    def test_overlay_uses_recipe_rects_and_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            troot = Path(tmp)
            src = troot / "src.png"
            Image.new("RGB", (120, 80), (255, 255, 255)).save(src)
            recipe = {"entries": [{
                "source": str(src),
                "erase": [[5, 5, 10, 10]],
                "crops": [{"rect": [0, 0, 60, 40], "target": "figs/a.jpg"},
                          {"rect": [60, 0, 60, 40], "target": "figs/b.jpg"}],
            }]}
            rp = troot / ".recrop.json"
            rp.write_text(json.dumps(recipe), encoding="utf-8")
            seen = {}

            def fake(cmd, **kwargs):
                if "--capabilities" in cmd:
                    return _FakeProc(
                        stdout='{"version":"0.4","features":["json-items","labels-file"]}')
                seen["cmd"] = list(cmd)
                p = Path(cmd[cmd.index("--preview") + 1])
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(b"\x89PNG\r\n\x1a\n")
                return _FakeProc(stdout='{"rects":[],"labels":[]}')

            with mock.patch.object(rf, "ROOT", troot), \
                 mock.patch.object(rf.subprocess, "run", side_effect=fake):
                rc = cmd_preview(rp, None, "splitpicture")

            self.assertEqual(rc, 0)
            self.assertIn("--rects-file", seen["cmd"])
            self.assertIn("--labels-file", seen["cmd"])
            self.assertTrue((troot / "crop_preview" / "src.splitpicture.png").is_file())

    def test_rejects_old_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            troot = Path(tmp)
            src = troot / "s.png"
            Image.new("RGB", (10, 10), (255, 255, 255)).save(src)
            rp = troot / ".recrop.json"
            rp.write_text(json.dumps({"entries": [{
                "source": str(src),
                "crops": [{"rect": [0, 0, 5, 5], "target": "figs/a.jpg"}]}]}),
                encoding="utf-8")
            with mock.patch.object(rf, "ROOT", troot), \
                 mock.patch.object(rf.subprocess, "run", return_value=_FakeProc(
                     stdout='{"version":"0.3","features":["json-items"]}')):
                rc = cmd_preview(rp, None, "splitpicture")
            self.assertEqual(rc, 1)


class TestSplitpictureFeatures(unittest.TestCase):
    def test_parses_features(self):
        with mock.patch.object(rf.subprocess, "run", return_value=_FakeProc(
                stdout='{"version":"0.4","features":["json-items","tight"]}')):
            self.assertEqual(splitpicture_features("splitpicture"), {"json-items", "tight"})

    def test_none_on_old_version(self):
        with mock.patch.object(rf.subprocess, "run",
                               return_value=_FakeProc(returncode=1)):
            self.assertIsNone(splitpicture_features("splitpicture"))

    def test_panels_tight_passthrough(self):
        captured = {}

        def fake(cmd, **kwargs):
            captured["cmd"] = list(cmd)
            return _FakeProc(stdout='{"rects":[{"x":0,"y":0,"w":5,"h":5}],"labels":[]}')

        with mock.patch.object(rf.subprocess, "run", side_effect=fake):
            splitpicture_panels(Path("p.jpg"), "splitpicture", tight=True)
        self.assertIn("--tight", captured["cmd"])
        with mock.patch.object(rf.subprocess, "run", side_effect=fake):
            splitpicture_panels(Path("p.jpg"), "splitpicture", tight=False)
        self.assertNotIn("--tight", captured["cmd"])


class TestMakeSheetsEraseRedBox(unittest.TestCase):
    def test_left_panel_marks_erase_with_red_box(self):
        with tempfile.TemporaryDirectory() as tmp:
            troot = Path(tmp)
            src = troot / "src.png"
            Image.new("RGB", (100, 100), (255, 255, 255)).save(src)
            tgt = troot / "lesson" / "figs" / "out.jpg"
            tgt.parent.mkdir(parents=True)
            Image.new("RGB", (50, 50), (255, 255, 255)).save(tgt)
            (troot / "lesson" / "lesson.tex").write_text(
                r"\onepicture[w=3cm]{figs/out.jpg}", encoding="utf-8")
            applied = [{
                "source": src,
                "crops": [({"rect": [0, 0, 50, 50]}, "lesson/figs/out.jpg")],
                "erase": [[10, 10, 20, 20]],
            }]
            with mock.patch.object(rf, "ROOT", troot):
                make_sheets(applied)
            sheet = troot / "lesson" / "crop_compare" / "lesson_裁剪前后.png"
            self.assertTrue(sheet.is_file())
            im = Image.open(sheet).convert("RGB")
            px = im.load()
            found = any(px[x, y][0] > 200 and px[x, y][1] < 80 and px[x, y][2] < 80
                        for x in range(im.width) for y in range(0, 320, 2))
            self.assertTrue(found, "对比图左栏未画出擦除红框")


if __name__ == "__main__":
    unittest.main()

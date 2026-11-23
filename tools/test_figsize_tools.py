"""tools/test_figsize_tools.py —— plan/apply/check 小型端到端测试。"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from tools import figsize_apply, figsize_automap, figsize_check, figsize_fix_refs, figsize_merge_fallback, figsize_plan, figsize_status


class TestFigsizeTools(unittest.TestCase):
    def test_plan_apply_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            unit = root / "试卷" / "2000" / "测试"
            (unit / "figs").mkdir(parents=True)
            Image.new("RGB", (100, 50), "white").save(unit / "figs" / "a.png")
            tex = unit / "测试.tex"
            tex.write_text("\\onepicture[w=9cm]{figs/a.png}\n", encoding="utf-8")
            (unit / "figures.map.json").write_text(json.dumps({
                "entries": [{"target": "试卷/2000/测试/figs/a.png", "candidate": 1}]
            }), encoding="utf-8")
            cand = unit / "cand.json"
            cand.write_text(json.dumps({
                "source_pdf": "OriginPDF/2000/2000_测试.pdf",
                "figures": [{"page": 1, "kind": "vector", "width_cm": 4.0,
                             "height_cm": 2.0, "rect_norm": [0, 0, 1, 1]}],
            }), encoding="utf-8")

            with mock.patch.object(figsize_plan, "ROOT", root):
                rc = figsize_plan.main([str(unit), "--candidates", str(cand), "--write"])
            self.assertEqual(rc, 0)
            manifest = json.loads((unit / "figures.manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["entries"][0]["width_cm"], 4.0)

            with mock.patch.object(figsize_apply, "ROOT", root):
                figsize_apply.main([str(unit), "--write"])
            self.assertIn("w=4.00cm", tex.read_text(encoding="utf-8"))

            with mock.patch.object(figsize_check, "ROOT", root):
                errs = figsize_check.check_unit(unit)
            self.assertEqual(errs, [])

            # pHYs 被改坏后应能检出
            Image.open(unit / "figs" / "a.png").save(
                unit / "figs" / "a.png", dpi=(50, 50))
            with mock.patch.object(figsize_check, "ROOT", root):
                errs = figsize_check.check_unit(unit)
            self.assertTrue(any("pHYs" in e for e in errs), errs)

    def test_plan_merges_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            unit = root / "试卷" / "2000" / "测试"
            (unit / "figs").mkdir(parents=True)
            Image.new("RGB", (100, 50), "white").save(unit / "figs" / "a.png")
            (unit / "figures.map.json").write_text(json.dumps({
                "entries": [{
                    "target": "试卷/2000/测试/figs/a.png",
                    "merge": [1, 2],
                }]
            }), encoding="utf-8")
            cand = unit / "cand.json"
            cand.write_text(json.dumps({
                "source_pdf": "OriginPDF/2000/2000_测试.pdf",
                "figures": [
                    {"page": 1, "kind": "vector", "width_cm": 2.0,
                     "height_cm": 2.0, "rect_norm": [0, 0, 0.5, 0.5]},
                    {"page": 1, "kind": "vector", "width_cm": 2.0,
                     "height_cm": 2.0, "rect_norm": [0.5, 0, 1.0, 0.5]},
                ],
            }), encoding="utf-8")

            with mock.patch.object(figsize_plan, "ROOT", root):
                rc = figsize_plan.main([str(unit), "--candidates", str(cand), "--write"])
            self.assertEqual(rc, 0)
            manifest = json.loads((unit / "figures.manifest.json").read_text(encoding="utf-8"))
            entry = manifest["entries"][0]
            self.assertEqual(entry["width_cm"], 4.0)
            self.assertEqual(entry["height_cm"], 2.0)
            self.assertEqual(entry["status"], "auto")

    def test_status_skips_done_and_flags_todo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            done = root / "试卷" / "2000" / "已完成"
            todo = root / "试卷" / "2000" / "待处理"
            (done / "figs").mkdir(parents=True)
            (todo / "figs").mkdir(parents=True)
            (done / "figures.manifest.json").write_text("{}", encoding="utf-8")
            with mock.patch.object(figsize_status, "check_unit", return_value=[]):
                self.assertEqual(figsize_status.status_unit(done)["status"], "done")
            self.assertEqual(figsize_status.status_unit(todo)["status"], "todo")

    def test_check_svg_aspect(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            unit = root / "试卷" / "2000" / "测试"
            (unit / "figs").mkdir(parents=True)
            svg = unit / "figs" / "a.svg"
            svg.write_text('<svg width="200" height="100"></svg>', encoding="utf-8")
            (unit / "测试.tex").write_text(
                "\\onepicture[w=4cm]{figs/a}\n", encoding="utf-8")
            (unit / "figures.manifest.json").write_text(json.dumps({
                "entries": [{"target": "试卷/2000/测试/figs/a.svg",
                             "width_cm": 4.0, "height_cm": 2.0}]
            }), encoding="utf-8")
            with mock.patch.object(figsize_check, "ROOT", root):
                self.assertEqual(figsize_check.check_unit(unit), [])
                strict = figsize_check.check_unit(unit, strict_assets=True)
            self.assertTrue(any("SVG" in e for e in strict), strict)
            svg.write_text('<svg width="200" height="200"></svg>', encoding="utf-8")
            with mock.patch.object(figsize_check, "ROOT", root):
                errs = figsize_check.check_unit(unit)
            self.assertTrue(any("SVG" in e for e in errs), errs)

    def test_plan_accepts_final_only_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            unit = root / "试卷" / "2000" / "测试"
            (unit / "figs").mkdir(parents=True)
            Image.new("RGB", (100, 50), "white").save(unit / "figs" / "a.png")
            (unit / "figures.map.json").write_text(json.dumps({
                "entries": [{
                    "target": "试卷/2000/测试/figs/a.png",
                    "final_width_cm": 3.0,
                    "final_height_cm": 2.0,
                }]
            }), encoding="utf-8")
            cand = unit / "cand.json"
            cand.write_text(json.dumps({"source_pdf": "x.pdf", "figures": []}),
                            encoding="utf-8")

            with mock.patch.object(figsize_plan, "ROOT", root):
                rc = figsize_plan.main([str(unit), "--candidates", str(cand), "--write"])
            self.assertEqual(rc, 0)
            entry = json.loads((unit / "figures.manifest.json").read_text(encoding="utf-8"))["entries"][0]
            self.assertEqual((entry["width_cm"], entry["height_cm"]), (3.0, 2.0))
            self.assertEqual(entry["status"], "manual")

    def test_svg_aspect_viewbox_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            svg = Path(tmp) / "a.svg"
            svg.write_text('<svg viewBox="0 0 200 100"></svg>', encoding="utf-8")
            self.assertAlmostEqual(figsize_plan.asset_aspect(svg), 2.0)

    def test_svg_aspect_clip_path_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            svg = Path(tmp) / "a.svg"
            svg.write_text(
                '<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" '
                '"http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">\n'
                '<svg xmlns="http://www.w3.org/2000/svg">'
                '<defs><clipPath id="cc"><rect x="0" y="0" '
                'width="524" height="423"/></clipPath></defs></svg>',
                encoding="utf-8")
            self.assertAlmostEqual(figsize_plan.asset_aspect(svg), 524 / 423)
            self.assertAlmostEqual(figsize_check.svg_aspect(svg), 524 / 423)

    def test_svg_aspect_namespaced_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            svg = Path(tmp) / "a.svg"
            svg.write_text(
                '<?xml version="1.0"?>\n'
                '<ns0:svg xmlns:ns0="http://www.w3.org/2000/svg" '
                'width="465" height="405" viewBox="0 0 465 405"></ns0:svg>',
                encoding="utf-8")
            self.assertAlmostEqual(figsize_plan.asset_aspect(svg), 465 / 405)
            self.assertAlmostEqual(figsize_check.svg_aspect(svg), 465 / 405)

    def test_hungarian_min(self):
        a = [[1.0, 2.0], [4500.0, 5.0]]
        res = figsize_automap.hungarian_min(a)
        self.assertEqual(res, {0: 0, 1: 1})

    def test_automap_assign_is_one_to_one(self):
        def q(ai, cand, sim, dev):
            return {"ai": ai, "c": {"candidate": cand}, "sim": sim, "dev": dev,
                    "cost": sim - 1.5 * min(dev, 1.0)}
        pairs = [
            q(0, 1, 0.95, 0.01), q(0, 2, 0.50, 0.01),
            q(1, 1, 0.90, 0.01), q(1, 2, 0.30, 0.30),
        ]
        out = figsize_automap.assign_pairs(pairs, 2, 2, min_sim=0.20, max_dev=0.15)
        self.assertEqual(sorted(v["c"]["candidate"] for v in out.values()), [1, 2])
        self.assertNotEqual(out[0]["c"]["candidate"], out[1]["c"]["candidate"])

    def test_fix_refs_adds_png_extension_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            unit = root / "试卷" / "2000" / "测试"
            (unit / "figs").mkdir(parents=True)
            Image.new("RGB", (20, 10), "white").save(unit / "figs" / "a.png")
            (unit / "figs" / "b.svg").write_text(
                '<svg width="20" height="10"></svg>', encoding="utf-8")
            tex = unit / "测试.tex"
            tex.write_text(
                "\\onepicture[h=1cm]{figs/a}\n"
                "\\includesvg{figs/b}\n", encoding="utf-8")
            with mock.patch.object(figsize_fix_refs, "ROOT", root):
                figsize_fix_refs.main([str(unit), "--write"])
            text = tex.read_text(encoding="utf-8")
            self.assertIn("figs/a.png}", text)
            self.assertIn("\\includesvg{figs/b}", text)

    def test_automap_legacy_candidate_manifest_without_candidate_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            img = Path(tmp) / "a.png"
            Image.new("RGB", (20, 10), "white").save(img)
            manifest = Path(tmp) / "figures.manifest.json"
            manifest.write_text(json.dumps({
                "figures": [{
                    "page": 1, "kind": "vector",
                    "width_cm": 4.0, "height_cm": 2.0,
                    "png": str(img),
                }]
            }), encoding="utf-8")
            cands = figsize_automap.load_candidates(manifest)
            self.assertEqual(cands[0]["candidate"], 1)
            self.assertEqual(cands[0]["aspect"], 2.0)

    def test_merge_fallback_helpers(self):
        import numpy as np
        r = figsize_merge_fallback.union_rect([[0.1, 0.2, 0.5, 0.6],
                                               [0.4, 0.1, 0.8, 0.4]])
        self.assertEqual(r, [0.1, 0.1, 0.8, 0.6])
        img = Image.linear_gradient("L").resize((40, 20))
        v = figsize_merge_fallback.feature_image(img)
        self.assertAlmostEqual(float(np.linalg.norm(v)), 1.0, places=5)

    def test_plan_skip_unreferenced(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            unit = root / "试卷" / "2000" / "测试"
            (unit / "figs").mkdir(parents=True)
            Image.new("RGB", (100, 50), "white").save(unit / "figs" / "a.png")
            Image.new("RGB", (100, 50), "white").save(unit / "figs" / "b.png")
            (unit / "测试.tex").write_text(
                "\\onepicture[w=4cm]{figs/a.png}\n", encoding="utf-8")
            (unit / "figures.map.json").write_text('{"entries": []}',
                                                   encoding="utf-8")
            cand = unit / "cand.json"
            cand.write_text('{"source_pdf": "x.pdf", "figures": []}',
                            encoding="utf-8")
            with mock.patch.object(figsize_plan, "ROOT", root):
                rc = figsize_plan.main([str(unit), "--candidates", str(cand),
                                        "--write", "--keep-current",
                                        "--skip-unreferenced"])
            self.assertEqual(rc, 0)
            m = json.loads((unit / "figures.manifest.json").read_text(encoding="utf-8"))
            names = [Path(e["target"]).name for e in m["entries"]]
            self.assertEqual(names, ["a.png"])

    def test_apply_adds_options_to_command_without_options(self):
        """无尺寸选项的图片命令必须补上带方括号的尺寸，而不是拼成 \\onepicturew=…。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            unit = root / "试卷" / "2000" / "测试"
            (unit / "figs").mkdir(parents=True)
            Image.new("RGB", (100, 50), "white").save(unit / "figs" / "a.png")
            tex = unit / "测试.tex"
            tex.write_text("\\onepicture{figs/a.png}\n", encoding="utf-8")
            (unit / "figures.manifest.json").write_text(json.dumps({
                "entries": [{
                    "target": "试卷/2000/测试/figs/a.png",
                    "width_cm": 4.0, "height_cm": 2.0,
                    "final": {"reference": "width"},
                }]
            }), encoding="utf-8")

            with mock.patch.object(figsize_apply, "ROOT", root):
                figsize_apply.main([str(unit), "--write"])
            self.assertEqual(tex.read_text(encoding="utf-8"),
                             "\\onepicture[w=4.00cm]{figs/a.png}\n")

            with mock.patch.object(figsize_check, "ROOT", root):
                errs = figsize_check.check_unit(unit)
            self.assertEqual(errs, [])


if __name__ == "__main__":
    unittest.main()

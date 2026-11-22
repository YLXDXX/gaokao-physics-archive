"""tools/test_figsize_tools.py —— plan/apply/check 小型端到端测试。"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from tools import figsize_apply, figsize_check, figsize_plan


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


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import figsize_audit as fa


class TestFigsizeAudit(unittest.TestCase):
    def test_audit_unit_and_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            unit = root / "试卷" / "2000" / "测试"
            (unit / "figs").mkdir(parents=True)
            for name in ["01.png", "02.svg", "03a.png", "03b.png",
                         "04a.svg", "04b.svg", "04c.svg", "04d.svg", "unused.png"]:
                (unit / "figs" / name).write_bytes(b"x")
            (unit / "figs" / ".ocr_before").mkdir()
            (unit / "figs" / ".ocr_before" / "old.png").write_bytes(b"x")
            tex = unit / "测试.tex"
            tex.write_text(
                "\\onepicture[w=6cm]{figs/01.png}\n"
                "\\onepicture{figs/02.svg}\n"
                "\\twopicture[h=3cm]{figs/03a.png}{figs/03b.png}\n"
                "\\fourchoices[answer=A, ispicture=true, h=2.7cm]\n"
                "{figs/04a.svg}{figs/04b.svg}{figs/04c.svg}{figs/04d.svg}\n",
                encoding="utf-8",
            )
            (root / "OriginPDF" / "2000").mkdir(parents=True)
            (root / "OriginPDF" / "2000" / "2000_测试.pdf").write_bytes(b"%PDF")
            (root / "材料处理" / "2000" / "测试" / "pdfimages").mkdir(parents=True)
            manifest = root / "材料处理" / "2000" / "测试" / "pdfimages" / "manifest.json"
            manifest.write_text(json.dumps({
                "source_pdf": "OriginPDF/2000/2000_测试.pdf"
            }), encoding="utf-8")

            with mock.patch.object(fa, "ROOT", root):
                row = fa.audit_unit(unit)

            self.assertEqual(row["images"], 9)
            self.assertEqual(row["by_ext"]["png"], 4)
            self.assertEqual(row["by_ext"]["svg"], 5)
            self.assertEqual(row["referenced"], 8)
            self.assertEqual(row["unreferenced"], 1)
            self.assertIn("figs/02", row["missing_size_images"])
            self.assertEqual(row["image_sizes"]["figs/01"], "6cm")
            self.assertEqual(row["image_sizes"]["figs/03a"], "3cm")
            self.assertEqual(row["image_sizes"]["figs/04d"], "2.7cm")
            self.assertTrue(row["pdf"])
            self.assertIn("no_recrop", row["flags"])
            self.assertIn("has_svg", row["flags"])
            self.assertIn("unreferenced", row["flags"])

            with mock.patch.object(fa, "ROOT", root):
                summary = fa.summarize([row])
            self.assertEqual(summary["units"], 1)
            self.assertEqual(summary["images"], 9)
            self.assertEqual(summary["flags"]["no_figures_manifest"], 1)

    def test_dual_format_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            unit = root / "试卷" / "2000" / "测试"
            (unit / "figs").mkdir(parents=True)
            (unit / "figs" / "05.png").write_bytes(b"x")
            (unit / "figs" / "05.svg").write_bytes(b"x")
            (unit / "测试.tex").write_text(
                "\\onepicture{figs/05.svg}\n", encoding="utf-8")
            (root / "OriginPDF" / "2000").mkdir(parents=True)
            (root / "OriginPDF" / "2000" / "2000_测试.pdf").write_bytes(b"%PDF")
            (root / "材料处理" / "2000" / "测试" / "pdfimages").mkdir(parents=True)
            (root / "材料处理" / "2000" / "测试" / "pdfimages" / "manifest.json").write_text(
                json.dumps({"source_pdf": "OriginPDF/2000/2000_测试.pdf"}),
                encoding="utf-8")
            with mock.patch.object(fa, "ROOT", root):
                row = fa.audit_unit(unit)
            self.assertIn("dual_format", row["flags"])
            self.assertEqual(row["dual_format_files"], ["05"])

    def test_fig_key(self):
        self.assertEqual(fa._fig_key("figs/03a.svg"), "figs/03a")
        self.assertEqual(fa._fig_key("figs/03a"), "figs/03a")
        self.assertEqual(fa._fig_key("other/03a.png"), "")

    def test_per_image_size_key_case(self):
        opts = fa._parse_options("hA=3.3cm, hB=1.8cm, hC=3.3cm")
        self.assertEqual(fa._first_size(opts, 3, 0), "3.3cm")
        self.assertEqual(fa._first_size(opts, 3, 1), "1.8cm")
        self.assertEqual(fa._first_size(opts, 3, 2), "3.3cm")


if __name__ == "__main__":
    unittest.main()

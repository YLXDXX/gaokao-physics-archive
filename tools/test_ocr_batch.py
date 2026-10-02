#!/usr/bin/env python3
"""tools/test_ocr_batch.py

``tools/ocr_batch.py`` 的单元测试：目录映射（含 2000 年以前同名地区）、
pdfimages 完整性判定、重试与非空判定。

运行::

    python3 -m unittest tools.test_ocr_batch
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ocr_batch  # noqa: E402


class TestMapping(unittest.TestCase):
    def test_split_basic(self):
        p = ocr_batch.DOCX / "2026" / "2026_湖南.pdf"
        self.assertEqual(ocr_batch._split(p), ("2026", "2026_湖南"))

    def test_split_rejects_flat(self):
        p = ocr_batch.DOCX / "2026_湖南.pdf"
        self.assertIsNone(ocr_batch._split(p))

    def test_iter_pdfs_unique_outdirs(self):
        """核心不变式：任意两份 PDF 不得映射到同一处理目录（防同名地区互相覆盖）。"""
        if not ocr_batch.DOCX.is_dir():
            self.skipTest("Docx/ 不存在（Git 忽略，属正常）")
        items = ocr_batch.iter_pdfs()
        outs = [out for _pdf, out in items]
        self.assertEqual(len(outs), len(set(outs)), "存在重复的处理目录映射")

    def test_iter_pdfs_pre2000_full_stem(self):
        """2000 年以前（非 4 位年份桶）一律用完整卷名作子目录。"""
        if not ocr_batch.DOCX.is_dir():
            self.skipTest("Docx/ 不存在")
        items = ocr_batch.iter_pdfs(years=["2000年以前"])
        for pdf, out in items:
            self.assertEqual(out.parent.name, "2000年以前")
            self.assertIn(out.name, pdf.stem)  # 子目录名即完整卷名

    def test_iter_pdfs_year_region_short(self):
        """常规年份且地区唯一时，用短地区名。"""
        if not ocr_batch.DOCX.is_dir():
            self.skipTest("Docx/ 不存在")
        items = ocr_batch.iter_pdfs(years=["2026"], region="湖南")
        self.assertTrue(items)
        _pdf, out = items[0]
        self.assertEqual(out.name, "湖南")


class TestPdfimagesOk(unittest.TestCase):
    def _mk(self, d: Path, manifest=None, files=()):
        p = d / "pdfimages"
        p.mkdir(parents=True)
        for f in files:
            (p / f).write_bytes(b"x")
        if manifest is not None:
            (p / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def test_missing_dir(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertFalse(ocr_batch.pdfimages_ok(Path(t)))

    def test_no_manifest_ok(self):
        with tempfile.TemporaryDirectory() as t:
            self._mk(Path(t))
            self.assertTrue(ocr_batch.pdfimages_ok(Path(t)))

    def test_manifest_complete(self):
        with tempfile.TemporaryDirectory() as t:
            self._mk(Path(t), manifest={"images": [{"file": "a.jpg"}]}, files=("a.jpg",))
            self.assertTrue(ocr_batch.pdfimages_ok(Path(t)))

    def test_manifest_missing_file(self):
        with tempfile.TemporaryDirectory() as t:
            self._mk(Path(t), manifest={"images": [{"file": "a.jpg"}]})
            self.assertFalse(ocr_batch.pdfimages_ok(Path(t)))


class TestRunRetry(unittest.TestCase):
    def test_success_first(self):
        r = ocr_batch.run_retry([sys.executable, "-c", "print('ok')"])
        self.assertEqual(r.returncode, 0)
        self.assertIn("ok", r.stdout)

    def test_fail_returns_last(self):
        r = ocr_batch.run_retry([sys.executable, "-c", "import sys; sys.exit(3)"], tries=2)
        self.assertEqual(r.returncode, 3)


class TestNonempty(unittest.TestCase):
    def test_nonempty(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "f"
            self.assertFalse(ocr_batch.nonempty(p))
            p.write_bytes(b"")
            self.assertFalse(ocr_batch.nonempty(p))
            p.write_bytes(b"x")
            self.assertTrue(ocr_batch.nonempty(p))


if __name__ == "__main__":
    unittest.main(verbosity=2)

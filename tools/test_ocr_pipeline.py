#!/usr/bin/env python3
"""tools/ocr_pipeline 的纯单元测试（不依赖 GPU / Paddle 服务）。"""

from __future__ import annotations

import base64
import io
import json
import logging
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List

from PIL import Image

from tools.ocr_pipeline import state as st
from tools.ocr_pipeline.config import load_config
from tools.ocr_pipeline.ovis3 import (
    OvisOCR3Engine,
    OvisStage,
    crop_saved_pages,
    parse_layout,
    parse_structured,
    save_block_crops,
    save_markdown_crops,
)
from tools.ocr_pipeline.paddle import PaddleStage, _normalise_paddle_page, _rewrite_image_paths
from tools.ocr_pipeline.pdf import PDFInfo, probe_pdf, render_page_images
from tools.ocr_pipeline.pipeline import (
    Job,
    canonical_stages,
    discover_jobs,
    run_stages,
    status_rows,
)
from tools.check_material import check_dir
from tools.ocr_pipeline.utils import (
    bbox_1000_to_pixels,
    bbox_pixels_to_norm,
    read_json,
    write_json_atomic,
)

TMP_ROOT = Path("/tmp/opencode")
if not TMP_ROOT.is_dir():
    TMP_ROOT = Path(tempfile.gettempdir())


def _tmpdir() -> tempfile.TemporaryDirectory:
    return tempfile.TemporaryDirectory(prefix="ocr_test_", dir=str(TMP_ROOT))


def _make_pdf(path: Path, pages: int = 2, text: bool = True) -> Path:
    import pymupdf

    doc = pymupdf.open()
    for i in range(pages):
        page = doc.new_page(width=300, height=400)
        if text:
            page.insert_text((30, 50), f"Page {i + 1} test text", fontsize=12)
    doc.save(str(path))
    doc.close()
    return path


class TestBBox(unittest.TestCase):
    def test_normalised_to_pixels(self):
        self.assertEqual(bbox_1000_to_pixels([100, 200, 500, 600], 1000, 2000),
                         (100, 400, 500, 1200))

    def test_clamp_and_invalid(self):
        self.assertEqual(bbox_1000_to_pixels([-10, -10, 1200, 300], 100, 100),
                         (0, 0, 100, 30))
        self.assertIsNone(bbox_1000_to_pixels([500, 500, 100, 600], 100, 100))

    def test_pixels_to_norm(self):
        self.assertEqual(bbox_pixels_to_norm([100, 200, 500, 600], 1000, 2000),
                         [0.1, 0.1, 0.5, 0.3])


class TestStructuredParsing(unittest.TestCase):
    def test_valid(self):
        raw = json.dumps([
            {"bbox": [10, 20, 300, 400], "category": "image",
             "content": '<img src="images/bbox_10_20_300_400.jpg" />'},
            {"bbox": [10, 500, 900, 600], "category": "text", "content": "题干"},
        ], ensure_ascii=False)
        blocks, diag, md = parse_structured(raw)
        self.assertTrue(diag["valid"])
        self.assertEqual(len(blocks), 2)
        self.assertIn("题干", md)
        self.assertIn("bbox_10_20_300_400.jpg", md)

    def test_fenced_and_truncated_prefix(self):
        raw = "```json\n[" + json.dumps(
            {"bbox": [1, 2, 3, 4], "category": "text", "content": "甲"},
            ensure_ascii=False,
        ) + ", {\"bbox\": [5, 6, 7, 8], \"category\": \"text\", \"content\": \"乙"
        blocks, diag, md = parse_structured(raw)
        self.assertFalse(diag["json_complete"])
        self.assertEqual(len(blocks), 1)
        self.assertEqual(md, "甲")
        self.assertGreater(diag["unparsed_tail_chars"], 0)

    def test_invalid_category_is_reported_but_kept(self):
        raw = '[{"bbox":[0,0,10,10],"category":"bogus","content":"x"}]'
        blocks, diag, _ = parse_structured(raw)
        self.assertEqual(len(blocks), 1)
        self.assertFalse(diag["valid"])

    def test_layout(self):
        raw = '[{"bbox":[0,0,10,10],"category":"image"}]'
        layout, diag = parse_layout(raw)
        self.assertTrue(diag["json_complete"])
        self.assertEqual(layout[0]["category"], "image")


class TestCropping(unittest.TestCase):
    def test_markdown_crops(self):
        with _tmpdir() as td:
            base = Path(td)
            img = Image.new("RGB", (1000, 1000), "white")
            md = '<img src="images/bbox_100_100_500_500.jpg" />'
            new_md, records, errors = save_markdown_crops(md, img, 1, base / "images")
            self.assertFalse(errors)
            self.assertIn("page_1_bbox_100_100_500_500.jpg", new_md)
            self.assertTrue((base / "images" / "page_1_bbox_100_100_500_500.jpg").is_file())
            self.assertEqual(records[0]["pixel_bbox"], [100, 100, 500, 500])

    def test_block_crops(self):
        with _tmpdir() as td:
            base = Path(td)
            img = Image.new("RGB", (1000, 1000), "white")
            blocks = [
                {"index": 0, "bbox": [10, 20, 300, 400], "category": "image"},
                {"index": 1, "bbox": [10, 500, 900, 600], "category": "text"},
            ]
            records, errors = save_block_crops(blocks, img, 2, base)
            self.assertFalse(errors)
            self.assertEqual(len(records), 1)
            self.assertTrue((base / records[0]["image"]).is_file())


class TestState(unittest.TestCase):
    def test_pages_and_errors(self):
        with _tmpdir() as td:
            out = Path(td)
            st.set_page(out, "ovis", 1, "done")
            st.set_page(out, "ovis", 2, "failed", error="timeout")
            st.add_error(out, "ovis", "page 2 timeout", page=2)
            self.assertTrue(st.is_page_done(out, "ovis", 1))
            self.assertFalse(st.is_page_done(out, "ovis", 2))
            state = st.load_state(out)
            self.assertEqual(state["stages"]["ovis"]["pages"]["2"]["status"], "failed")
            self.assertEqual(len(state["errors"]), 1)


class TestPDF(unittest.TestCase):
    def test_probe_and_render(self):
        with _tmpdir() as td:
            base = Path(td)
            pdf = _make_pdf(base / "a.pdf", pages=2)
            info = probe_pdf(pdf, text_min_chars=10)
            self.assertEqual(info.pages, 2)
            self.assertTrue(info.has_text)
            outs = render_page_images(pdf, base / "pages", dpi=72)
            self.assertEqual(len(outs), 2)
            self.assertTrue(all(p.is_file() for p in outs))


class TestOvisStageResume(unittest.TestCase):
    def _config(self, root: Path) -> Dict[str, Any]:
        cfg = load_config()
        cfg["model"]["path"] = str(root / "OvisOCR3")  # backend 注入，不实际加载
        cfg["pdf"]["dpi"] = 72
        cfg["ovis"]["prompt_mode"] = "structured"
        cfg["ovis"]["crop_dpi"] = 72
        cfg["ovis"]["save_block_crops"] = True
        cfg["ovis"]["include_metadata"] = True
        return cfg

    def test_resume_and_force(self):
        with _tmpdir() as td:
            base = Path(td)
            pdf = _make_pdf(base / "lesson.pdf", pages=2)
            cfg = self._config(base)
            calls: List[int] = []

            def backend(images, prompt):
                calls.append(len(images))
                out = []
                for img in images:
                    out.append((
                        json.dumps(
                            [
                                {"bbox": [10, 10, 100, 100], "category": "image",
                                 "content": '<img src="images/bbox_10_10_100_100.jpg" />'},
                                {"bbox": [10, 200, 900, 300], "category": "text",
                                 "content": "第 1 页题干"},
                            ],
                            ensure_ascii=False,
                        ),
                        "stop",
                    ))
                return out

            logger = logging.getLogger("test_ovis")
            engine = OvisOCR3Engine(cfg, logger, backend=backend)
            out = base / "proc"
            stage = OvisStage(out, pdf, cfg, logger, engine=engine)
            result = stage.run()
            self.assertEqual(result["status"], "done")
            self.assertEqual(len(calls), 2)
            self.assertTrue((out / "ovis" / "output.md").is_file())
            self.assertTrue((out / "ovis" / "structured" / "page_0001.json").is_file())
            self.assertTrue((out / "ovis" / "layout" / "page_0002.json").is_file())
            self.assertTrue((out / "ovis" / "crops" / "page_0001" / "000_image.png").is_file())
            raw = read_json(out / "ovis" / "raw" / "page_0001.json", default={})
            self.assertEqual(raw["status"], "done")
            self.assertTrue(raw["markdown"].startswith(""))
            self.assertIn("page_1_bbox_10_10_100_100.jpg", read_json(
                out / "ovis" / "raw" / "page_0001.json", default={}
            )["markdown"])

            # 第二次：应完全从 raw 断点跳过，不再调用后端
            stage2 = OvisStage(out, pdf, cfg, logger, engine=engine)
            result2 = stage2.run()
            self.assertEqual(result2["status"], "done")
            self.assertEqual(len(calls), 2)

            # --force：重新推理
            stage3 = OvisStage(out, pdf, cfg, logger, engine=engine, force=True)
            stage3.run()
            self.assertEqual(len(calls), 4)

    def test_batch_inference(self):
        with _tmpdir() as td:
            base = Path(td)
            pdf = _make_pdf(base / "batch.pdf", pages=2)
            cfg = self._config(base)
            cfg["ovis"]["batch_size"] = 2
            calls: List[int] = []

            def backend(images, prompt):
                calls.append(len(images))
                return [
                    (json.dumps([
                        {"bbox": [10, 10, 100, 100], "category": "image",
                         "content": '<img src="images/bbox_10_10_100_100.jpg" />'},
                        {"bbox": [10, 200, 900, 300], "category": "text", "content": "题"},
                    ], ensure_ascii=False), "stop")
                    for _ in images
                ]

            logger = logging.getLogger("test_ovis_batch")
            engine = OvisOCR3Engine(cfg, logger, backend=backend)
            out = base / "proc"
            result = OvisStage(out, pdf, cfg, logger, engine=engine).run()
            self.assertEqual(result["status"], "done")
            self.assertEqual(calls, [2])
            self.assertTrue((out / "ovis" / "structured" / "page_0002.json").is_file())



class TestPipelinePlanning(unittest.TestCase):
    def test_canonical_stage_order(self):
        self.assertEqual(
            canonical_stages(["ovis", "paddle", "text"]),
            ["text", "paddle", "ovis"],
        )
        with self.assertRaises(ValueError):
            canonical_stages(["text", "typo"])

    def test_fail_fast_writes_report(self):
        with _tmpdir() as td:
            base = Path(td)
            job1 = Job(base / "missing1.pdf", base / "out1")
            job2 = Job(base / "missing2.pdf", base / "out2")
            cfg = load_config()
            report_path = base / "report.json"
            test_logger = logging.getLogger("test_pipeline")
            test_logger.setLevel(logging.CRITICAL)
            report = run_stages(
                [job1, job2], ["text"], config=cfg,
                logger=test_logger, fail_fast=True,
                report_path=report_path,
            )
            self.assertTrue(report_path.is_file())
            self.assertEqual(len(report["summary"]["failed_jobs"]), 1)
            self.assertEqual(len(report["summary"]["failed_jobs"]), 1)

    def test_status_rows_counts(self):
        with _tmpdir() as td:
            base = Path(td)
            out = base / "proc"
            (out / "ovis" / "raw").mkdir(parents=True)
            (out / "ovis" / "structured").mkdir(parents=True)
            (out / "ovis" / "output.md").write_text("x", encoding="utf-8")
            write_json_atomic(out / "ovis" / "manifest.json", {"engine": "OvisOCR3", "pages": 1, "status": "complete"})
            write_json_atomic(out / "ovis" / "raw" / "page_0001.json", {"status": "done"})
            write_json_atomic(out / "ovis" / "structured" / "page_0001.json", {})
            rows = status_rows([Job(None, out)], load_config())
            self.assertEqual(rows[0]["ovis_raw"], 1)
            self.assertEqual(rows[0]["ovis_structured"], 1)


class TestCheckMaterialPages(unittest.TestCase):
    def test_new_manifest_requires_page_artifacts(self):
        with _tmpdir() as td:
            base = Path(td)
            for rel in ("ovis", "paddle"):
                (base / rel).mkdir(parents=True)
                (base / rel / "output.md").write_text("x", encoding="utf-8")
            (base / "pdftotext.txt").write_text("x", encoding="utf-8")
            (base / "merged.md").write_text("x", encoding="utf-8")
            write_json_atomic(base / "ovis" / "manifest.json", {"engine": "OvisOCR3", "pages": 1, "status": "complete"})
            write_json_atomic(base / "paddle" / "manifest.json", {"engine": "PaddleOCR-VL", "pages": 1, "status": "complete"})
            problems, warnings = [], []
            check_dir(base, problems, warnings)
            self.assertTrue(any("ovis/raw/page_0001.json" in p for p in problems))
            self.assertTrue(any("paddle/raw/page_0001.json" in p for p in problems))

    def test_corrupt_manifest_is_problem(self):
        with _tmpdir() as td:
            base = Path(td)
            (base / "ovis").mkdir()
            (base / "ovis" / "manifest.json").write_text("{bad", encoding="utf-8")
            problems, warnings = [], []
            check_dir(base, problems, warnings)
            self.assertTrue(any("不是合法 JSON" in p for p in problems))


class TestOvisReliability(unittest.TestCase):
    def _cfg(self, root: Path, dpi: int = 72) -> Dict[str, Any]:
        cfg = load_config()
        cfg["model"]["path"] = str(root / "OvisOCR3")
        cfg["pdf"]["dpi"] = dpi
        cfg["ovis"]["prompt_mode"] = "structured"
        cfg["ovis"]["crop_dpi"] = dpi
        return cfg

    def _fake_backend(self, calls):
        def backend(images, prompt):
            calls.append(len(images))
            return [(
                json.dumps([
                    {"bbox": [10, 10, 100, 100], "category": "image",
                     "content": '<img src="images/bbox_10_10_100_100.jpg" />'},
                    {"bbox": [10, 200, 900, 300], "category": "text", "content": "题"},
                ], ensure_ascii=False), "stop")
                for _ in images
            ]
        return backend

    def test_source_change_and_dpi_change_rerun(self):
        with _tmpdir() as td:
            base = Path(td)
            pdf = _make_pdf(base / "x.pdf", pages=1)
            calls: List[int] = []
            logger = logging.getLogger("test_ovis_reliability")
            out = base / "proc"
            cfg = self._cfg(base, 72)
            engine = OvisOCR3Engine(cfg, logger, backend=self._fake_backend(calls))
            OvisStage(out, pdf, cfg, logger, engine=engine).run()
            self.assertEqual(len(calls), 1)
            # 源 PDF 改变 → 必须重新渲染并推理
            _make_pdf(pdf, pages=1, text=False)
            OvisStage(out, pdf, cfg, logger, engine=engine).run()
            self.assertEqual(len(calls), 2)
            # DPI 改变 → 必须重新渲染并推理
            cfg["pdf"]["dpi"] = 100
            cfg["ovis"]["crop_dpi"] = 100
            OvisStage(out, pdf, cfg, logger, engine=engine).run()
            self.assertEqual(len(calls), 3)


    def test_partial_page_is_retried(self):
        with _tmpdir() as td:
            base = Path(td)
            pdf = _make_pdf(base / "partial.pdf", pages=1)
            cfg = self._cfg(base)
            state = {"calls": 0}
            good = json.dumps([
                {"bbox": [10, 10, 100, 100], "category": "text", "content": "完整"},
            ], ensure_ascii=False)

            def backend(images, prompt):
                state["calls"] += 1
                text = '[{"bbox":[10,10,100,100],"category":"text","content":"截' if state["calls"] == 1 else good
                return [(text, "stop") for _ in images]

            logger = logging.getLogger("test_ovis_partial")
            out = base / "proc"
            engine = OvisOCR3Engine(cfg, logger, backend=backend)
            result = OvisStage(out, pdf, cfg, logger, engine=engine).run()
            self.assertEqual(result["status"], "partial")
            raw = read_json(out / "ovis" / "raw" / "page_0001.json", default={})
            self.assertEqual(raw.get("status"), "partial")
            result2 = OvisStage(out, pdf, cfg, logger, engine=engine).run()
            self.assertEqual(result2["status"], "done")
            self.assertEqual(state["calls"], 2)

    def test_crop_saved_pages(self):
        with _tmpdir() as td:
            base = Path(td)
            pdf = _make_pdf(base / "x.pdf", pages=1)
            calls: List[int] = []
            logger = logging.getLogger("test_ovis_crops")
            out = base / "proc"
            cfg = self._cfg(base, 72)
            engine = OvisOCR3Engine(cfg, logger, backend=self._fake_backend(calls))
            OvisStage(out, pdf, cfg, logger, engine=engine).run()
            result = crop_saved_pages(out, pdf, dpi=100, out_dir=base / "crops")
            self.assertEqual(result["count"], 1)
            manifest = read_json(base / "crops" / "manifest.json", default={})
            self.assertTrue((base / "crops" / "manifest.json").is_file())
            self.assertEqual(len(manifest["crops"]), 1)
            self.assertTrue((base / "crops" / manifest["crops"][0]["image"]).is_file())


class TestPaddleChunksAndRestructure(unittest.TestCase):
    def test_chunking_and_resume(self):
        import pymupdf

        class FakeClient:
            def __init__(self):
                self.calls = []

            def healthy(self):
                return True

            def parse_document(self, data, file_type=0, options=None):
                doc = pymupdf.open(stream=data, filetype="pdf")
                n = len(doc)
                doc.close()
                self.calls.append(n)
                return {"layoutParsingResults": [self._page(i) for i in range(n)]}

            def _page(self, i):
                return {
                    "prunedResult": {
                        "width": 1000,
                        "height": 1400,
                        "layout_det_res": {"boxes": [
                            {"label": "text", "coordinate": [10, 20, 900, 100], "score": 0.9}
                        ]},
                        "parsing_res_list": [
                            {"block_label": "text", "block_bbox": [10, 20, 900, 100],
                             "block_content": "文字"},
                        ],
                    },
                    "markdown": {"text": "文字", "images": {}},
                }

        with _tmpdir() as td:
            base = Path(td)
            pdf = _make_pdf(base / "x.pdf", pages=3)
            cfg = load_config()
            cfg["paddle"]["page_chunk"] = 2
            cfg["paddle"]["restructure"] = False
            logger = logging.getLogger("test_paddle_chunks")
            client = FakeClient()
            out = base / "proc"
            result = PaddleStage(out, pdf, cfg, logger, client=client).run()
            self.assertEqual(result["status"], "done")
            self.assertEqual(client.calls, [2, 1])
            self.assertEqual(
                len(list((out / "paddle" / "raw").glob("page_*.json"))), 3
            )
            PaddleStage(out, pdf, cfg, logger, client=client).run()
            self.assertEqual(client.calls, [2, 1])

    def test_restructure_output(self):
        class FakeClient:
            def __init__(self):
                self.restructured = 0

            def healthy(self):
                return True

            def parse_document(self, data, file_type=0, options=None):
                return {"layoutParsingResults": [{
                    "prunedResult": {
                        "width": 1000, "height": 1000,
                        "layout_det_res": {"boxes": [
                            {"label": "text", "coordinate": [0, 0, 100, 100], "score": 1}
                        ]},
                        "parsing_res_list": [],
                    },
                    "markdown": {"text": "逐页", "images": {}},
                }]}

            def restructure_pages(self, pages, **kwargs):
                self.restructured += 1
                return {"layoutParsingResults": [{
                    "markdown": {"text": "重构正文", "images": {}}
                }]}

        with _tmpdir() as td:
            base = Path(td)
            pdf = _make_pdf(base / "x.pdf", pages=1)
            cfg = load_config()
            cfg["paddle"]["page_chunk"] = 10
            cfg["paddle"]["restructure"] = True
            logger = logging.getLogger("test_paddle_restructure")
            client = FakeClient()
            out = base / "proc"
            PaddleStage(out, pdf, cfg, logger, client=client).run()
            self.assertEqual(client.restructured, 1)
            self.assertTrue((out / "paddle" / "restructured" / "chunk_0001_0001.md").is_file())
            self.assertIn("重构正文", (out / "paddle" / "output.md").read_text(encoding="utf-8"))


class TestPaddleHelpers(unittest.TestCase):
    def test_normalise(self):
        pruned = {
            "width": 1000,
            "height": 2000,
            "layout_det_res": {
                "boxes": [
                    {"label": "image", "coordinate": [100, 200, 500, 600], "score": 0.9},
                ]
            },
            "parsing_res_list": [
                {"block_label": "image", "block_bbox": [100, 200, 500, 600], "block_content": ""},
                {"block_label": "text", "block_bbox": [10, 700, 990, 800], "block_content": "文字"},
            ],
        }
        data = _normalise_paddle_page(pruned, 3)
        self.assertEqual(data["page"], 3)
        self.assertEqual(len(data["blocks"]), 2)
        self.assertEqual(data["blocks"][0]["category"], "image")
        self.assertEqual(data["blocks"][0]["bbox"], [0.1, 0.1, 0.5, 0.3])

    def test_rewrite_paths(self):
        text = '<img src="imgs/a.jpg" /> ![](imgs/b.jpg)'
        out = _rewrite_image_paths(text, {"imgs/a.jpg": "images/p1_a.jpg"})
        self.assertIn("images/p1_a.jpg", out)
        self.assertIn("images/b.jpg", out)


    def test_stage_resume_with_fake_client(self):
        class FakeClient:
            def __init__(self):
                self.calls = 0

            def healthy(self):
                return True

            def parse_document(self, data, file_type=0, options=None):
                self.calls += 1
                buf = io.BytesIO()
                Image.new("RGB", (10, 10), "white").save(buf, format="JPEG")
                b64 = base64.b64encode(buf.getvalue()).decode("ascii")
                results = []
                for p in (1, 2):
                    results.append({
                        "prunedResult": {
                            "width": 1000,
                            "height": 1400,
                            "layout_det_res": {"boxes": [
                                {"label": "image", "coordinate": [100, 200, 500, 600], "score": 0.9}
                            ]},
                            "parsing_res_list": [
                                {"block_label": "image", "block_bbox": [100, 200, 500, 600],
                                 "block_content": ""},
                                {"block_label": "text", "block_bbox": [10, 700, 990, 800],
                                 "block_content": f"第 {p} 页"},
                            ],
                        },
                        "markdown": {
                            "text": f"第 {p} 页\n\n<img src=\"imgs/a.jpg\" />\n",
                            "images": {"imgs/a.jpg": b64},
                        },
                    })
                return {"layoutParsingResults": results}

        with _tmpdir() as td:
            base = Path(td)
            pdf = _make_pdf(base / "p.pdf", pages=2)
            cfg = load_config()
            cfg["paddle"]["page_chunk"] = 10
            cfg["paddle"]["restructure"] = False
            logger = logging.getLogger("test_paddle")
            client = FakeClient()
            out = base / "proc"
            stage = PaddleStage(out, pdf, cfg, logger, client=client)
            result = stage.run()
            self.assertEqual(result["status"], "done")
            self.assertEqual(client.calls, 1)
            self.assertTrue((out / "paddle" / "output.md").is_file())
            self.assertTrue((out / "paddle" / "raw" / "page_0002.json").is_file())
            self.assertTrue((out / "paddle" / "structured" / "page_0001.json").is_file())
            self.assertTrue((out / "paddle" / "images" / "p0001_a.jpg").is_file())

            stage2 = PaddleStage(out, pdf, cfg, logger, client=client)
            result2 = stage2.run()
            self.assertEqual(result2["status"], "done")
            self.assertEqual(client.calls, 1)

    def test_chunk_plan(self):
        with _tmpdir() as td:
            base = Path(td)
            cfg = load_config()
            cfg["paddle"]["page_chunk"] = 20
            stage = PaddleStage(base, base / "x.pdf", cfg, logging.getLogger("test"))
            stage.info = PDFInfo(path="x", name="x.pdf", pages=55)
            self.assertEqual(stage._chunk_plan(), [(1, 20), (21, 40), (41, 55)])
            stage.pages = [2, 3, 10]
            self.assertEqual(stage._chunk_plan(), [(2, 3), (10, 10)])


class TestDiscovery(unittest.TestCase):
    def test_root_locates_source(self):
        with _tmpdir() as td:
            base = Path(td)
            src_root = base / "base"
            proc_root = base / "proc"
            pdf = src_root / "lesson" / "x.pdf"
            pdf.parent.mkdir(parents=True)
            _make_pdf(pdf, pages=1)
            out = proc_root / "lesson" / "x"
            (out / "ovis").mkdir(parents=True)
            (out / "ovis" / "output.md").write_text(
                "---\ntitle: x\nsource: x.pdf\n---\n", encoding="utf-8"
            )
            cfg = load_config()
            jobs = discover_jobs(
                config=cfg,
                roots=[str(proc_root)],
                base_roots=[str(src_root)],
            )
            self.assertEqual(len(jobs), 1)
            self.assertEqual(jobs[0].pdf.resolve(), pdf.resolve())

    def test_filename_fallback_when_prefix_differs(self):
        with _tmpdir() as td:
            base = Path(td)
            src_root = base / "base"
            proc_root = base / "proc"
            # 处理目录与源 PDF 的前缀层级不同，只能靠文件名唯一匹配
            pdf = src_root / "力学" / "第 1 章 物体的运动" / "1.1 相对运动.pdf"
            pdf.parent.mkdir(parents=True)
            _make_pdf(pdf, pages=1)
            out = proc_root / "力学" / "1.1 相对运动"
            (out / "ovis").mkdir(parents=True)
            (out / "ovis" / "output.md").write_text(
                "---\ntitle: x\nsource: 1.1 相对运动.pdf\n---\n", encoding="utf-8"
            )
            cfg = load_config()
            jobs = discover_jobs(
                config=cfg,
                roots=[str(proc_root)],
                base_roots=[str(src_root)],
            )
            self.assertEqual(len(jobs), 1)
            self.assertEqual(jobs[0].pdf.resolve(), pdf.resolve())

    def test_dry_run(self):
        with _tmpdir() as td:
            base = Path(td)
            job = Job(base / "x.pdf", base / "out")
            cfg = load_config()
            report = run_stages(
                [job], ["text", "ovis"], config=cfg,
                logger=logging.getLogger("test"), dry_run=True,
            )
            self.assertEqual(report["summary"]["jobs"], 1)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""tools/check_recrop.py 的单元测试（recipe 结构与尺寸一致性校验）。"""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from tools.check_recrop import check_recipe


def _img(path: Path, size=(200, 200)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (255, 255, 255)).save(path)
    return path


def _recipe(directory: Path, entries):
    p = directory / ".recrop.json"
    p.write_text(json.dumps({"entries": entries}), encoding="utf-8")
    return p


class TestCheckRecrop(unittest.TestCase):
    def test_valid_recipe_no_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            src = _img(d / "src.png", (200, 200))
            tgt = _img(d / "figs" / "a.png", (50, 40))
            rec = _recipe(d, [{
                "source": str(src),
                "crops": [{"rect": [10, 10, 50, 40], "target": str(tgt)}],
            }])
            errors, _warnings = check_recipe(rec)
            self.assertEqual(errors, [])

    def test_target_size_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            src = _img(d / "src.png", (200, 200))
            tgt = _img(d / "figs" / "a.png", (40, 40))  # 应为 50x40
            rec = _recipe(d, [{
                "source": str(src),
                "crops": [{"rect": [10, 10, 50, 40], "target": str(tgt)}],
            }])
            errors, _ = check_recipe(rec)
            self.assertTrue(any("尺寸" in e for e in errors), errors)

    def test_missing_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            src = _img(d / "src.png", (200, 200))
            rec = _recipe(d, [{
                "source": str(src),
                "crops": [{"rect": [0, 0, 50, 40],
                           "target": str(d / "figs" / "none.png")}],
            }])
            errors, _ = check_recipe(rec)
            self.assertTrue(any("不存在" in e for e in errors), errors)

    def test_missing_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            tgt = _img(d / "figs" / "a.png", (50, 40))
            rec = _recipe(d, [{
                "source": str(d / "missing.png"),
                "crops": [{"rect": [0, 0, 50, 40], "target": str(tgt)}],
            }])
            errors, warnings = check_recipe(rec)
            # 源图常位于 Git 忽略目录（JSON/、材料处理/），缺失时降级为提示
            self.assertEqual(errors, [])
            self.assertTrue(any("source" in w for w in warnings), warnings)

    def test_rect_out_of_bounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            src = _img(d / "src.png", (200, 200))
            tgt = _img(d / "figs" / "a.png", (50, 40))
            rec = _recipe(d, [{
                "source": str(src),
                "crops": [{"rect": [180, 180, 50, 40], "target": str(tgt)}],
            }])
            errors, _ = check_recipe(rec)
            self.assertTrue(any("超出" in e for e in errors), errors)

    def test_invalid_erase_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            src = _img(d / "src.png", (200, 200))
            tgt = _img(d / "figs" / "a.png", (50, 40))
            rec = _recipe(d, [{
                "source": str(src),
                "erase_labels": "whatever",
                "crops": [{"rect": [0, 0, 50, 40], "target": str(tgt)}],
            }])
            errors, _ = check_recipe(rec)
            self.assertTrue(any("erase_labels" in e for e in errors), errors)

    def test_duplicate_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            src = _img(d / "src.png", (200, 200))
            tgt = _img(d / "figs" / "a.png", (50, 40))
            rec = _recipe(d, [
                {"source": str(src),
                 "crops": [{"rect": [0, 0, 50, 40], "target": str(tgt)}]},
                {"source": str(src),
                 "crops": [{"rect": [0, 0, 50, 40], "target": str(tgt)}]},
            ])
            errors, _ = check_recipe(rec)
            self.assertTrue(any("重复" in e for e in errors), errors)

    def test_overlap_is_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            src = _img(d / "src.png", (200, 200))
            t1 = _img(d / "figs" / "a.png", (60, 40))
            t2 = _img(d / "figs" / "b.png", (60, 40))
            rec = _recipe(d, [{
                "source": str(src),
                "crops": [{"rect": [0, 0, 60, 40], "target": str(t1)},
                          {"rect": [30, 0, 60, 40], "target": str(t2)}],
            }])
            errors, warnings = check_recipe(rec)
            self.assertEqual(errors, [])
            self.assertTrue(any("重叠" in w for w in warnings), warnings)

    def test_bad_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            rec = d / ".recrop.json"
            rec.write_text("{ not json", encoding="utf-8")
            errors, _ = check_recipe(rec)
            self.assertTrue(errors)

    def test_signature_extension_mismatch(self):
        """PNG 字节写到 .jpg（旧 pipeline 错配）应报错。"""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            src = _img(d / "src.png", (200, 200))
            tgt = d / "figs" / "a.jpg"
            tgt.parent.mkdir(parents=True, exist_ok=True)
            buf = io.BytesIO()
            Image.new("RGB", (50, 40), (255, 255, 255)).save(buf, format="PNG")
            tgt.write_bytes(buf.getvalue())
            rec = _recipe(d, [{
                "source": str(src),
                "crops": [{"rect": [10, 10, 50, 40], "target": str(tgt)}],
            }])
            errors, _ = check_recipe(rec)
            self.assertTrue(any("字节与扩展名不符" in e for e in errors), errors)


class TestCheckRecropTrim(unittest.TestCase):
    def test_trim_allows_smaller_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            src = _img(d / "src.png", (200, 200))
            tgt = _img(d / "figs" / "a.png", (40, 30))  # 小于 rect，trim 后正常
            p = d / ".recrop.json"
            p.write_text(json.dumps({
                "trim": {"padding": 8},
                "entries": [{"source": str(src),
                             "crops": [{"rect": [10, 10, 50, 40], "target": str(tgt)}]}],
            }), encoding="utf-8")
            errors, _ = check_recipe(p)
            self.assertEqual(errors, [])

    def test_trim_larger_than_rect_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            src = _img(d / "src.png", (200, 200))
            tgt = _img(d / "figs" / "a.png", (60, 40))  # 大于 rect 期望 50x40
            p = d / ".recrop.json"
            p.write_text(json.dumps({
                "trim": True,
                "entries": [{"source": str(src),
                             "crops": [{"rect": [10, 10, 50, 40], "target": str(tgt)}]}],
            }), encoding="utf-8")
            errors, _ = check_recipe(p)
            self.assertTrue(any("大于" in e for e in errors), errors)

    def test_bad_trim_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            src = _img(d / "src.png", (200, 200))
            tgt = _img(d / "figs" / "a.png", (50, 40))
            p = d / ".recrop.json"
            p.write_text(json.dumps({
                "trim": {"padding": "big"},
                "entries": [{"source": str(src),
                             "crops": [{"rect": [10, 10, 50, 40], "target": str(tgt)}]}],
            }), encoding="utf-8")
            errors, _ = check_recipe(p)
            self.assertTrue(any("trim.padding" in e for e in errors), errors)


if __name__ == "__main__":
    unittest.main()

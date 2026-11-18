"""通用 OCR 识别转换流水线（OvisOCR3 + PaddleOCR-VL）。

本包把「PDF → 页面图 → OvisOCR3 / PaddleOCR-VL → Markdown + 版面源数据 →
merged.md → 内嵌图提取」封装为可分阶段、可断点续跑、可跨项目复用的模块。

入口：

    python3 -m tools.ocr_pipeline --help
    python3 -m tools.ocr_pipeline run -i <PDF> -o <处理目录>
    python3 -m tools.ocr_pipeline batch --root 课程材料处理
    python3 -m tools.ocr_pipeline status --root 课程材料处理
"""

from __future__ import annotations

__version__ = "3.0.0"
SCHEMA_VERSION = 1

__all__ = ["__version__", "SCHEMA_VERSION"]

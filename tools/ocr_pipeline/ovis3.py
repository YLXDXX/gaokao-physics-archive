"""OvisOCR3 引擎封装、结构化版面解析、高清裁剪与断点续跑。"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from . import SCHEMA_VERSION, __version__
from .utils import (
    VISUAL_CATEGORIES,
    bbox_1000_to_pixels,
    ensure_dir,
    iter_batches,
    now_iso,
    one_line,
    read_json,
    read_text,
    safe_name,
    time_limit,
    write_json_atomic,
    write_text_atomic,
)
from . import state as st
from .pdf import PDFInfo, probe_pdf, render_page_images, write_source_info

PROMPT_STRUCTURED = (
    "Analyze the document structure and extract text content. Return a single JSON array "
    "in natural reading order.\n\n"
    "Each element follows this schema:\n"
    '`{"bbox": [x_min, y_min, x_max, y_max], "category": "string", "content": "string"}`\n\n'
    "Rules:\n"
    "1. The bbox coordinates are integers scaled to [0, 1000).\n"
    "2. The category is exactly one of:\n"
    '["abstract", "algorithm", "aside_text", "chart", "content", "display_formula", '
    '"doc_title", "figure_title", "footer", "footer_image", "footnote", "formula_number", '
    '"header", "header_image", "image", "inline_formula", "number", "paragraph_title", '
    '"reference_content", "seal", "table", "text", "vertical_text", "vision_footnote"].\n'
    "3. The content formatting depends on category:\n"
    '- For "footer_image", "header_image", "image", or "chart": write as an HTML image tag '
    '<img src="images/bbox_{x_min}_{y_min}_{x_max}_{y_max}.jpg" />.\n'
    '- For "display_formula" or "inline_formula": write in LaTeX.\n'
    '- For "table": write as a standard HTML `<table>...</table>`.\n'
    "- Otherwise: write in Markdown.\n"
    "4. Output must be strictly valid JSON. Properly escape quotes and special characters inside content."
)

PROMPT_MARKDOWN = (
    "Extract all readable content from the image in natural human reading order and output "
    "the result as a single Markdown document. For charts or images, represent them using an "
    'HTML image tag: <img src="images/bbox_{left}_{top}_{right}_{bottom}.jpg" />, where left, '
    "top, right, bottom are bounding box coordinates scaled to [0, 1000). Format formulas as "
    "LaTeX. Format tables as HTML: <table>...</table>. Transcribe all other text as standard "
    "Markdown. Preserve the original text without translation or paraphrasing."
)

PROMPT_LAYOUT = (
    "Analyze the document structure and return a single JSON array in natural reading order.\n\n"
    "Each element follows this schema:\n"
    '`{"bbox": [x_min, y_min, x_max, y_max], "category": "string"}`\n\n'
    "Rules:\n"
    "1. The bbox coordinates are integers scaled to [0, 1000).\n"
    "2. The category is exactly one of:\n"
    '["abstract", "algorithm", "aside_text", "chart", "content", "display_formula", '
    '"doc_title", "figure_title", "footer", "footer_image", "footnote", "formula_number", '
    '"header", "header_image", "image", "inline_formula", "number", "paragraph_title", '
    '"reference_content", "seal", "table", "text", "vertical_text", "vision_footnote"].'
)

PROMPTS = {
    "document_structured": PROMPT_STRUCTURED,
    "document_markdown": PROMPT_MARKDOWN,
    "document_layout": PROMPT_LAYOUT,
}

CATEGORIES = {
    "abstract", "algorithm", "aside_text", "chart", "content", "display_formula",
    "doc_title", "figure_title", "footer", "footer_image", "footnote", "formula_number",
    "header", "header_image", "image", "inline_formula", "number", "paragraph_title",
    "reference_content", "seal", "table", "text", "vertical_text", "vision_footnote",
}

# 匹配 images/bbox_... 或 page_N/images/bbox_...
BBOX_IMAGE_RE = re.compile(
    r'(?:page_\d+/)?images/bbox_(\d+)_(\d+)_(\d+)_(\d+)\.(?:jpg|jpeg|png)',
    re.I,
)


def _strip_fence(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json|markdown|html)?\s*\n?", "", text, flags=re.I)
        text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


def _recover_json_prefix(text: str) -> Tuple[List[Any], int]:
    """只保留完整前缀对象；不猜测/修补损坏的 JSON 语法。"""
    blocks: List[Any] = []
    if not text.startswith("["):
        return blocks, len(text)
    pos = 1
    decoder = json.JSONDecoder()
    while pos < len(text):
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if pos >= len(text) or text[pos] == "]":
            break
        try:
            block, end = decoder.raw_decode(text, pos)
        except json.JSONDecodeError:
            return blocks, len(text) - pos
        blocks.append(block)
        pos = end
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if pos < len(text) and text[pos] == ",":
            pos += 1
        elif pos < len(text) and text[pos] != "]":
            return blocks, len(text) - pos
    return blocks, 0


def _valid_bbox(value: Any) -> Optional[List[int]]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return None
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        out = [int(v) for v in value]
    except (TypeError, ValueError):
        return None
    if not all(0 <= v < 1000 for v in out):
        return None
    if out[0] > out[2] or out[1] > out[3]:
        return None
    return out


def parse_structured(raw: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any], str]:
    """解析 structured 模式输出；返回 (blocks, diagnostics, markdown)。"""
    text = _strip_fence(raw)
    if not text.startswith("["):
        start, end = text.find("["), text.rfind("]")
        if start != -1 and end > start:
            text = text[start : end + 1]
    diagnostics: Dict[str, Any] = {
        "json_complete": False,
        "schema_issues": [],
        "invalid_objects": [],
        "unparsed_tail_chars": 0,
        "parsed_objects": 0,
    }
    try:
        data = json.loads(text)
        if not isinstance(data, list):
            raise ValueError("Expected one JSON array")
        diagnostics["json_complete"] = True
    except ValueError as exc:
        diagnostics["parse_error"] = str(exc)
        data, tail = _recover_json_prefix(text)
        diagnostics["unparsed_tail_chars"] = tail

    blocks: List[Dict[str, Any]] = []
    for index, item in enumerate(data):
        if not isinstance(item, dict) or not isinstance(item.get("content"), str):
            diagnostics["invalid_objects"].append(index)
            continue
        bbox = _valid_bbox(item.get("bbox"))
        category = item.get("category")
        if bbox is None:
            diagnostics["schema_issues"].append({"index": index, "field": "bbox"})
        if not isinstance(category, str) or category not in CATEGORIES:
            diagnostics["schema_issues"].append({"index": index, "field": "category"})
            category = "text"
        blocks.append(
            {
                "index": len(blocks),
                "bbox": bbox,
                "category": category,
                "content": item["content"],
            }
        )
    diagnostics["parsed_objects"] = len(data)
    diagnostics["emitted_blocks"] = len(blocks)
    diagnostics["valid"] = (
        diagnostics["json_complete"]
        and not diagnostics["schema_issues"]
        and not diagnostics["invalid_objects"]
        and bool(blocks)
    )
    markdown = "\n\n".join(b["content"] for b in blocks)
    return blocks, diagnostics, markdown


def parse_layout(raw: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    text = _strip_fence(raw)
    if not text.startswith("["):
        start, end = text.find("["), text.rfind("]")
        if start != -1 and end > start:
            text = text[start : end + 1]
    diagnostics: Dict[str, Any] = {"json_complete": False, "schema_issues": [], "unparsed_tail_chars": 0}
    try:
        data = json.loads(text)
        if not isinstance(data, list):
            raise ValueError("Expected one JSON array")
        diagnostics["json_complete"] = True
    except ValueError as exc:
        diagnostics["parse_error"] = str(exc)
        data, tail = _recover_json_prefix(text)
        diagnostics["unparsed_tail_chars"] = tail
    layout = []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            diagnostics["schema_issues"].append({"index": index, "field": "object"})
            continue
        bbox = _valid_bbox(item.get("bbox"))
        category = item.get("category")
        if bbox is None or not isinstance(category, str) or category not in CATEGORIES:
            diagnostics["schema_issues"].append({"index": index, "field": "bbox/category"})
            continue
        layout.append({"bbox": bbox, "category": category})
    return layout, diagnostics


def clean_truncated_repeats(
    text: str,
    min_text_len: int = 8000,
    max_period: int = 200,
    min_period: int = 1,
    min_repeat_chars: int = 100,
    min_repeat_times: int = 5,
) -> str:
    n = len(text)
    if n < min_text_len:
        return text
    max_period = min(max_period, n - 1)
    for unit_len in range(min_period, max_period + 1):
        if text[n - 1] != text[n - 1 - unit_len]:
            continue
        match_len = 1
        idx = n - 2
        while idx >= unit_len and text[idx] == text[idx - unit_len]:
            match_len += 1
            idx -= 1
        total_len = match_len + unit_len
        repeat_times = total_len // unit_len
        tail_len = total_len % unit_len
        if repeat_times >= min_repeat_times and total_len >= min_repeat_chars:
            return text[: n - total_len + unit_len] + text[n - tail_len :]
    return text


def load_prompt(model_path: Path, name: str, prompt_dir: Optional[str] = None) -> str:
    base = Path(prompt_dir) if prompt_dir else Path(model_path) / "prompts"
    path = base / f"{name}.txt"
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    if name in PROMPTS:
        return PROMPTS[name]
    raise FileNotFoundError(f"找不到提示词：{path}")


class OvisOCR3Engine:
    """vLLM 后端；backend 参数仅供测试注入。"""

    def __init__(
        self,
        config: Dict[str, Any],
        logger: logging.Logger,
        backend: Optional[Callable[[List[Any], str], List[Tuple[str, str]]]] = None,
    ):
        self.config = config
        self.logger = logger
        self.backend = backend
        self.model = None
        self.tokenizer = None
        self.sampling = None
        self.model_path = Path(config["model"]["path"])

    def _load(self) -> None:
        if self.model is not None or self.backend is not None:
            return
        if not (self.model_path / "config.json").is_file():
            raise FileNotFoundError(
                f"未找到 OvisOCR3 模型：{self.model_path}（可用 --model-path 或 OVIS_MODEL 指定）"
            )
        try:
            from vllm import LLM, SamplingParams  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "当前 Python 环境没有 vllm；请使用 ovis_ocr 环境（原 OvisOCR2 环境）运行"
            ) from exc

        kwargs: Dict[str, Any] = {
            "model": str(self.model_path),
            "tensor_parallel_size": self.config["model"]["tensor_parallel_size"],
            "gpu_memory_utilization": self.config["model"]["gpu_memory_utilization"],
            "max_model_len": self.config["model"]["max_model_len"],
            "trust_remote_code": self.config["model"]["trust_remote_code"],
            "gdn_prefill_backend": self.config["model"]["gdn_prefill_backend"],
            "limit_mm_per_prompt": self.config["model"].get("limit_mm_per_prompt", {"image": 2}),
        }
        if self.config["model"].get("enforce_eager"):
            kwargs["enforce_eager"] = True
        if self.config["model"].get("skip_compile"):
            kwargs["compilation_config"] = {"mode": "NONE"}

        self.logger.info("加载 OvisOCR3：%s", self.model_path)
        self.model = LLM(**kwargs)
        self.tokenizer = self.model.get_tokenizer()
        self.sampling = SamplingParams(
            max_tokens=self.config["ovis"]["max_tokens"],
            temperature=self.config["ovis"]["temperature"],
        )
        self.logger.info("OvisOCR3 模型加载完成")

    def prompt(self, name: str) -> str:
        return load_prompt(self.model_path, name, self.config["ovis"].get("prompt_dir"))

    def infer_many(
        self,
        images: Sequence[Any],
        prompt_name: str,
        *,
        timeout: Optional[float] = None,
    ) -> List[Tuple[str, str]]:
        prompt = self.prompt(prompt_name)
        if self.backend is not None:
            return list(self.backend(list(images), prompt))
        self._load()
        assert self.tokenizer is not None and self.model is not None and self.sampling is not None
        requests = []
        for image in images:
            chat = self.tokenizer.apply_chat_template(
                [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image"},
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=self.config["ovis"].get("enable_thinking", False),
            )
            requests.append(
                {
                    "prompt": chat,
                    "multi_modal_data": {"image": image},
                    "mm_processor_kwargs": {
                        "images_kwargs": {
                            "min_pixels": self.config["ovis"]["min_pixels"],
                            "max_pixels": self.config["ovis"]["max_pixels"],
                        }
                    },
                }
            )
        with time_limit(timeout, f"OvisOCR3 推理（{len(images)} 页）"):
            outputs = self.model.generate(requests, self.sampling)
        results: List[Tuple[str, str]] = []
        for output in outputs:
            item = output.outputs[0]
            results.append((item.text, str(getattr(item, "finish_reason", "") or "")))
        return results

    def close(self) -> None:
        # vLLM 没有跨进程安全的释放接口；保持进程存活以便批量复用。
        return


def save_markdown_crops(
    markdown: str,
    page_image: Any,
    page: int,
    images_dir: Path,
    *,
    quality: int = 95,
) -> Tuple[str, List[Dict[str, Any]], List[str]]:
    """按 Markdown 中的 bbox 标签从整页原图裁剪，返回 (新 Markdown, 记录, 错误)。"""
    ensure_dir(images_dir)
    width, height = page_image.size
    records: List[Dict[str, Any]] = []
    errors: List[str] = []

    def repl(match: re.Match) -> str:
        left, top, right, bottom = (int(v) for v in match.groups())
        filename = f"page_{page}_bbox_{left}_{top}_{right}_{bottom}.jpg"
        target = images_dir / filename
        pixel = bbox_1000_to_pixels([left, top, right, bottom], width, height)
        if pixel is None:
            errors.append(f"无效图片框：page {page} bbox {[left, top, right, bottom]}")
            return match.group(0)
        records.append(
            {
                "page": page,
                "source": "ovis-markdown",
                "bbox": [left, top, right, bottom],
                "pixel_bbox": list(pixel),
                "image": f"images/{filename}",
            }
        )
        if not target.is_file() or target.stat().st_size == 0:
            try:
                page_image.crop(pixel).convert("RGB").save(target, quality=quality)
            except Exception as exc:  # pragma: no cover - 磁盘/编码异常
                errors.append(f"裁剪失败 {filename}: {exc}")
                return match.group(0)
        return f"images/{filename}"

    return BBOX_IMAGE_RE.sub(repl, markdown), records, errors


def save_block_crops(
    blocks: Sequence[Dict[str, Any]],
    page_image: Any,
    page: int,
    out_dir: Path,
    *,
    categories: Iterable[str] = VISUAL_CATEGORIES,
    fmt: str = "png",
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """按 structured blocks 的 bbox 从整页图裁剪视觉块（PNG 默认，无损）。"""
    ensure_dir(out_dir)
    width, height = page_image.size
    wanted = set(categories)
    records: List[Dict[str, Any]] = []
    errors: List[str] = []
    for block in blocks:
        category = block.get("category") or "unknown"
        if category not in wanted:
            continue
        bbox = block.get("bbox")
        pixel = bbox_1000_to_pixels(bbox or [], width, height)
        if pixel is None:
            errors.append(f"无效版面框：page {page} {category} {bbox}")
            continue
        idx = block.get("index", len(records))
        filename = f"{int(idx):03d}_{safe_name(category)}.{fmt}"
        target = out_dir / f"page_{page:04d}" / filename
        ensure_dir(target.parent)
        try:
            image = page_image.crop(pixel).convert("RGB")
            if fmt.lower() in ("jpg", "jpeg"):
                image.save(target, quality=95)
            else:
                image.save(target)
        except Exception as exc:  # pragma: no cover
            errors.append(f"裁剪失败 {target}: {exc}")
            continue
        records.append(
            {
                "page": page,
                "source": "ovis-structured",
                "category": category,
                "bbox": bbox,
                "pixel_bbox": list(pixel),
                "image": str(target.relative_to(out_dir)),
                "content": one_line(block.get("content", ""), 500),
            }
        )
    return records, errors


def _read_page_image(path: Path):
    from PIL import Image

    with Image.open(path) as image:
        return image.convert("RGB").copy()


def _load_or_probe(pdf_path: Path, config: Dict[str, Any]) -> PDFInfo:
    return probe_pdf(
        pdf_path,
        text_probe_pages=config["pdf"]["text_probe_pages"],
        text_min_chars=config["pdf"]["text_min_chars"],
        with_text=False,
    )


class OvisStage:
    """把一份 PDF 的每一页转成 Markdown + structured/layout 源数据。"""

    def __init__(
        self,
        proc_dir: Path,
        pdf_path: Path,
        config: Dict[str, Any],
        logger: logging.Logger,
        *,
        engine: Optional[OvisOCR3Engine] = None,
        force: bool = False,
        pages: Optional[Sequence[int]] = None,
    ):
        self.proc_dir = proc_dir
        self.pdf_path = pdf_path
        self.config = config
        self.logger = logger
        self.engine = engine
        self.force = force
        self.pages = list(pages) if pages else None
        self.info: Optional[PDFInfo] = None
        self._source_changed = False

    def _paths(self) -> Dict[str, Path]:
        root = self.proc_dir / "ovis"
        return {
            "root": root,
            "raw": root / "raw",
            "structured": root / "structured",
            "layout": root / "layout",
            "pages": root / "pages",
            "images": root / "images",
            "crops": root / "crops",
            "manifest": root / "manifest.json",
            "output": root / "output.md",
        }

    def _raw_valid(self, raw: Dict[str, Any], page: int, prompt_mode: str) -> bool:
        if not isinstance(raw, dict):
            return False
        if raw.get("status") != "done":
            return False
        if raw.get("schema_version") != SCHEMA_VERSION:
            return False
        if raw.get("source_sha256") != self.info.sha256:  # type: ignore[union-attr]
            return False
        if raw.get("prompt_mode") != prompt_mode:
            return False
        if raw.get("engine", {}).get("model") != str(Path(self.config["model"]["path"])):
            return False
        render = raw.get("render") or {}
        if int(render.get("dpi", 0)) != int(self.config["pdf"]["dpi"]):
            return False
        generation = raw.get("generation") or {}
        expected = {
            "max_tokens": self.config["ovis"]["max_tokens"],
            "temperature": self.config["ovis"]["temperature"],
            "min_pixels": self.config["ovis"]["min_pixels"],
            "max_pixels": self.config["ovis"]["max_pixels"],
        }
        for key, value in expected.items():
            if generation.get(key) != value:
                return False
        if int(raw.get("page", 0)) != page:
            return False
        paths = self._paths()
        for rel in (
            paths["structured"] / f"page_{page:04d}.json",
            paths["layout"] / f"page_{page:04d}.json",
            paths["pages"] / f"page_{page:04d}.md",
        ):
            if not rel.is_file():
                return False
        for match in BBOX_IMAGE_RE.finditer(raw.get("markdown") or ""):
            left, top, right, bottom = match.groups()
            image = paths["images"] / f"page_{page}_bbox_{left}_{top}_{right}_{bottom}.jpg"
            if not image.is_file():
                return False
        return True

    def _infer_page(
        self,
        page_image: Any,
        mode: str,
    ) -> Tuple[Dict[str, Tuple[str, str]], List[Dict[str, Any]], Dict[str, Any], str, str]:
        assert self.engine is not None
        responses: Dict[str, Tuple[str, str]] = {}
        blocks: List[Dict[str, Any]] = []
        diagnostics: Dict[str, Any] = {}
        markdown = ""
        timeout = self.config["ovis"]["page_timeout"]

        if mode == "both":
            md = self.engine.infer_many([page_image], "document_markdown", timeout=timeout)[0]
            struct = self.engine.infer_many([page_image], "document_structured", timeout=timeout)[0]
            responses["markdown"] = md
            responses["structured"] = struct
            blocks, diagnostics, _projected = parse_structured(struct[0])
            markdown = md[0]
        elif mode == "markdown":
            result = self.engine.infer_many([page_image], "document_markdown", timeout=timeout)[0]
            responses["markdown"] = result
            blocks = []
            diagnostics = {
                "json_complete": False,
                "schema_issues": [],
                "invalid_objects": [],
                "unparsed_tail_chars": 0,
                "valid": False,
                "note": "markdown mode：无 structured 版面数据",
            }
            markdown = result[0]
        elif mode == "layout":
            result = self.engine.infer_many([page_image], "document_layout", timeout=timeout)[0]
            responses["layout"] = result
            blocks, diagnostics = parse_layout(result[0])
            markdown = ""
        else:
            result = self.engine.infer_many([page_image], "document_structured", timeout=timeout)[0]
            responses["structured"] = result
            blocks, diagnostics, markdown = parse_structured(result[0])

        if mode in ("markdown", "both"):
            markdown = _strip_fence(markdown)
        markdown = clean_truncated_repeats(markdown.strip())
        if mode in ("markdown", "both"):
            finish = responses.get("markdown", ("", ""))[1]
        elif mode == "layout":
            finish = responses.get("layout", ("", ""))[1]
        else:
            finish = responses.get("structured", ("", ""))[1]
        return responses, blocks, diagnostics, markdown, finish

    def _save_page(
        self,
        page: int,
        page_image: Any,
        page_paths: Dict[str, Path],
        mode: str,
        responses: Dict[str, Tuple[str, str]],
        blocks: List[Dict[str, Any]],
        diagnostics: Dict[str, Any],
        markdown: str,
        finish: str,
    ) -> Dict[str, Any]:
        assert self.info is not None
        width, height = page_image.size
        for block in blocks:
            if block.get("bbox"):
                block["pixel_bbox"] = list(
                    bbox_1000_to_pixels(block["bbox"], width, height) or ()
                )
            block["page"] = page

        qualified, md_records, md_errors = save_markdown_crops(
            markdown,
            page_image,
            page,
            page_paths["images"],
            quality=int(self.config["ovis"].get("image_quality", 95)),
        )

        block_records: List[Dict[str, Any]] = []
        block_errors: List[str] = []
        if blocks and self.config["ovis"].get("save_block_crops", True):
            crop_image = page_image
            crop_dpi = int(self.config["ovis"].get("crop_dpi", self.config["pdf"]["dpi"]) or 0)
            # 裁图 DPI 至少不低于推理页图 DPI，避免把高清页反渲染成低清图。
            crop_dpi = max(crop_dpi, int(self.config["pdf"]["dpi"]))
            if crop_dpi != int(self.config["pdf"]["dpi"]):
                crop_dir = self.proc_dir / f"pageimages_crop_{crop_dpi}"
                crop_path = crop_dir / f"page_{page:04d}.png"
                if self.force or self._source_changed or not crop_path.is_file():
                    render_page_images(
                        self.pdf_path, crop_dir, dpi=crop_dpi, pages=[page],
                        force=self.force or self._source_changed,
                    )
                crop_image = _read_page_image(crop_path)
            block_records, block_errors = save_block_crops(
                blocks,
                crop_image,
                page,
                page_paths["crops"],
                categories=self.config["ovis"].get("crop_categories", VISUAL_CATEGORIES),
                fmt=self.config["ovis"].get("crop_format", "png"),
            )

        if mode == "markdown":
            complete = finish != "length" and bool(qualified.strip())
        elif mode == "both":
            complete = (
                finish != "length"
                and bool(diagnostics.get("json_complete"))
                and not diagnostics.get("invalid_objects")
                and not diagnostics.get("schema_issues")
            )
        else:
            complete = (
                finish != "length"
                and bool(diagnostics.get("json_complete", False))
                and not diagnostics.get("invalid_objects")
                and not diagnostics.get("schema_issues")
            )
        page_status = "done" if complete else "partial"
        raw = {
            "schema_version": SCHEMA_VERSION,
            "engine": {
                "name": "OvisOCR3",
                "model": str(Path(self.config["model"]["path"])),
            },
            "page": page,
            "source": self.info.name,
            "source_path": str(self.pdf_path),
            "source_sha256": self.info.sha256,
            "prompt_mode": mode,
            "render": {
                "dpi": self.config["pdf"]["dpi"],
                "width": width,
                "height": height,
                "image": str(page_paths["page_image"]),
            },
            "generation": {
                "min_pixels": self.config["ovis"]["min_pixels"],
                "max_pixels": self.config["ovis"]["max_pixels"],
                "max_tokens": self.config["ovis"]["max_tokens"],
                "temperature": self.config["ovis"]["temperature"],
            },
            "finish_reason": finish,
            "responses": {
                key: {"text": value[0], "finish_reason": value[1]}
                for key, value in responses.items()
            },
            "markdown": qualified,
            "diagnostics": diagnostics,
            "status": page_status,
            "warnings": md_errors + block_errors,
            "created_at": now_iso(),
        }
        write_json_atomic(page_paths["raw"] / f"page_{page:04d}.json", raw)
        write_text_atomic(page_paths["pages"] / f"page_{page:04d}.md", qualified + "\n")

        structured = {
            "schema_version": SCHEMA_VERSION,
            "page": page,
            "source_sha256": self.info.sha256,
            "width": width,
            "height": height,
            "render_dpi": self.config["pdf"]["dpi"],
            "blocks": blocks,
            "diagnostics": diagnostics,
            "markdown_crops": md_records,
            "block_crops": block_records,
            "warnings": md_errors + block_errors,
            "created_at": now_iso(),
        }
        write_json_atomic(page_paths["structured"] / f"page_{page:04d}.json", structured)
        layout = {
            "schema_version": SCHEMA_VERSION,
            "page": page,
            "source": "ovis-structured" if blocks else "ovis-markdown",
            "width": width,
            "height": height,
            "blocks": [
                {
                    "bbox": b.get("bbox"),
                    "category": b.get("category"),
                    "pixel_bbox": b.get("pixel_bbox"),
                    "score": 1.0,
                }
                for b in blocks
                if b.get("bbox")
            ],
        }
        write_json_atomic(page_paths["layout"] / f"page_{page:04d}.json", layout)
        return raw

    def _process_page(
        self,
        page: int,
        page_paths: Dict[str, Path],
        prompt_mode: str,
    ) -> Dict[str, Any]:
        page_image = _read_page_image(page_paths["page_image"])
        responses, blocks, diagnostics, markdown, finish = self._infer_page(
            page_image, prompt_mode
        )
        return self._save_page(
            page, page_image, page_paths, prompt_mode,
            responses, blocks, diagnostics, markdown, finish,
        )

    def _write_manifest(self, page_status: Dict[int, str]) -> None:
        paths = self._paths()
        info = self.info
        assert info is not None
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "engine": "OvisOCR3",
            "model": str(Path(self.config["model"]["path"])),
            "prompt_mode": self.config["ovis"]["prompt_mode"],
            "source": info.name,
            "source_path": str(self.pdf_path),
            "source_sha256": info.sha256,
            "pages": info.pages,
            "render_dpi": self.config["pdf"]["dpi"],
            "crop_dpi": max(
                int(self.config["ovis"].get("crop_dpi") or 0),
                int(self.config["pdf"]["dpi"]),
            ),
            "status": "complete"
            if all(v == "done" for v in page_status.values())
            else "partial",
            "page_status": {str(k): v for k, v in sorted(page_status.items())},
            "artifacts": {
                "output_md": "output.md",
                "raw": "raw/page_NNNN.json",
                "structured": "structured/page_NNNN.json",
                "layout": "layout/page_NNNN.json",
                "pages": "pages/page_NNNN.md",
                "crops": "crops/page_NNNN/",
                "images": "images/",
            },
            "updated_at": now_iso(),
        }
        write_json_atomic(paths["manifest"], manifest)
        crop_entries = []
        for page in range(1, info.pages + 1):
            data = read_json(paths["structured"] / f"page_{page:04d}.json", default={}) or {}
            for entry in data.get("block_crops") or []:
                crop_entries.append(entry)
        write_json_atomic(
            paths["crops"] / "manifest.json",
            {
                "schema_version": SCHEMA_VERSION,
                "source": info.name,
                "source_path": str(self.pdf_path),
                "source_sha256": info.sha256,
                "dpi": max(
                    int(self.config["ovis"].get("crop_dpi") or 0),
                    int(self.config["pdf"]["dpi"]),
                ),
                "format": self.config["ovis"].get("crop_format", "png"),
                "crops": crop_entries,
                "updated_at": now_iso(),
            },
        )

    def _write_output(self, page_status: Dict[int, str]) -> None:
        paths = self._paths()
        info = self.info
        assert info is not None
        page_markdowns: List[str] = []
        for page in range(1, info.pages + 1):
            path = paths["pages"] / f"page_{page:04d}.md"
            if page_status.get(page) in ("done", "partial", "existing") and path.is_file():
                page_markdowns.append(read_text(path).rstrip())
            else:
                page_markdowns.append(
                    f"<!-- 第 {page} 页未完成（status={page_status.get(page, 'missing')}） -->"
                )
        body = "\n\n".join(page_markdowns).strip() + "\n"
        if self.config["ovis"].get("include_metadata", True):
            header = (
                "---\n"
                f'title: "{info.name.rsplit(".", 1)[0]}"\n'
                f'source: "{info.name}"\n'
                f"source_path: \"{self.pdf_path}\"\n"
                f"pages: {info.pages}\n"
                'model: "OvisOCR3"\n'
                f'prompt_mode: "{self.config["ovis"]["prompt_mode"]}"\n'
                f'source_sha256: "{info.sha256}"\n'
                f'engine_version: "{__version__}"\n'
                "---\n\n"
            )
            body = header + body
        write_text_atomic(paths["output"], body)

    def run(self) -> Dict[str, Any]:
        paths = self._paths()
        for key in ("root", "raw", "structured", "layout", "pages", "images", "crops"):
            ensure_dir(paths[key])
        self.info = _load_or_probe(self.pdf_path, self.config)
        old = st.load_state(self.proc_dir).get("source") or {}
        old_sha = old.get("sha256") or (
            read_json(self.proc_dir / "source.json", default={}) or {}
        ).get("sha256")
        self._source_changed = bool(old_sha and old_sha != self.info.sha256)
        write_source_info(self.proc_dir, self.info)
        st.mark_source(self.proc_dir, self.info.as_dict())
        if self.info.pages <= 0:
            raise RuntimeError(f"PDF 无页面：{self.pdf_path}")

        prompt_mode = self.config["ovis"]["prompt_mode"]
        if prompt_mode not in {"structured", "markdown", "both", "layout"}:
            raise ValueError(f"未知 ovis prompt_mode：{prompt_mode}")

        selected = self.pages or list(range(1, self.info.pages + 1))
        selected = [p for p in selected if 1 <= p <= self.info.pages]
        if not selected:
            raise ValueError("没有可处理的页面")

        # 页面图先全部渲染，便于断点续跑与裁剪
        render_dir = self.proc_dir / "pageimages"
        render_meta = read_json(render_dir / ".render.json", default={}) or {}
        render_force = (
            self.force
            or self._source_changed
            or int(render_meta.get("dpi", 0) or 0) != int(self.config["pdf"]["dpi"])
        )
        render_page_images(
            self.pdf_path,
            render_dir,
            dpi=int(self.config["pdf"]["dpi"]),
            pages=selected,
            force=render_force,
        )
        page_paths = {
            "page_image": self.proc_dir / "pageimages" / "page_0001.png",
            "raw": paths["raw"],
            "structured": paths["structured"],
            "layout": paths["layout"],
            "pages": paths["pages"],
            "images": paths["images"],
            "crops": paths["crops"],
        }

        if self.engine is None:
            self.engine = OvisOCR3Engine(self.config, self.logger)
        st.set_stage(self.proc_dir, "ovis", "running", model=str(self.config["model"]["path"]))

        page_status: Dict[int, str] = {}
        pending: List[int] = []
        for page in selected:
            raw_path = paths["raw"] / f"page_{page:04d}.json"
            raw = read_json(raw_path, default=None)
            if not self.force and self._raw_valid(raw or {}, page, prompt_mode):
                page_status[page] = "done"
                st.set_page(self.proc_dir, "ovis", page, "done")
                continue
            pending.append(page)
        if page_status:
            self.logger.info("OvisOCR3 断点续跑：已完成 %d 页，待处理 %d 页",
                             len(page_status), len(pending))

        batch_size = max(1, int(self.config["ovis"].get("batch_size", 1)))
        for group in iter_batches(pending, batch_size):
            group = list(group)
            images = [
                _read_page_image(self.proc_dir / "pageimages" / f"page_{p:04d}.png")
                for p in group
            ]
            # 批量推理：成功则一次保存整组；任一环节失败则回退逐页，保证断点粒度。
            if len(group) > 1:
                try:
                    mode = prompt_mode
                    if mode == "both":
                        md_list = self.engine.infer_many(
                            images, "document_markdown",
                            timeout=float(self.config["ovis"]["page_timeout"]) * len(images),
                        )
                        st_list = self.engine.infer_many(
                            images, "document_structured",
                            timeout=float(self.config["ovis"]["page_timeout"]) * len(images),
                        )
                        prepared = []
                        if len(md_list) != len(group) or len(st_list) != len(group):
                            raise RuntimeError(
                                f"Ovis 批量返回数量不符：期望 {len(group)}，"
                                f"markdown={len(md_list)}，structured={len(st_list)}"
                            )
                        for md, struct in zip(md_list, st_list):
                            blocks, diagnostics, _ = parse_structured(struct[0])
                            prepared.append(({"markdown": md, "structured": struct},
                                             blocks, diagnostics,
                                             clean_truncated_repeats(_strip_fence(md[0]).strip()),
                                             md[1]))
                    elif mode == "markdown":
                        results = self.engine.infer_many(
                            images, "document_markdown",
                            timeout=float(self.config["ovis"]["page_timeout"]) * len(images),
                        )
                        if len(results) != len(group):
                            raise RuntimeError(
                                f"Ovis 批量返回数量不符：期望 {len(group)}，实际 {len(results)}"
                            )
                        prepared = []
                        for result in results:
                            prepared.append((
                                {"markdown": result}, [],
                                {"json_complete": False, "schema_issues": [],
                                 "invalid_objects": [], "unparsed_tail_chars": 0,
                                 "valid": False, "note": "markdown mode：无 structured 版面数据"},
                                clean_truncated_repeats(_strip_fence(result[0]).strip()),
                                result[1],
                            ))
                    elif mode == "layout":
                        results = self.engine.infer_many(
                            images, "document_layout",
                            timeout=float(self.config["ovis"]["page_timeout"]) * len(images),
                        )
                        if len(results) != len(group):
                            raise RuntimeError(
                                f"Ovis 批量返回数量不符：期望 {len(group)}，实际 {len(results)}"
                            )
                        prepared = []
                        for result in results:
                            blocks, diagnostics = parse_layout(result[0])
                            prepared.append(({"layout": result}, blocks, diagnostics, "", result[1]))
                    else:
                        results = self.engine.infer_many(
                            images, "document_structured",
                            timeout=float(self.config["ovis"]["page_timeout"]) * len(images),
                        )
                        if len(results) != len(group):
                            raise RuntimeError(
                                f"Ovis 批量返回数量不符：期望 {len(group)}，实际 {len(results)}"
                            )
                        prepared = []
                        for result in results:
                            blocks, diagnostics, markdown = parse_structured(result[0])
                            prepared.append((
                                {"structured": result}, blocks, diagnostics,
                                clean_truncated_repeats(markdown.strip()), result[1],
                            ))
                    for page, image, item in zip(group, images, prepared):
                        page_paths["page_image"] = (
                            self.proc_dir / "pageimages" / f"page_{page:04d}.png"
                        )
                        try:
                            saved = self._save_page(
                                page, image, page_paths, prompt_mode, *item
                            )
                            page_status[page] = saved.get("status", "done")
                            st.set_page(self.proc_dir, "ovis", page, page_status[page])
                            self.logger.info("OvisOCR3 第 %d/%d 页完成", page, self.info.pages)
                        except Exception as exc:
                            raise exc
                    continue
                except Exception as exc:
                    self.logger.warning(
                        "OvisOCR3 批量推理失败，回退逐页重试（%s）：%s",
                        ",".join(map(str, group)), exc,
                    )

            for page, image in zip(group, images):
                page_paths["page_image"] = self.proc_dir / "pageimages" / f"page_{page:04d}.png"
                existing = read_json(paths["raw"] / f"page_{page:04d}.json", default=None)
                if not self.force and self._raw_valid(existing or {}, page, prompt_mode):
                    page_status[page] = "done"
                    st.set_page(self.proc_dir, "ovis", page, "done")
                    continue
                try:
                    saved = self._process_page(page, page_paths, prompt_mode)
                    page_status[page] = saved.get("status", "done")
                    st.set_page(self.proc_dir, "ovis", page, page_status[page])
                    self.logger.info("OvisOCR3 第 %d/%d 页完成", page, self.info.pages)
                except Exception as exc:
                    page_status[page] = "failed"
                    st.set_page(self.proc_dir, "ovis", page, "failed", error=str(exc))
                    st.add_error(self.proc_dir, "ovis", f"page {page}: {exc}", page=page)
                    self.logger.error("OvisOCR3 第 %d 页失败：%s", page, exc)
                    for stale in (
                        paths["pages"] / f"page_{page:04d}.md",
                        paths["structured"] / f"page_{page:04d}.json",
                        paths["layout"] / f"page_{page:04d}.json",
                    ):
                        try:
                            if stale.is_file():
                                stale.unlink()
                        except OSError:
                            pass
                    write_json_atomic(
                        paths["raw"] / f"page_{page:04d}.error.json",
                        {
                            "page": page,
                            "status": "failed",
                            "error": str(exc),
                            "created_at": now_iso(),
                        },
                    )
                    if not self.config["pipeline"].get("continue_on_error", True):
                        raise
        # 补齐未选页面的状态（保留已有输出）
        for page in range(1, self.info.pages + 1):
            page_status.setdefault(
                page,
                "existing"
                if (paths["pages"] / f"page_{page:04d}.md").is_file()
                else "missing",
            )

        self._write_output(page_status)
        self._write_manifest(page_status)
        failed = [p for p, s in page_status.items() if s == "failed"]
        partial = [p for p, s in page_status.items() if s == "partial"]
        status = "done" if not failed and not partial else "partial"
        st.set_stage(
            self.proc_dir,
            "ovis",
            status,
            failed_pages=failed,
            partial_pages=partial,
            pages_done=sum(1 for s in page_status.values() if s == "done"),
            pages_total=self.info.pages,
        )
        return {
            "stage": "ovis",
            "status": status,
            "pages": self.info.pages,
            "failed_pages": failed,
            "partial_pages": partial,
            "page_status": page_status,
        }


def crop_saved_pages(
    proc_dir: Path,
    pdf_path: Path,
    *,
    dpi: int = 300,
    fmt: str = "png",
    categories: Optional[Iterable[str]] = None,
    out_dir: Optional[Path] = None,
    logger: Optional[logging.Logger] = None,
) -> Dict[str, Any]:
    """不重新 OCR，直接读取 ovis/structured 的 bbox，从原 PDF 高清渲染后重裁。"""
    logger = logger or logging.getLogger("ocr_pipeline")
    structured_dir = proc_dir / "ovis" / "structured"
    if not structured_dir.is_dir():
        raise FileNotFoundError(f"缺少 Ovis structured 数据：{structured_dir}")
    out = out_dir or (proc_dir / f"ocr_crops_{dpi}")
    ensure_dir(out)
    wanted = set(categories or VISUAL_CATEGORIES)
    info = probe_pdf(pdf_path, with_text=False)
    old_manifest = read_json(out / "manifest.json", default={}) or {}
    force_render = bool(
        old_manifest.get("source_sha256")
        and old_manifest.get("source_sha256") != info.sha256
    )
    page_dir = out / f"pageimages_{dpi}"
    all_records: List[Dict[str, Any]] = []
    errors: List[str] = []

    for page_file in sorted(structured_dir.glob("page_*.json")):
        data = read_json(page_file, default={})
        page = int(data.get("page") or page_file.stem.split("_")[-1])
        blocks = data.get("blocks") or []
        if not any(b.get("category") in wanted for b in blocks):
            continue
        image_path = page_dir / f"page_{page:04d}.png"
        if force_render or not image_path.is_file():
            render_page_images(pdf_path, page_dir, dpi=dpi, pages=[page], force=force_render)
        page_image = _read_page_image(image_path)
        records, errs = save_block_crops(
            blocks, page_image, page, out, categories=wanted, fmt=fmt
        )
        all_records.extend(records)
        errors.extend(errs)
        logger.info("重裁第 %d/%d 页：%d 个视觉块", page, info.pages, len(records))

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "source": info.name,
        "source_path": str(pdf_path),
        "source_sha256": info.sha256,
        "dpi": dpi,
        "format": fmt,
        "categories": sorted(wanted),
        "crops": all_records,
        "errors": errors,
        "created_at": now_iso(),
    }
    write_json_atomic(out / "manifest.json", manifest)
    return {"output": str(out), "count": len(all_records), "errors": errors}

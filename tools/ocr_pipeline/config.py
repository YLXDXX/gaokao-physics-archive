"""流水线默认配置、模型路径解析与配置合并。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from .utils import PROJECT_ROOT, deep_merge, read_json

DEFAULT_MODEL_PATH = "/home/shui/AI/ATH-MaaS/OvisOCR3"

DEFAULT_CONFIG: Dict[str, Any] = {
    "model": {
        "path": DEFAULT_MODEL_PATH,
        "tensor_parallel_size": 1,
        "gpu_memory_utilization": 0.8,
        "max_model_len": 32768,
        "trust_remote_code": True,
        "gdn_prefill_backend": "triton",
        "limit_mm_per_prompt": {"image": 2},
        "enforce_eager": True,
        "skip_compile": False,
    },
    "pdf": {
        "dpi": 300,
        "text_probe_pages": 3,
        "text_min_chars": 40,
    },
    "ovis": {
        # structured：一次调用同时得到文字 + bbox/category（推荐）
        # markdown：纯 Markdown（仅图片 bbox，无元素类别标签）
        # both：分别调用 markdown 与 structured，成本翻倍，便于交叉检查
        "prompt_mode": "structured",
        "prompt_dir": None,
        "min_pixels": 448 * 448,
        "max_pixels": 2880 * 2880,
        "max_tokens": 16384,
        "temperature": 0.0,
        "enable_thinking": False,
        "batch_size": 1,
        "page_timeout": 600,
        "include_metadata": True,
        "image_quality": 95,
        "save_block_crops": True,
        "crop_dpi": 300,
        "crop_format": "png",
        "crop_categories": [
            "image",
            "chart",
            "table",
            "header_image",
            "footer_image",
            "seal",
        ],
    },
    "paddle": {
        "host": "127.0.0.1",
        "port": 8203,
        "timeout": 600,
        "retries": 3,
        "retry_base_delay": 2.0,
        "page_chunk": 20,
        "service_max_pages": 50,
        "restructure": True,
        "include_metadata": True,
        "auto_serve": False,
        "serve_start_script": None,
        "serve_stop_script": None,
        "serve_start_timeout": 300,
        "pipeline_version": "1.6",
        "markdown_ignore_labels": [
            "number",
            "footnote",
            "header",
            "header_image",
            "footer",
            "footer_image",
            "aside_text",
        ],
        "use_doc_orientation_classify": False,
        "use_doc_unwarping": False,
        "use_layout_detection": True,
        "use_chart_recognition": False,
        "use_seal_recognition": False,
        "use_ocr_for_image_block": False,
    },
    "pipeline": {
        "stages": ["text", "images", "paddle", "ovis", "merge", "check"],
        "continue_on_error": True,
        "lock": True,
        "base_roots": [
            "课程基础材料",
            "周练月考基础材料",
            "补充基础材料",
        ],
        "merge_script": "tools/material_merge.py",
        "check_script": "tools/check_material.py",
        "images_script": "tools/pdf_extract_images.py",
    },
    "logging": {
        "level": "INFO",
        "dir": None,
    },
}


def _env_model_path() -> Optional[str]:
    for key in ("OVIS_MODEL", "OCR_MODEL_PATH", "OVIS_MODEL_PATH"):
        value = os.environ.get(key)
        if value:
            return value
    return None


def find_model_path(explicit: Optional[str] = None) -> str:
    """按显式参数 → 环境变量 → 默认位置 → 常见位置查找 OvisOCR3。"""
    candidates = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    env = _env_model_path()
    if env:
        candidates.append(Path(env).expanduser())
    candidates.extend(
        [
            Path(DEFAULT_MODEL_PATH),
            Path.cwd() / "OvisOCR3",
            Path.home() / "AI" / "ATH-MaaS" / "OvisOCR3",
            Path.home() / ".cache" / "OvisOCR3",
            PROJECT_ROOT / "OvisOCR3",
        ]
    )
    for cand in candidates:
        if (cand / "config.json").is_file():
            return str(cand.resolve())
    # 找不到时返回默认值，让上层给出明确错误
    return str(Path(candidates[0]).resolve())


def load_config(
    config_path: Optional[str] = None,
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    if config_path:
        path = Path(config_path)
        if not path.is_file():
            raise FileNotFoundError(f"配置文件不存在：{path}")
        user = read_json(path, default=None)
        if not isinstance(user, dict):
            raise ValueError(f"配置文件不是合法 JSON 对象：{path}")
        config = deep_merge(config, user)
    if overrides:
        config = deep_merge(config, overrides)

    if not config["model"].get("path"):
        config["model"]["path"] = find_model_path()
    else:
        config["model"]["path"] = find_model_path(config["model"]["path"])

    env_host = os.environ.get("PADDLE_HOST")
    env_port = os.environ.get("PADDLE_PORT")
    if env_host:
        config["paddle"]["host"] = env_host
    if env_port:
        try:
            config["paddle"]["port"] = int(env_port)
        except ValueError:
            pass

    config["_project_root"] = str(PROJECT_ROOT)
    return config


def script_path(config: Dict[str, Any], key: str) -> Optional[Path]:
    raw = config.get("pipeline", {}).get(key)
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path if path.is_file() else None


def save_config(path: Path, config: Dict[str, Any]) -> None:
    data = {k: v for k, v in config.items() if not k.startswith("_")}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

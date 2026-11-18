"""处理目录状态（.ocr_state.json）：阶段、逐页进度与断点判断。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from . import SCHEMA_VERSION
from .utils import now_iso, read_json, write_json_atomic


STATE_NAME = ".ocr_state.json"


def state_path(proc_dir: Path) -> Path:
    return proc_dir / STATE_NAME


def load_state(proc_dir: Path) -> Dict[str, Any]:
    data = read_json(state_path(proc_dir), default=None)
    if not isinstance(data, dict):
        data = {}
    data.setdefault("schema_version", SCHEMA_VERSION)
    data.setdefault("stages", {})
    data.setdefault("errors", [])
    return data


def save_state(proc_dir: Path, state: Dict[str, Any]) -> None:
    state["schema_version"] = SCHEMA_VERSION
    state["updated_at"] = now_iso()
    write_json_atomic(state_path(proc_dir), state)


def get_stage(proc_dir: Path, stage: str) -> Dict[str, Any]:
    return load_state(proc_dir).get("stages", {}).get(stage, {})


def set_stage(
    proc_dir: Path,
    stage: str,
    status: str,
    **extra: Any,
) -> Dict[str, Any]:
    state = load_state(proc_dir)
    info = state.setdefault("stages", {}).setdefault(stage, {})
    info.update(extra)
    info["status"] = status
    info["at"] = now_iso()
    save_state(proc_dir, state)
    return info


def set_page(
    proc_dir: Path,
    stage: str,
    page: int,
    status: str,
    **extra: Any,
) -> None:
    state = load_state(proc_dir)
    info = state.setdefault("stages", {}).setdefault(stage, {})
    pages = info.setdefault("pages", {})
    entry = pages.setdefault(str(page), {})
    entry.update(extra)
    entry["status"] = status
    entry["at"] = now_iso()
    save_state(proc_dir, state)


def add_error(proc_dir: Path, stage: str, message: str, **extra: Any) -> None:
    state = load_state(proc_dir)
    state.setdefault("errors", []).append(
        {"stage": stage, "message": message, "at": now_iso(), **extra}
    )
    # 只保留最近 200 条，避免状态文件无限增长
    state["errors"] = state["errors"][-200:]
    save_state(proc_dir, state)


def source_matches(proc_dir: Path, source_sha256: str) -> bool:
    state = load_state(proc_dir)
    source = state.get("source") or {}
    return bool(source.get("sha256")) and source.get("sha256") == source_sha256


def mark_source(proc_dir: Path, info: Dict[str, Any]) -> None:
    state = load_state(proc_dir)
    state["source"] = {
        "path": info.get("path"),
        "name": info.get("name"),
        "sha256": info.get("sha256"),
        "pages": info.get("pages"),
        "kind": info.get("kind"),
        "probed_at": info.get("probed_at"),
    }
    save_state(proc_dir, state)


def is_page_done(proc_dir: Path, stage: str, page: int) -> bool:
    info = get_stage(proc_dir, stage)
    entry = (info.get("pages") or {}).get(str(page)) or {}
    return entry.get("status") == "done"


def stage_done(proc_dir: Path, stage: str) -> bool:
    return get_stage(proc_dir, stage).get("status") == "done"

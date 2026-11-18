"""PaddleOCR-VL 服务客户端、分块识别、版面源数据保存与断点续跑。"""

from __future__ import annotations

import base64
import json
import logging
import re
import socket
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

import requests

from . import SCHEMA_VERSION
from .utils import (
    bbox_overlap,
    bbox_pixels_to_norm,
    ensure_dir,
    now_iso,
    one_line,
    read_json,
    read_text,
    retry_call,
    run_cmd,
    tmp_root,
    write_json_atomic,
    write_text_atomic,
)
from . import state as st
from .pdf import PDFInfo, probe_pdf, split_pdf_pages, write_source_info

def _normalise_options(config: Dict[str, Any]) -> Dict[str, Any]:
    p = config["paddle"]
    return {
        "markdown_ignore_labels": p.get("markdown_ignore_labels", []),
        "use_doc_orientation_classify": bool(p.get("use_doc_orientation_classify", False)),
        "use_doc_unwarping": bool(p.get("use_doc_unwarping", False)),
        "use_layout_detection": bool(p.get("use_layout_detection", True)),
        "use_chart_recognition": bool(p.get("use_chart_recognition", False)),
        "use_seal_recognition": bool(p.get("use_seal_recognition", False)),
        "use_ocr_for_image_block": bool(p.get("use_ocr_for_image_block", False)),
    }


class PaddleClient:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8203,
        timeout: float = 600,
        logger: Optional[logging.Logger] = None,
    ):
        self.base_url = f"http://{host}:{port}"
        self.timeout = timeout
        self.logger = logger or logging.getLogger("ocr_pipeline")
        self.session = requests.Session()

    def healthy(self, timeout: float = 3.0) -> bool:
        try:
            resp = self.session.get(f"{self.base_url}/layout-parsing", timeout=timeout)
            return resp.status_code in (200, 204, 400, 405, 415, 422, 500)
        except requests.exceptions.RequestException:
            try:
                parsed = urlparse(self.base_url)
                with socket.create_connection(
                    (parsed.hostname or "127.0.0.1", parsed.port or 80),
                    timeout=timeout,
                ):
                    return True
            except OSError:
                return False

    def parse_document(
        self,
        file_data: bytes,
        *,
        file_type: int = 0,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "file": base64.b64encode(file_data).decode("ascii"),
            "fileType": file_type,
            "visualize": False,
        }
        options = options or {}
        mapping = {
            "markdown_ignore_labels": "markdownIgnoreLabels",
            "use_doc_orientation_classify": "useDocOrientationClassify",
            "use_doc_unwarping": "useDocUnwarping",
            "use_layout_detection": "useLayoutDetection",
            "use_chart_recognition": "useChartRecognition",
            "use_seal_recognition": "useSealRecognition",
            "use_ocr_for_image_block": "useOcrForImageBlock",
        }
        for key, value in options.items():
            if key in mapping:
                payload[mapping[key]] = value
        resp = self.session.post(
            f"{self.base_url}/layout-parsing", json=payload, timeout=self.timeout
        )
        if resp.status_code != 200:
            raise RuntimeError(f"PaddleOCR-VL 解析失败：{resp.status_code} {resp.text[:500]}")
        data = resp.json()
        if "result" not in data:
            raise RuntimeError(f"PaddleOCR-VL 返回缺少 result：{str(data)[:500]}")
        return data["result"]

    def restructure_pages(
        self,
        pages: List[Dict[str, Any]],
        *,
        merge_tables: bool = True,
        relevel_titles: bool = True,
        concatenate_pages: bool = True,
    ) -> Dict[str, Any]:
        payload = {
            "pages": pages,
            "mergeTables": merge_tables,
            "relevelTitles": relevel_titles,
            "concatenatePages": concatenate_pages,
        }
        resp = self.session.post(
            f"{self.base_url}/restructure-pages", json=payload, timeout=self.timeout
        )
        if resp.status_code != 200:
            raise RuntimeError(f"PaddleOCR-VL 页面重构失败：{resp.status_code} {resp.text[:500]}")
        data = resp.json()
        return data.get("result", data)


class PaddleService:
    """按需启停 PaddleOCR-VL 服务；脚本默认在项目根。"""

    def __init__(
        self,
        config: Dict[str, Any],
        logger: logging.Logger,
        *,
        start_script: Optional[Path] = None,
        stop_script: Optional[Path] = None,
        log_file: Optional[Path] = None,
    ):
        self.config = config
        self.logger = logger
        p = config["paddle"]
        root = Path(config.get("_project_root") or ".")

        def _resolve(raw, default_name: str) -> Path:
            if not raw:
                return root / default_name
            path = Path(raw)
            return path if path.is_absolute() else root / path

        self.start_script = start_script or _resolve(
            p.get("serve_start_script"), "paddlex_serve_start.sh"
        )
        self.stop_script = stop_script or _resolve(
            p.get("serve_stop_script"), "paddlex_serve_stop.sh"
        )
        self.log_file = log_file or (tmp_root() / "paddle_serve.log")
        self.proc: Optional[subprocess.Popen] = None
        self.client = PaddleClient(
            host=p["host"], port=p["port"], timeout=10, logger=logger
        )

    def healthy(self) -> bool:
        return self.client.healthy()

    def start(self, timeout: Optional[float] = None) -> bool:
        if self.healthy():
            return True
        if not self.start_script.is_file():
            self.logger.error("找不到 Paddle 启动脚本：%s", self.start_script)
            return False
        ensure_dir(self.log_file.parent)
        self.logger.info("启动 PaddleOCR-VL 服务：%s", self.start_script)
        log = self.log_file.open("a", encoding="utf-8")
        self.proc = subprocess.Popen(
            ["bash", str(self.start_script)],
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            cwd=str(self.start_script.parent),
        )
        deadline = time.time() + float(
            timeout or self.config["paddle"].get("serve_start_timeout", 300)
        )
        while time.time() < deadline:
            if self.healthy():
                self.logger.info("PaddleOCR-VL 服务已就绪")
                return True
            if self.proc.poll() is not None:
                self.logger.error("Paddle 服务启动进程已退出，详见 %s", self.log_file)
                return False
            time.sleep(3)
        self.logger.error("Paddle 服务在超时内未就绪，详见 %s", self.log_file)
        return False

    def stop(self) -> None:
        if self.stop_script.is_file():
            run_cmd(["bash", str(self.stop_script)], check=False, timeout=60)
        elif self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()


def _save_b64_images(
    images: Dict[str, str],
    page: int,
    out_dir: Path,
    *,
    prefix: str = "",
) -> Dict[str, str]:
    ensure_dir(out_dir)
    mapping: Dict[str, str] = {}
    for key, b64 in (images or {}).items():
        name = Path(key).name or f"image_{len(mapping)}.jpg"
        filename = f"p{page:04d}_{prefix}{name}"
        target = out_dir / filename
        try:
            target.write_bytes(base64.b64decode(b64))
        except Exception as exc:
            raise RuntimeError(f"Paddle 返回图片解码失败：{key}（{exc}）") from exc
        mapping[key] = f"images/{filename}"
    return mapping


def _rewrite_image_paths(markdown: str, mapping: Dict[str, str]) -> str:
    if not markdown:
        return markdown
    text = markdown
    for old in sorted(mapping, key=len, reverse=True):
        new = mapping[old]
        text = text.replace(f'"{old}"', f'"{new}"')
        text = text.replace(f"'{old}'", f"'{new}'")
        text = text.replace(f"({old})", f"({new})")
        text = text.replace(f"src=\"{old}\"", f"src=\"{new}\"")
        text = text.replace(old, new)
    text = text.replace("imgs/", "images/")
    text = text.replace("/imgs/", "/images/")
    return text


def _normalise_paddle_page(pruned: Dict[str, Any], page: int) -> Dict[str, Any]:
    width = int(pruned.get("width") or 0)
    height = int(pruned.get("height") or 0)
    boxes = (pruned.get("layout_det_res") or {}).get("boxes") or []
    parsed = pruned.get("parsing_res_list") or []
    blocks: List[Dict[str, Any]] = []

    for box in boxes:
        coord = box.get("coordinate")
        if not coord or len(coord) != 4:
            continue
        label = str(box.get("label") or "text")
        content = ""
        best = 0.0
        for p in parsed:
            bb = p.get("block_bbox") or []
            if len(bb) != 4:
                continue
            score = bbox_overlap(coord, bb)
            if score > best:
                best = score
                content = p.get("block_content") or ""
        bbox = bbox_pixels_to_norm(coord, width, height)
        if bbox is None:
            continue
        blocks.append(
            {
                "bbox": bbox,
                "pixel_bbox": [round(float(v), 2) for v in coord],
                "category": label,
                "score": round(float(box.get("score", 0.0)), 4),
                "content": one_line(content, 1200),
            }
        )
    for p in parsed:
        bb = p.get("block_bbox") or []
        if len(bb) != 4:
            continue
        label = str(p.get("block_label") or "text")
        if any(
            b.get("pixel_bbox") == [round(float(v), 2) for v in bb]
            for b in blocks
        ):
            continue
        bbox = bbox_pixels_to_norm(bb, width, height)
        if bbox is None:
            continue
        blocks.append(
            {
                "bbox": bbox,
                "pixel_bbox": [round(float(v), 2) for v in bb],
                "category": label,
                "score": 1.0,
                "content": one_line(p.get("block_content") or "", 1200),
            }
        )
    blocks.sort(key=lambda b: (b.get("pixel_bbox") or [0, 0, 0, 0])[1])
    return {
        "schema_version": SCHEMA_VERSION,
        "page": page,
        "width": width,
        "height": height,
        "blocks": blocks,
        "layout_boxes": len(boxes),
        "parsing_blocks": len(parsed),
        "created_at": now_iso(),
    }


class PaddleStage:
    def __init__(
        self,
        proc_dir: Path,
        pdf_path: Path,
        config: Dict[str, Any],
        logger: logging.Logger,
        *,
        client: Optional[PaddleClient] = None,
        service: Optional[PaddleService] = None,
        force: bool = False,
        pages: Optional[Sequence[int]] = None,
    ):
        self.proc_dir = proc_dir
        self.pdf_path = pdf_path
        self.config = config
        self.logger = logger
        self.client = client
        self.service = service
        self.force = force
        self.pages = list(pages) if pages else None
        self.info: Optional[PDFInfo] = None
        self.restructure_errors: List[str] = []

    def _paths(self) -> Dict[str, Path]:
        root = self.proc_dir / "paddle"
        return {
            "root": root,
            "raw": root / "raw",
            "pages": root / "pages",
            "structured": root / "structured",
            "images": root / "images",
            "restructured": root / "restructured",
            "output": root / "output.md",
            "manifest": root / "manifest.json",
        }

    def _ensure_client(self) -> PaddleClient:
        if self.client is None:
            p = self.config["paddle"]
            self.client = PaddleClient(
                host=p["host"], port=p["port"], timeout=p["timeout"], logger=self.logger
            )
        if not self.client.healthy():
            if self.service and self.config["paddle"].get("auto_serve"):
                self.logger.info("Paddle 服务未就绪，尝试自动启动")
                if not self.service.start():
                    raise RuntimeError("PaddleOCR-VL 服务未启动且自动启动失败")
            else:
                raise RuntimeError(
                    f"PaddleOCR-VL 服务未启动：{self.client.base_url}；"
                    "请先运行 paddlex_serve_start.sh，或使用 --auto-serve"
                )
        return self.client

    def _chunk_plan(self) -> List[Tuple[int, int]]:
        assert self.info is not None
        total = self.info.pages
        if self.pages:
            # 只处理指定页时，按连续页分组
            pages = sorted(set(p for p in self.pages if 1 <= p <= total))
            chunks: List[Tuple[int, int]] = []
            for p in pages:
                if chunks and p == chunks[-1][1] + 1:
                    chunks[-1] = (chunks[-1][0], p)
                else:
                    chunks.append((p, p))
            return chunks
        size = int(self.config["paddle"].get("page_chunk", 20) or 20)
        size = max(1, min(size, int(self.config["paddle"].get("service_max_pages", 50) or 50)))
        return [(s, min(total, s + size - 1)) for s in range(1, total + 1, size)]

    def _chunk_hash(self, start: int, end: int) -> str:
        p = self.config["paddle"]
        raw = json.dumps(
            {
                "source": self.info.sha256 if self.info else "",
                "start": start,
                "end": end,
                "options": _normalise_options(self.config),
                "restructure": p.get("restructure"),
                "version": p.get("pipeline_version"),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        from .utils import sha256_text

        return sha256_text(raw)

    def _chunk_done(self, start: int, end: int, chunk_hash: str) -> bool:
        paths = self._paths()
        for page in range(start, end + 1):
            raw = read_json(paths["raw"] / f"page_{page:04d}.json", default=None)
            if not isinstance(raw, dict) or raw.get("status") != "done":
                return False
            if raw.get("chunk_hash") != chunk_hash:
                return False
            if not (paths["structured"] / f"page_{page:04d}.json").is_file():
                return False
            if not (paths["pages"] / f"page_{page:04d}.md").is_file():
                return False
            for rel in (raw.get("markdown") or {}).get("image_files", {}).values():
                if not (paths["root"] / rel).is_file():
                    return False
        return True

    def _save_page_result(
        self,
        *,
        page: int,
        result: Dict[str, Any],
        chunk: Tuple[int, int],
        chunk_hash: str,
        paths: Dict[str, Path],
    ) -> Dict[str, Any]:
        pruned = result.get("prunedResult") or {}
        markdown_obj = result.get("markdown") or {}
        markdown = markdown_obj.get("text") or ""
        mapping = _save_b64_images(
            markdown_obj.get("images") or {}, page, paths["images"]
        )
        markdown = _rewrite_image_paths(markdown, mapping)
        # 统一为 images/ 路径
        markdown = markdown.replace("imgs/", "images/")
        raw = {
            "schema_version": SCHEMA_VERSION,
            "engine": "PaddleOCR-VL",
            "pipeline_version": self.config["paddle"].get("pipeline_version", "1.6"),
            "page": page,
            "chunk": list(chunk),
            "chunk_hash": chunk_hash,
            "source": self.info.name,
            "source_path": str(self.pdf_path),
            "source_sha256": self.info.sha256,
            "status": "done",
            "prunedResult": pruned,
            "markdown": {"text": markdown, "image_files": mapping},
            "created_at": now_iso(),
        }
        write_json_atomic(paths["raw"] / f"page_{page:04d}.json", raw)
        write_text_atomic(paths["pages"] / f"page_{page:04d}.md", markdown.rstrip() + "\n")
        structured = _normalise_paddle_page(pruned, page)
        structured["markdown"] = markdown
        structured["image_files"] = mapping
        write_json_atomic(paths["structured"] / f"page_{page:04d}.json", structured)
        return raw

    def _run_chunk(
        self,
        start: int,
        end: int,
        paths: Dict[str, Path],
        client: PaddleClient,
    ) -> None:
        assert self.info is not None
        chunk_hash = self._chunk_hash(start, end)
        if not self.force and self._chunk_done(start, end, chunk_hash):
            self.logger.info("Paddle 断点续跑：第 %d-%d 页已完成，跳过", start, end)
            return
        if not client.healthy():
            if self.service and self.config["paddle"].get("auto_serve"):
                if not self.service.start():
                    raise RuntimeError("PaddleOCR-VL 服务自动启动失败")
            else:
                raise RuntimeError("PaddleOCR-VL 服务连接断开")

        work = tmp_root() / f"chunk_{self.pdf_path.stem}_{start}_{end}.pdf"
        try:
            if start == 1 and end == self.info.pages:
                source_pdf = self.pdf_path
            else:
                source_pdf = split_pdf_pages(self.pdf_path, work, start, end)
            data = source_pdf.read_bytes()
            options = _normalise_options(self.config)
            self.logger.info("PaddleOCR-VL 识别第 %d-%d 页（%.1f MB）", start, end, len(data) / 1048576)

            def _call():
                return client.parse_document(data, file_type=0, options=options)

            def _parse_with_retry():
                return retry_call(
                    _call,
                    attempts=int(self.config["paddle"].get("retries", 3)),
                    base_delay=float(self.config["paddle"].get("retry_base_delay", 2.0)),
                    logger=self.logger,
                    description=f"Paddle 第 {start}-{end} 页",
                )

            try:
                result = _parse_with_retry()
            except Exception:
                # 服务断连/显存异常时，自动重启一次再重试整个 chunk
                if self.service and self.config["paddle"].get("auto_serve"):
                    self.logger.warning("Paddle 请求失败，尝试重启服务后重试")
                    self.service.stop()
                    if self.service.start():
                        result = _parse_with_retry()
                    else:
                        raise
                else:
                    raise
            results = result.get("layoutParsingResults") or []
            expected = end - start + 1
            if len(results) != expected:
                raise RuntimeError(
                    f"Paddle 返回页数不符：期望 {expected}，实际 {len(results)}"
                    "（可能超过服务页数上限，请减小 --paddle-page-chunk）"
                )
            for offset, res in enumerate(results):
                page = start + offset
                self._save_page_result(
                    page=page, result=res, chunk=(start, end),
                    chunk_hash=chunk_hash, paths=paths,
                )
                st.set_page(self.proc_dir, "paddle", page, "done")
                self.logger.info("Paddle 第 %d/%d 页完成", page, self.info.pages)

            # 可选：服务端跨页重构（按 chunk 进行；跨 chunk 表格由后续人工/合并处理）
            if self.config["paddle"].get("restructure", True):
                pages_payload = [
                    {
                        "prunedResult": res.get("prunedResult") or {},
                        "markdownImages": (res.get("markdown") or {}).get("images"),
                    }
                    for res in results
                ]
                try:
                    restructured = client.restructure_pages(
                        pages_payload,
                        merge_tables=True,
                        relevel_titles=True,
                        concatenate_pages=True,
                    )
                    out = restructured.get("layoutParsingResults") or []
                    md = ((out[0] or {}).get("markdown") or {}) if out else {}
                    text = md.get("text") or ""
                    img_map = _save_b64_images(
                        md.get("images") or {}, start, paths["images"], prefix="merged_"
                    )
                    text = _rewrite_image_paths(text, img_map)
                    if not text.strip():
                        raise RuntimeError("跨页重构返回空正文")
                    target = paths["restructured"] / f"chunk_{start:04d}_{end:04d}.md"
                    write_text_atomic(target, text + "\n")
                    old_err = paths["restructured"] / f"chunk_{start:04d}_{end:04d}.error.json"
                    if old_err.is_file():
                        old_err.unlink()
                except Exception as exc:
                    msg = f"chunk {start}-{end}: {exc}"
                    self.restructure_errors.append(msg)
                    target = paths["restructured"] / f"chunk_{start:04d}_{end:04d}.error.json"
                    write_json_atomic(
                        target,
                        {"chunk": [start, end], "error": str(exc), "created_at": now_iso()},
                    )
                    self.logger.warning("Paddle 跨页重构失败（保留逐页结果）：%s", exc)

            st.set_stage(
                self.proc_dir, "paddle", "running",
                last_chunk=f"{start}-{end}", chunk_hash=chunk_hash,
            )
        finally:
            if work.exists():
                try:
                    work.unlink()
                except OSError:
                    pass

    def _write_output(self) -> None:
        paths = self._paths()
        assert self.info is not None
        # 按页顺序拼接；有完整重构结果的 chunk 用重构 Markdown，否则用逐页 Markdown。
        chunk_md: Dict[Tuple[int, int], str] = {}
        if self.config["paddle"].get("restructure", True):
            for f in sorted(paths["restructured"].glob("chunk_*.md")):
                m = re.search(r"chunk_(\d+)_(\d+)", f.name)
                if not m:
                    continue
                start, end = int(m.group(1)), int(m.group(2))
                chunk_hash = self._chunk_hash(start, end)
                if not all(
                    (read_json(paths["raw"] / f"page_{p:04d}.json", default={}) or {}).get("status")
                    == "done"
                    and (read_json(paths["raw"] / f"page_{p:04d}.json", default={}) or {}).get("chunk_hash")
                    == chunk_hash
                    for p in range(start, end + 1)
                ):
                    continue
                text = read_text(f).rstrip()
                if text:
                    chunk_md[(start, end)] = text

        parts: List[str] = []
        page = 1
        while page <= self.info.pages:
            chosen = next(
                (c for c in chunk_md if c[0] == page),
                None,
            )
            if chosen is None:
                chosen = next(
                    (c for c in chunk_md if c[0] < page <= c[1]),
                    None,
                )
            if chosen is not None:
                parts.append(chunk_md[chosen])
                page = chosen[1] + 1
                continue
            p = paths["pages"] / f"page_{page:04d}.md"
            parts.append(
                read_text(p).rstrip() if p.is_file() else f"<!-- 第 {page} 页未完成 -->"
            )
            page += 1
        body = "\n\n".join(x for x in parts if x).strip() + "\n"
        if self.config["paddle"].get("include_metadata", True):
            header = (
                "---\n"
                f'title: "{self.info.name.rsplit(".", 1)[0]}"\n'
                f'source: "{self.info.name}"\n'
                f"source_path: \"{self.pdf_path}\"\n"
                f"pages: {self.info.pages}\n"
                f'model: "PaddleOCR-VL-{self.config["paddle"].get("pipeline_version", "1.6")}"\n'
                f'source_sha256: "{self.info.sha256}"\n'
                "---\n\n"
            )
            body = header + body
        write_text_atomic(paths["output"], body)

    def _write_manifest(self) -> None:
        paths = self._paths()
        assert self.info is not None
        statuses = {}
        for page in range(1, self.info.pages + 1):
            raw = read_json(paths["raw"] / f"page_{page:04d}.json", default=None)
            statuses[str(page)] = (raw or {}).get("status", "missing")
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "engine": "PaddleOCR-VL",
            "pipeline_version": self.config["paddle"].get("pipeline_version", "1.6"),
            "service": f"{self.config['paddle']['host']}:{self.config['paddle']['port']}",
            "source": self.info.name,
            "source_path": str(self.pdf_path),
            "source_sha256": self.info.sha256,
            "pages": self.info.pages,
            "page_chunk": self.config["paddle"].get("page_chunk"),
            "restructure": self.config["paddle"].get("restructure"),
            "restructure_errors": list(self.restructure_errors),
            "status": "complete"
            if all(v == "done" for v in statuses.values()) and not self.restructure_errors
            else "partial",
            "page_status": statuses,
            "artifacts": {
                "output_md": "output.md",
                "raw": "raw/page_NNNN.json",
                "structured": "structured/page_NNNN.json",
                "pages": "pages/page_NNNN.md",
                "images": "images/",
                "restructured": "restructured/chunk_NNNN_NNNN.md",
            },
            "updated_at": now_iso(),
        }
        write_json_atomic(paths["manifest"], manifest)

    def run(self) -> Dict[str, Any]:
        paths = self._paths()
        self.restructure_errors = []
        for key in ("root", "raw", "pages", "structured", "images", "restructured"):
            ensure_dir(paths[key])
        self.info = probe_pdf(
            self.pdf_path,
            text_probe_pages=self.config["pdf"]["text_probe_pages"],
            text_min_chars=self.config["pdf"]["text_min_chars"],
            with_text=False,
        )
        write_source_info(self.proc_dir, self.info)
        st.mark_source(self.proc_dir, self.info.as_dict())
        st.set_stage(self.proc_dir, "paddle", "running")
        chunks = self._chunk_plan()
        self.logger.info("Paddle 分块计划：%s", chunks)
        pending = [
            (start, end) for start, end in chunks
            if self.force or not self._chunk_done(start, end, self._chunk_hash(start, end))
        ]
        client = self._ensure_client() if pending else None
        if not pending:
            self.logger.info("Paddle 断点续跑：全部 chunk 已完成，无需启动服务")
        errors: List[str] = []
        for start, end in pending:
            assert client is not None
            try:
                self._run_chunk(start, end, paths, client)
            except Exception as exc:
                msg = f"chunk {start}-{end}: {exc}"
                errors.append(msg)
                st.add_error(self.proc_dir, "paddle", msg)
                self.logger.error("Paddle %s 失败：%s", f"{start}-{end}", exc)
                if not self.config["pipeline"].get("continue_on_error", True):
                    st.set_stage(self.proc_dir, "paddle", "error", error=str(exc))
                    raise
        if self.config["paddle"].get("restructure", True):
            for start, end in chunks:
                target = paths["restructured"] / f"chunk_{start:04d}_{end:04d}.md"
                if not target.is_file():
                    msg = f"chunk {start}-{end}: 缺少跨页重构结果"
                    if msg not in self.restructure_errors:
                        self.restructure_errors.append(msg)
        self._write_output()
        self._write_manifest()
        statuses = [
            (read_json(paths["raw"] / f"page_{p:04d}.json", default={}) or {}).get("status")
            for p in range(1, self.info.pages + 1)
        ]
        status = "done" if all(s == "done" for s in statuses) and not self.restructure_errors else "partial"
        st.set_stage(
            self.proc_dir,
            "paddle",
            status,
            pages_done=sum(1 for s in statuses if s == "done"),
            pages_total=self.info.pages,
            errors=errors + self.restructure_errors,
        )
        return {
            "stage": "paddle",
            "status": status,
            "errors": errors + self.restructure_errors,
        }

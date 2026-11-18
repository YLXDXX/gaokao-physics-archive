"""分阶段批量编排：探测 / 文本 / 内嵌图 / Paddle / Ovis / 合并 / 校验。"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .paddle import PaddleClient, PaddleService

from . import SCHEMA_VERSION
from .config import script_path
from .ovis3 import OvisOCR3Engine, OvisStage
from .pdf import (
    discover_processing_dirs,
    extract_text,
    locate_source_pdf,
    probe_pdf,
    write_source_info,
)
from .utils import (
    FileLock,
    PROJECT_ROOT,
    ensure_dir,
    now_iso,
    one_line,
    read_json,
    read_text,
    safe_rel,
    write_json_atomic,
)
from . import state as st

DEFAULT_STAGES = ["text", "images", "paddle", "ovis", "merge", "check"]
ALL_STAGES = set(DEFAULT_STAGES)


def canonical_stages(stages: Sequence[str]) -> List[str]:
    """按推荐顺序排列阶段，确保 Paddle 服务先于 Ovis 使用 GPU。"""
    unknown = [s for s in stages if s not in ALL_STAGES]
    if unknown:
        raise ValueError(f"未知阶段：{unknown}；可用：{','.join(DEFAULT_STAGES)}")
    wanted = set(stages)
    return [s for s in DEFAULT_STAGES if s in wanted]


@dataclass
class Job:
    pdf: Optional[Path]
    out: Path
    note: str = ""

    def key(self) -> str:
        return safe_rel(self.out)


def _parse_jobs_file(path: Path) -> List[Job]:
    text = read_text(path).strip()
    jobs: List[Job] = []
    if not text:
        return jobs
    if text.startswith("{") or text.startswith("["):
        data = json.loads(text)
        if isinstance(data, dict):
            data = data.get("jobs", [])
        for item in data:
            if isinstance(item, dict):
                pdf = item.get("pdf") or item.get("input")
                out = item.get("output") or item.get("out")
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                pdf, out = item[0], item[1]
            else:
                continue
            if pdf and out:
                jobs.append(Job(Path(pdf).expanduser(), Path(out).expanduser()))
        return jobs
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t") if "\t" in line else line.split()
        if len(parts) >= 2:
            jobs.append(Job(Path(parts[0]).expanduser(), Path(parts[1]).expanduser()))
    return jobs


def _resolve_base_roots(config: Dict[str, Any], extras: Sequence[str] = ()) -> List[Path]:
    roots = []
    for raw in list(config["pipeline"].get("base_roots", [])) + list(extras):
        p = Path(raw)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        roots.append(p)
    return roots


def discover_jobs(
    *,
    config: Dict[str, Any],
    jobs_file: Optional[str] = None,
    roots: Sequence[str] = (),
    source_root: Optional[str] = None,
    output_root: Optional[str] = None,
    base_roots: Sequence[str] = (),
    only: Optional[str] = None,
    limit: int = 0,
    extra_pairs: Sequence[str] = (),
) -> List[Job]:
    jobs: List[Job] = []
    if jobs_file:
        jobs.extend(_parse_jobs_file(Path(jobs_file)))
    for pair in extra_pairs:
        if "::" in pair:
            pdf, out = pair.split("::", 1)
        elif "=" in pair:
            pdf, out = pair.split("=", 1)
        elif "\t" in pair:
            pdf, out = pair.split("\t", 1)
        else:
            parts = pair.split()
            if len(parts) != 2:
                raise ValueError(f"--pair 需要 PDF::OUT：{pair}")
            pdf, out = parts
        jobs.append(Job(Path(pdf), Path(out)))

    if source_root or output_root:
        if not source_root or not output_root:
            raise ValueError("--source-root 与 --output-root 必须同时给出")
        src = Path(source_root)
        out = Path(output_root)
        if not src.is_dir():
            raise FileNotFoundError(f"源 PDF 根目录不存在：{src}")
        for pdf in sorted(src.rglob("*.pdf")):
            rel = pdf.relative_to(src)
            jobs.append(Job(pdf, out / rel.parent / pdf.stem))

    if roots:
        bases = _resolve_base_roots(config, base_roots)
        for root in roots:
            root_path = Path(root)
            is_leaf = root_path.is_dir() and any(
                (root_path / name).exists() for name in ("ovis", "paddle", "merged.md")
            )
            proc_root = None if is_leaf else (root_path if root_path.is_dir() else root_path.parent)
            for proc_dir in discover_processing_dirs([root_path]):
                pdf = locate_source_pdf(proc_dir, base_roots=bases, proc_root=proc_root)
                jobs.append(Job(pdf, proc_dir, note="" if pdf else "未定位源 PDF"))

    # 去重（同一输出目录保留第一个有 PDF 的）
    merged: Dict[Path, Job] = {}
    for job in jobs:
        key = job.out.resolve()
        if key not in merged or (not merged[key].pdf and job.pdf):
            merged[key] = job
    jobs = sorted(merged.values(), key=lambda j: str(j.out))

    if only:
        jobs = [j for j in jobs if only in str(j.out) or (j.pdf and only in str(j.pdf))]
    if limit:
        jobs = jobs[:limit]
    return jobs


def _job_lock(job: Job, config: Dict[str, Any]) -> Optional[FileLock]:
    if not config["pipeline"].get("lock", True):
        return None
    ensure_dir(job.out)
    lock = FileLock(job.out / ".ocr_lock")
    if not lock.acquire():
        return None
    return lock


def _run_script(
    script: Optional[Path],
    args: Sequence[str],
    *,
    logger: logging.Logger,
    cwd: Optional[Path] = None,
    timeout: Optional[float] = None,
) -> Tuple[bool, str]:
    if not script or not Path(script).is_file():
        return False, "脚本不存在"
    cmd = [sys.executable, str(script), *map(str, args)]
    try:
        proc = subprocess.run(
            cmd, cwd=str(cwd or PROJECT_ROOT), capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return False, f"脚本超时：{script}"
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "").strip()
        logger.error("%s 失败（rc=%d）：%s", Path(script).name, proc.returncode, one_line(msg, 500))
        return False, msg
    return True, proc.stdout


def _stage_text(job: Job, config: Dict[str, Any], logger: logging.Logger, force: bool) -> Dict[str, Any]:
    if not job.pdf or not job.pdf.is_file():
        raise FileNotFoundError(f"缺少源 PDF：{job.out}")
    info = probe_pdf(
        job.pdf,
        text_probe_pages=config["pdf"]["text_probe_pages"],
        text_min_chars=config["pdf"]["text_min_chars"],
    )
    old_sha = (st.load_state(job.out).get("source") or {}).get("sha256") or (
        read_json(job.out / "source.json", default={}) or {}
    ).get("sha256")
    write_source_info(job.out, info)
    st.mark_source(job.out, info.as_dict())
    target = job.out / "pdftotext.txt"
    if force or (old_sha and old_sha != info.sha256) or not target.is_file() or target.stat().st_size == 0:
        extract_text(job.pdf, target, force=True)
    st.set_stage(
        job.out, "text", "done",
        kind=info.kind, pages=info.pages, text_chars=info.text_chars,
    )
    return {"status": "done", "kind": info.kind, "pages": info.pages}


def _stage_images(job: Job, config: Dict[str, Any], logger: logging.Logger, force: bool) -> Dict[str, Any]:
    if not job.pdf:
        raise FileNotFoundError(f"缺少源 PDF：{job.out}")
    script = script_path(config, "images_script")
    if not script:
        logger.warning("未找到 pdf_extract_images.py，跳过内嵌图提取：%s", job.out)
        return {"status": "skipped", "reason": "script-missing"}
    args = ["--pdf", str(job.pdf), "--out", str(job.out / "pdfimages"), "--quiet"]
    if force:
        args.append("--force")
    ok, output = _run_script(script, args, logger=logger)
    if not ok:
        raise RuntimeError(f"内嵌图提取失败：{one_line(output, 400)}")
    st.set_stage(job.out, "images", "done")
    return {"status": "done"}


def _stage_paddle(
    job: Job,
    config: Dict[str, Any],
    logger: logging.Logger,
    force: bool,
    *,
    service: Optional[PaddleService],
    client: Optional[PaddleClient],
) -> Dict[str, Any]:
    if not job.pdf:
        raise FileNotFoundError(f"缺少源 PDF：{job.out}")
    from .paddle import PaddleStage

    stage = PaddleStage(
        job.out, job.pdf, config, logger,
        client=client, service=service, force=force,
    )
    result = stage.run()
    return result


def _stage_ovis(
    job: Job,
    config: Dict[str, Any],
    logger: logging.Logger,
    force: bool,
    *,
    engine: Optional[OvisOCR3Engine],
) -> Dict[str, Any]:
    if not job.pdf:
        raise FileNotFoundError(f"缺少源 PDF：{job.out}")
    stage = OvisStage(
        job.out, job.pdf, config, logger, engine=engine, force=force
    )
    return stage.run()


def _merged_source_hash(job: Job) -> str:
    """按 material_merge 的规则计算 ovis/paddle 底稿哈希。"""
    h = hashlib.sha256()
    for rel in ("ovis/output.md", "paddle/output.md"):
        _p = job.out / rel
        h.update(_p.read_bytes() if _p.is_file() else b"")
        h.update(b"\x00")
    return h.hexdigest()


def _merged_needs_rebuild(job: Job) -> bool:
    merged = job.out / "merged.md"
    if not merged.is_file():
        return True
    text = read_text(merged)
    m = re.search(r"^source_sha256:\s*([0-9a-fA-F]{64})\s*$", text, re.M)
    if not m:
        return True
    return m.group(1).lower() != _merged_source_hash(job)


def _stage_merge(job: Job, config: Dict[str, Any], logger: logging.Logger, force: bool) -> Dict[str, Any]:
    script = script_path(config, "merge_script")
    if not script:
        logger.warning("未找到 material_merge.py，跳过 merged.md：%s", job.out)
        return {"status": "skipped", "reason": "script-missing"}
    if not (job.out / "ovis" / "output.md").is_file() or not (
        job.out / "paddle" / "output.md"
    ).is_file():
        logger.warning("缺少 ovis/paddle 输出，跳过 merged.md：%s", job.out)
        return {"status": "skipped", "reason": "missing-input"}
    rebuild = force or _merged_needs_rebuild(job)
    args = [str(job.out), "--force"] if rebuild else [str(job.out)]
    ok, output = _run_script(script, args, logger=logger)
    if not ok:
        raise RuntimeError(f"生成 merged.md 失败：{one_line(output, 400)}")
    st.set_stage(job.out, "merge", "done")
    return {"status": "done"}


def _stage_check(job: Job, config: Dict[str, Any], logger: logging.Logger) -> Dict[str, Any]:
    script = script_path(config, "check_script")
    if not script:
        logger.warning("未找到 check_material.py，跳过完整性校验：%s", job.out)
        return {"status": "skipped", "reason": "script-missing"}
    ok, output = _run_script(script, [str(job.out)], logger=logger)
    if not ok:
        raise RuntimeError(f"完整性校验失败：{one_line(output, 800)}")
    return {"status": "done", "output": one_line(output, 300)}


def run_stages(
    jobs: Sequence[Job],
    stages: Sequence[str],
    *,
    config: Dict[str, Any],
    logger: logging.Logger,
    force: bool = False,
    force_stages: Sequence[str] = (),
    dry_run: bool = False,
    auto_serve: bool = False,
    fail_fast: bool = False,
    report_path: Optional[Path] = None,
) -> Dict[str, Any]:
    stages = canonical_stages(stages)
    if not stages:
        raise ValueError("没有可执行的阶段")
    unknown_force = [s for s in force_stages if s not in ALL_STAGES]
    if unknown_force:
        raise ValueError(f"未知 --force-stage：{unknown_force}")
    force_set = set(force_stages)
    logger.info("批量作业 %d 个；阶段：%s%s", len(jobs), ", ".join(stages),
                "（dry-run）" if dry_run else "")
    report: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "started_at": now_iso(),
        "finished_at": None,
        "stages": list(stages),
        "jobs": [],
        "summary": {},
    }
    engine: Optional[OvisOCR3Engine] = None
    service: Optional[PaddleService] = None
    client: Optional[PaddleClient] = None
    stage_results: Dict[str, Dict[str, int]] = {s: {"done": 0, "skipped": 0, "failed": 0} for s in stages}
    failed_jobs: set[str] = set()
    stop_all = False

    try:
        if "paddle" in stages and not dry_run:
            from .paddle import PaddleClient, PaddleService

            client = PaddleClient(
                host=config["paddle"]["host"],
                port=config["paddle"]["port"],
                timeout=config["paddle"]["timeout"],
                logger=logger,
            )
            service = PaddleService(config, logger)
            if auto_serve and not dry_run:
                # 延迟到真正有未完成 chunk 时再启动，避免全部完成后仍白等模型加载。
                config["paddle"]["auto_serve"] = True
            elif not dry_run and not client.healthy():
                logger.debug(
                    "PaddleOCR-VL 服务未就绪；需要时可用 --auto-serve 或先运行 paddlex_serve_start.sh"
                )

        for stage in stages:
            if stop_all:
                break
            logger.info("===== 阶段：%s =====", stage)
            for index, job in enumerate(jobs, 1):
                if stop_all:
                    break
                job_key = job.key()
                entry = next((e for e in report["jobs"] if e["out"] == job_key), None)
                if entry is None:
                    entry = {
                        "pdf": str(job.pdf) if job.pdf else None,
                        "out": job_key,
                        "stages": {},
                        "errors": [],
                    }
                    report["jobs"].append(entry)
                if dry_run:
                    print(f"[dry-run] {stage:7s} {job_key}")
                    entry["stages"][stage] = {"status": "dry-run"}
                    stage_results[stage]["skipped"] += 1
                    continue
                logger.info("[%d/%d] %s ← %s", index, len(jobs), stage, job_key)
                lock = _job_lock(job, config)
                if config["pipeline"].get("lock", True) and lock is None:
                    msg = "目录已被其它进程锁定"
                    logger.warning("%s：%s", job_key, msg)
                    entry["stages"][stage] = {"status": "locked"}
                    entry["errors"].append(msg)
                    stage_results[stage]["failed"] += 1
                    failed_jobs.add(job_key)
                    continue
                force_this = force or stage in force_set or "__all__" in force_set
                try:
                    if stage == "text":
                        res = _stage_text(job, config, logger, force_this)
                    elif stage == "images":
                        res = _stage_images(job, config, logger, force_this)
                    elif stage == "paddle":
                        res = _stage_paddle(
                            job, config, logger, force_this,
                            service=service, client=client,
                        )
                    elif stage == "ovis":
                        if engine is None:
                            engine = OvisOCR3Engine(config, logger)
                        res = _stage_ovis(
                            job, config, logger, force_this, engine=engine
                        )
                    elif stage == "merge":
                        res = _stage_merge(job, config, logger, force_this)
                    elif stage == "check":
                        res = _stage_check(job, config, logger)
                    else:
                        res = {"status": "skipped", "reason": "unknown-stage"}
                    status = res.get("status", "done")
                    entry["stages"][stage] = res
                    if status in ("failed", "partial"):
                        stage_results[stage]["failed"] += 1
                        failed_jobs.add(job_key)
                    elif status == "skipped":
                        stage_results[stage]["skipped"] += 1
                    else:
                        stage_results[stage]["done"] += 1
                except Exception as exc:
                    msg = one_line(str(exc), 800)
                    logger.error("%s %s 失败：%s", job_key, stage, msg)
                    entry["stages"][stage] = {"status": "failed", "error": msg}
                    entry["errors"].append(f"{stage}: {msg}")
                    stage_results[stage]["failed"] += 1
                    failed_jobs.add(job_key)
                    st.add_error(job.out, stage, msg)
                    if fail_fast:
                        stop_all = True
                        break
                finally:
                    if lock:
                        lock.release()
            logger.info(
                "阶段 %s 完成：成功 %d，跳过 %d，失败 %d",
                stage,
                stage_results[stage]["done"],
                stage_results[stage]["skipped"],
                stage_results[stage]["failed"],
            )
            if stage == "paddle" and service and not dry_run:
                # 只有流水线自己启动的服务，或后面还要跑 Ovis（必须释放显存）时才停止。
                if auto_serve or "ovis" in stages:
                    service.stop()
                service = None
            if stop_all:
                break
    finally:
        if service and not dry_run:
            service.stop()
        if engine:
            engine.close()

    report["finished_at"] = now_iso()
    report["summary"] = {
        "jobs": len(jobs),
        "failed_jobs": sorted(failed_jobs),
        "stages": stage_results,
    }
    if report_path:
        ensure_dir(report_path.parent)
        write_json_atomic(report_path, report)
    return report


def status_rows(jobs: Sequence[Job], config: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for job in jobs:
        out = job.out
        source = read_json(out / "source.json", default={}) or {}
        ovis_manifest = read_json(out / "ovis" / "manifest.json", default={}) or {}
        paddle_manifest = read_json(out / "paddle" / "manifest.json", default={}) or {}
        pdfimages_manifest = read_json(out / "pdfimages" / "manifest.json", default={}) or {}
        pages = source.get("pages", "")
        if not pages:
            head = read_text(out / "ovis" / "output.md")[:1200]
            m = re.search(r"^pages:\s*(\d+)", head, re.M)
            if m:
                pages = int(m.group(1))
        def _count_pages(directory: Path) -> int:
            return len(
                [p for p in directory.glob("page_*.json") if not p.name.endswith(".error.json")]
            )

        ovis_raw = _count_pages(out / "ovis" / "raw")
        ovis_struct = _count_pages(out / "ovis" / "structured")
        paddle_raw = _count_pages(out / "paddle" / "raw")
        paddle_struct = _count_pages(out / "paddle" / "structured")
        row = {
            "out": safe_rel(out),
            "pdf": str(job.pdf) if job.pdf else source.get("path", ""),
            "kind": source.get("kind", ""),
            "pages": pages,
            "text": (out / "pdftotext.txt").is_file(),
            "images": pdfimages_manifest.get("count", 0) if pdfimages_manifest else ("dir" if (out / "pdfimages").is_dir() else 0),
            "ovis": (out / "ovis" / "output.md").is_file(),
            "ovis_status": ovis_manifest.get("status", ""),
            "ovis_engine": ovis_manifest.get("engine", ""),
            "ovis_raw": ovis_raw,
            "ovis_structured": ovis_struct,
            "paddle": (out / "paddle" / "output.md").is_file(),
            "paddle_status": paddle_manifest.get("status", ""),
            "paddle_raw": paddle_raw,
            "paddle_structured": paddle_struct,
            "merged": (out / "merged.md").is_file(),
            "needs_upgrade": ovis_manifest.get("engine") not in ("", "OvisOCR3"),
        }
        rows.append(row)
    return rows


def print_status(rows: Sequence[Dict[str, Any]]) -> None:
    if not rows:
        print("没有匹配的作业。")
        return
    print(f"{'处理目录':50s} {'页':>4s} {'文':>2s} {'图':>4s} {'Ovis':>5s} {'Paddle':>6s} {'合并':>4s} 引擎/状态")
    for r in rows:
        ovis = r["ovis_status"] or ("有" if r["ovis"] else "-")
        paddle = r["paddle_status"] or ("有" if r["paddle"] else "-")
        upgrade = " [需升级]" if r["needs_upgrade"] else ""
        print(
            f"{r['out'][:50]:50s} {str(r['pages']):>4s} "
            f"{'Y' if r['text'] else '-':>2s} {str(r['images']):>4s} "
            f"{ovis:>5s} {paddle:>6s} {'Y' if r['merged'] else '-':>4s} "
            f"{r['ovis_engine']}{upgrade}"
        )


def plan_rows(jobs: Sequence[Job], stages: Sequence[str]) -> List[Dict[str, Any]]:
    return [
        {
            "pdf": str(j.pdf) if j.pdf else None,
            "out": str(j.out),
            "stages": list(stages),
            "note": j.note,
        }
        for j in jobs
    ]

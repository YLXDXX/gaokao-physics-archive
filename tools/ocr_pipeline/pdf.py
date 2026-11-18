"""PDF 探测、页面渲染、pdftotext 旁证与源文件定位。"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, asdict
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .utils import (
    ensure_dir,
    read_json,
    now_iso,
    read_text,
    run_cmd,
    sha256_file,
    write_json_atomic,
    write_text_atomic,
)


@dataclass
class PDFInfo:
    path: str
    name: str
    pages: int
    page_width: float = 0.0
    page_height: float = 0.0
    encrypted: bool = False
    title: str = ""
    producer: str = ""
    file_size: int = 0
    sha256: str = ""
    has_text: bool = False
    text_chars: int = 0
    kind: str = "unknown"  # text / scan
    probed_at: str = ""

    def as_dict(self) -> Dict:
        return asdict(self)


def _parse_pdfinfo(text: str) -> Dict[str, str]:
    data: Dict[str, str] = {}
    for line in text.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            data[key.strip()] = value.strip()
    return data


def _probe_with_pdfinfo(path: Path) -> Dict[str, str]:
    try:
        proc = run_cmd(["pdfinfo", str(path)], check=False, timeout=60)
    except (OSError, RuntimeError):
        return {}
    if proc.returncode != 0:
        return {}
    return _parse_pdfinfo(proc.stdout)


def _probe_with_pymupdf(path: Path) -> Dict[str, str]:
    try:
        import pymupdf  # type: ignore
    except ImportError:
        return {}
    try:
        doc = pymupdf.open(path)
        try:
            page = doc[0] if len(doc) else None
            rect = page.rect if page is not None else None
            return {
                "Pages": str(len(doc)),
                "Page size": f"{rect.width} x {rect.height} pts" if rect else "",
                "Encrypted": "yes" if doc.is_encrypted else "no",
                "Title": (doc.metadata or {}).get("title", ""),
                "Producer": (doc.metadata or {}).get("producer", ""),
            }
        finally:
            doc.close()
    except Exception:
        return {}


def _text_probe(path: Path, pages: int, probe_pages: int) -> Tuple[int, str]:
    """抽样首页/中间/末页判断文字版，避免封面空白导致误判为扫描版。"""
    if pages <= 0:
        return 0, ""
    probe_pages = max(1, int(probe_pages or 1))
    candidates = [1, max(1, pages // 2), pages, max(1, pages // 3), max(1, 2 * pages // 3)]
    sample = sorted({p for p in candidates if 1 <= p <= pages})[:probe_pages]
    texts: List[str] = []
    for page in sample:
        try:
            proc = run_cmd(
                ["pdftotext", "-layout", "-f", str(page), "-l", str(page), str(path), "-"],
                check=False,
                timeout=120,
            )
        except (OSError, RuntimeError):
            continue
        if proc.returncode == 0:
            texts.append(proc.stdout)
    text = "\n".join(texts)
    chars = len(re.sub(r"\s+", "", text))
    return chars, text


def probe_pdf(
    path: Path,
    *,
    text_probe_pages: int = 3,
    text_min_chars: int = 40,
    with_text: bool = True,
) -> PDFInfo:
    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError(str(path))
    data = _probe_with_pdfinfo(path) or _probe_with_pymupdf(path)
    try:
        pages = int(data.get("Pages", "0") or 0)
    except ValueError:
        pages = 0
    if pages <= 0:
        raise RuntimeError(f"无法读取 PDF 页数：{path}")
    width = height = 0.0
    m = re.search(r"([\d.]+)\s*x\s*([\d.]+)", data.get("Page size", ""))
    if m:
        width, height = float(m.group(1)), float(m.group(2))
    chars = 0
    if with_text:
        chars, _ = _text_probe(path, pages, text_probe_pages)
    has_text = chars >= max(1, text_min_chars)
    return PDFInfo(
        path=str(path),
        name=path.name,
        pages=pages,
        page_width=width,
        page_height=height,
        encrypted=data.get("Encrypted", "").lower().startswith("yes"),
        title=data.get("Title", ""),
        producer=data.get("Producer", ""),
        file_size=path.stat().st_size,
        sha256=sha256_file(path),
        has_text=has_text,
        text_chars=chars,
        kind="text" if has_text else "scan",
        probed_at=now_iso(),
    )


def write_source_info(proc_dir: Path, info: PDFInfo) -> Path:
    target = proc_dir / "source.json"
    old = read_json(target, default=None)
    # Ovis/Paddle 阶段为省时间不做文字探测；若 text 阶段已写入同一 PDF 的
    # has_text/kind，则保留，避免 source.json 被覆盖成 scan。
    if isinstance(old, dict) and old.get("sha256") == info.sha256:
        for key in ("has_text", "text_chars", "kind"):
            if key in old and old[key] not in (None, ""):
                setattr(info, key, old[key])
    write_json_atomic(target, info.as_dict())
    return target


def read_source_info(proc_dir: Path) -> Optional[Dict]:
    from .utils import read_json

    return read_json(proc_dir / "source.json")


def extract_text(pdf: Path, out_file: Path, *, force: bool = False) -> str:
    """pdftotext -layout 旁证；扫描版无文字时写入占位行，避免空文件告警。"""
    if out_file.is_file() and out_file.stat().st_size > 0 and not force:
        return read_text(out_file)
    ensure_dir(out_file.parent)
    try:
        proc = run_cmd(
            ["pdftotext", "-layout", str(pdf), str(out_file)],
            check=False,
            timeout=300,
        )
    except (OSError, RuntimeError) as exc:
        placeholder = f"（pdftotext 不可用或失败：{exc}）\n"
        write_text_atomic(out_file, placeholder)
        return placeholder
    text = read_text(out_file)
    if proc.returncode != 0 or not re.sub(r"\s+", "", text):
        # 保留 stderr 供排查，但写入明确占位，满足 check_material 的非空要求
        placeholder = "（扫描版 PDF，pdftotext 无有效文本，旁证不适用）\n"
        if proc.returncode != 0:
            placeholder += f"（pdftotext 退出码 {proc.returncode}：{proc.stderr.strip()[:300]}）\n"
        write_text_atomic(out_file, placeholder)
        return placeholder
    return text


def _render_with_pymupdf(
    pdf: Path,
    out_dir: Path,
    dpi: int,
    pages: Sequence[int],
    force: bool,
) -> List[Path]:
    try:
        import pymupdf  # type: ignore
    except ImportError:
        return []
    zoom = dpi / 72.0
    matrix = pymupdf.Matrix(zoom, zoom)
    outputs: List[Path] = []
    doc = pymupdf.open(pdf)
    try:
        for page_no in pages:
            if page_no < 1 or page_no > len(doc):
                raise ValueError(f"页码越界：{page_no}/{len(doc)}")
            target = out_dir / f"page_{page_no:04d}.png"
            outputs.append(target)
            if target.is_file() and target.stat().st_size > 0 and not force:
                continue
            page = doc[page_no - 1]
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            tmp = target.with_suffix(".tmp.png")
            pix.save(str(tmp))
            os.replace(tmp, target)
    finally:
        doc.close()
    return outputs


def _render_with_pdftoppm(
    pdf: Path,
    out_dir: Path,
    dpi: int,
    pages: Sequence[int],
    force: bool,
) -> List[Path]:
    outputs: List[Path] = []
    for page_no in pages:
        target = out_dir / f"page_{page_no:04d}.png"
        outputs.append(target)
        if target.is_file() and target.stat().st_size > 0 and not force:
            continue
        prefix = out_dir / f".pdftoppm_{page_no:04d}"
        run_cmd(
            [
                "pdftoppm",
                "-f", str(page_no),
                "-l", str(page_no),
                "-r", str(dpi),
                "-png",
                "-singlefile",
                str(pdf),
                str(prefix),
            ],
            timeout=300,
        )
        produced = prefix.with_suffix(".png")
        if not produced.is_file():
            raise RuntimeError(f"pdftoppm 未生成页面：{page_no}")
        os.replace(produced, target)
    return outputs


def render_page_images(
    pdf: Path,
    out_dir: Path,
    *,
    dpi: int = 300,
    pages: Optional[Iterable[int]] = None,
    force: bool = False,
) -> List[Path]:
    """把 PDF 页面渲染为 PNG；文件名 page_0001.png，已存在则跳过。"""
    ensure_dir(out_dir)
    if pages is None:
        info = probe_pdf(pdf, with_text=False)
        page_list = list(range(1, info.pages + 1))
    else:
        page_list = sorted({int(p) for p in pages if int(p) > 0})
    if not page_list:
        return []
    outputs = _render_with_pymupdf(pdf, out_dir, dpi, page_list, force)
    if not outputs:
        outputs = _render_with_pdftoppm(pdf, out_dir, dpi, page_list, force)
    missing = [p for p in outputs if not p.is_file() or p.stat().st_size == 0]
    if missing:
        raise RuntimeError(
            f"页面渲染失败：{missing[:3]}；请安装 PyMuPDF 或 poppler（pdftoppm）"
        )
    try:
        write_json_atomic(out_dir / ".render.json", {"dpi": dpi, "pages": page_list})
    except OSError:
        pass
    return outputs


def split_pdf_pages(
    pdf: Path,
    out_pdf: Path,
    start: int,
    end: int,
) -> Path:
    """用 qpdf 截取 1-based 闭区间页面；qpdf 缺失时回退 PyMuPDF。"""
    ensure_dir(out_pdf.parent)
    if start <= 0 or end < start:
        raise ValueError(f"非法页范围：{start}-{end}")
    if shutil.which("qpdf"):
        run_cmd(
            [
                "qpdf", "--empty", "--pages", str(pdf),
                f"{start}-{end}", "--", str(out_pdf),
            ],
            timeout=300,
        )
        return out_pdf
    try:
        import pymupdf  # type: ignore
    except ImportError as exc:
        raise RuntimeError("需要 qpdf（或 PyMuPDF）来分割超过服务页数上限的 PDF") from exc
    src = pymupdf.open(pdf)
    dst = pymupdf.open()
    try:
        dst.insert_pdf(src, from_page=start - 1, to_page=end - 1)
        dst.save(str(out_pdf))
    finally:
        dst.close()
        src.close()
    return out_pdf


@lru_cache(maxsize=32)
def _files_by_name(root: str) -> Dict[str, List[Path]]:
    """基础材料根目录内的文件名索引；避免逐处理目录重复 rglob。"""
    index: Dict[str, List[Path]] = {}
    root_path = Path(root)
    if not root_path.is_dir():
        return index
    for p in root_path.rglob("*"):
        if p.is_file():
            index.setdefault(p.name, []).append(p)
    return index


def _read_ovis_source(proc_dir: Path) -> Optional[str]:
    for rel in ("ovis/output.md", "merged.md"):
        path = proc_dir / rel
        if not path.is_file():
            continue
        head = read_text(path)[:1200]
        m = re.search(r'^source:\s*"?([^"\n]+)"?', head, re.M)
        if m:
            return m.group(1).strip()
    return None


def locate_source_pdf(
    proc_dir: Path,
    *,
    base_roots: Sequence[Path],
    proc_root: Optional[Path] = None,
) -> Optional[Path]:
    """由 ovis/output.md 的 source 字段在基础材料根目录中定位源 PDF。

    先按处理目录相对处理根的路径前缀匹配，再退化为文件名唯一匹配。
    """
    info = read_json(proc_dir / "source.json", default=None)
    if isinstance(info, dict) and info.get("path"):
        direct = Path(info["path"])
        if direct.is_file():
            return direct.resolve()
    name = _read_ovis_source(proc_dir)
    if not name:
        return None
    direct = Path(name)
    if direct.is_file():
        return direct.resolve()

    rel = None
    if proc_root:
        try:
            rel = proc_dir.resolve().relative_to(proc_root.resolve())
        except ValueError:
            rel = None

    candidates: List[Tuple[int, Path]] = []
    for root in base_roots:
        root = Path(root)
        if not root.is_dir():
            continue
        for cand in _files_by_name(str(root.resolve())).get(name, []):
            if rel is not None:
                try:
                    crel = cand.parent.resolve().relative_to(root.resolve())
                except ValueError:
                    continue
                n = len(crel.parts)
                if n <= len(rel.parts) and rel.parts[:n] == crel.parts:
                    candidates.append((n, cand))
            else:
                candidates.append((0, cand))
    if candidates:
        candidates.sort(key=lambda t: t[0], reverse=True)
        return candidates[0][1].resolve()

    # 前缀层级不一致时（如处理目录 材料处理/力学/1.1，源 PDF 在
    # pdf/力学/第1章/1.1.pdf），退化为文件名唯一匹配；仅全库唯一时采用，
    # 避免同名 PDF 误配。
    matches: List[Path] = []
    for root in base_roots:
        root = Path(root)
        if not root.is_dir():
            continue
        matches.extend(_files_by_name(str(root.resolve())).get(name, []))
    if len(matches) == 1:
        return matches[0].resolve()
    return None


def discover_processing_dirs(roots: Iterable[Path]) -> List[Path]:
    found = set()
    for root in roots:
        root = Path(root)
        if root.is_file():
            found.add(root.parent)
            continue
        if not root.is_dir():
            continue
        for name in ("ovis", "paddle"):
            for p in root.rglob(name):
                if p.is_dir():
                    found.add(p.parent)
        for name in ("merged.md", "pdftotext.txt", "source.json"):
            for p in root.rglob(name):
                found.add(p.parent)
    return sorted(found)

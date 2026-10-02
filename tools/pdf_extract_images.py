#!/usr/bin/env python3
"""tools/pdf_extract_images.py

从源 PDF **无损提取内嵌图片**（封装 poppler ``pdfimages``），供后续裁剪
（splitpicture）与制卷使用。

背景与定位：
    * 本项目源材料均为 **文字版 PDF**（WPS 导出），其中图片**几乎全部是位图**
      （600 dpi 内嵌图），质量远高于 OCR 引擎自动裁切的图片；
    * 本工具只做**提取**，不做裁剪；需要裁剪的图片交 **splitpicture** 逐张处理；
    * 仅当整页里**找不到内嵌位图**（纯矢量图）时，才改用 ``pdftoppm`` 整页渲染再裁
      （不在本工具内自动渲染，避免与“无损提取”语义混淆）。

产物（位于每个处理目录下，随 ``材料处理/`` 一并 Git 忽略）：:

    <处理目录>/pdfimages/
        ├── p<页>_<序号>.<ext>     # 按原始编码无损导出
        └── manifest.json          # 清单：页码/序号/尺寸/编码/dpi/哈希/源 PDF

源 PDF 的定位：读取 ``<处理目录>/ovis/output.md`` 头部 front matter 的
``source:`` 字段，再在 ``Docx/`` 下按目录结构（``<年>/<年_地区>.pdf``）匹配。

用法::

    # 批量：递归材料处理根目录
    python3 tools/pdf_extract_images.py --root 材料处理

    # 指定若干处理目录
    python3 tools/pdf_extract_images.py 材料处理/2026/湖北

    # 单文件：直接给定 PDF 与输出目录（不依赖 ovis/output.md）
    python3 tools/pdf_extract_images.py --pdf <源PDF> --out <输出目录>

默认仅处理**尚无 manifest.json** 的目录；``--force`` 覆盖重建。
退出码：0 全部成功；1 存在源 PDF 缺失或提取失败。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ROOTS = ["材料处理"]
BASE_ROOTS = ["Docx"]
OUTDIR_NAME = "pdfimages"
MANIFEST_NAME = "manifest.json"

# ovis/output.md front matter 中的 source 字段
FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)
SOURCE_RE = re.compile(r"^source:\s*\"?([^\"\n]+?)\"?\s*$", re.M)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_front_matter(path: Path) -> Dict[str, str]:
    """读取 Markdown 头部 ``---`` front matter 为简单键值字典。"""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return {}
    m = FRONT_MATTER_RE.match(text)
    if not m:
        return {}
    data: Dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        data[key.strip()] = value.strip().strip('"')
    return data


def parse_pdfimages_list(output: str) -> List[Dict[str, object]]:
    """解析 ``pdfimages -list`` 表格，返回按顺序的图片元数据列表。"""
    rows: List[Dict[str, object]] = []
    lines = output.strip().splitlines()
    if not lines:
        return rows
    # 跳过表头两行（标题 + 分隔线）
    for line in lines[2:]:
        parts = line.split()
        if len(parts) < 6:
            continue
        try:
            page = int(parts[0])
            num = int(parts[1])
            width = int(parts[3])
            height = int(parts[4])
        except (ValueError, IndexError):
            continue
        # 列尾固定为 "... x-ppi y-ppi size ratio"，故 xppi/yppi 位于倒数第 4、3 列
        xppi = yppi = 0
        if len(parts) >= 4 and parts[-4].isdigit() and parts[-3].isdigit():
            xppi, yppi = int(parts[-4]), int(parts[-3])
        rows.append({
            "page": page,
            "num": num,
            "type": parts[2],
            "width": width,
            "height": height,
            "color": parts[5] if len(parts) > 5 else "",
            "comp": int(parts[6]) if len(parts) > 6 and parts[6].isdigit() else 0,
            "bpc": int(parts[7]) if len(parts) > 7 and parts[7].isdigit() else 0,
            "enc": parts[8] if len(parts) > 8 else "",
            "xppi": xppi,
            "yppi": yppi,
        })
    return rows


def find_processing_dirs(roots: List[Path]) -> List[Path]:
    """定位所有处理目录（含 ovis/output.md 者）。"""
    dirs = set()
    for root in roots:
        if root.is_file():
            dirs.add(root.parent)
            continue
        if not root.is_dir():
            continue
        for p in root.rglob("ovis/output.md"):
            dirs.add(p.parent.parent)
    return sorted(dirs)


def locate_source_pdf(proc_dir: Path, proc_root: Path, source_name: str,
                      base_roots: List[Path]) -> Optional[Path]:
    """在基准材料根目录下按目录结构匹配源 PDF。

    匹配规则：候选 PDF 的父目录**相对基准根**的路径，是处理目录**相对处理根**的
    路径的前缀（处理目录可能比源目录多出 ``第N课时`` / ``<PDF 基名>`` 一层）。
    """
    try:
        rel = proc_dir.relative_to(proc_root)
    except ValueError:
        rel = proc_dir
    candidates: List[Tuple[int, Path]] = []
    for base in base_roots:
        if not base.is_dir():
            continue
        for cand in base.rglob(source_name):
            if not cand.is_file():
                continue
            try:
                crel = cand.parent.relative_to(base)
            except ValueError:
                continue
            n = len(crel.parts)
            if n <= len(rel.parts) and rel.parts[:n] == crel.parts:
                candidates.append((n, cand))
    if not candidates:
        # 回退：高考库目录为 材料处理/<年>/<地区>，若前缀匹配落空，
        # 则基准根下同名 PDF 唯一时直接采用。
        all_match = [
            c for base in base_roots if base.is_dir()
            for c in base.rglob(source_name) if c.is_file()
        ]
        return all_match[0] if len(all_match) == 1 else None
    candidates.sort(key=lambda t: t[0], reverse=True)
    return candidates[0][1]


def find_processing_root(proc_dir: Path) -> Optional[Path]:
    """向上查找处理根目录（材料处理）。"""
    for parent in [proc_dir, *proc_dir.parents]:
        if parent.name in DEFAULT_ROOTS:
            return parent
    return None


def _rename_extracted(outdir: Path, prefix: Path, meta_by_num: Dict[int, Dict[str, object]]) -> Dict[int, str]:
    """把 ``<prefix>-<num>.<ext>`` 重命名为 ``p<页>_<序号>.<ext>``，返回 num→文件名。"""
    result: Dict[int, str] = {}
    for produced in sorted(outdir.glob(prefix.name + "-*")):
        stem = produced.stem  # e.g. p-000
        try:
            num = int(stem.rsplit("-", 1)[1])
        except (ValueError, IndexError):
            continue
        meta = meta_by_num.get(num)
        page = int(meta["page"]) if meta else 0
        new_name = f"p{page}_{num}{produced.suffix.lower()}"
        target = outdir / new_name
        if produced != target:
            if target.exists():
                target.unlink()
            produced.rename(target)
        result[num] = new_name
    return result


def _png_size(path: Path) -> Optional[Tuple[int, int]]:
    """从 PNG 文件头读取 (w, h)；非 PNG 或失败返回 None。"""
    try:
        with path.open("rb") as f:
            head = f.read(24)
    except OSError:
        return None
    if head[:8] == b"\x89PNG\r\n\x1a\n" and len(head) >= 24:
        return (int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big"))
    return None


def _render_pages(pdf: Path, outdir: Path, dpi: int, quiet: bool) -> Dict[str, object]:
    """纯矢量页兜底：用 ``pdftoppm -r <dpi> -png`` 整页渲染，供后续裁剪。"""
    outdir.mkdir(parents=True, exist_ok=True)
    for old in outdir.glob("page-*.png"):
        old.unlink()
    prefix = outdir / "page"
    proc = subprocess.run(
        ["pdftoppm", "-r", str(dpi), "-png", str(pdf), str(prefix)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        return {"status": "error", "error": f"pdftoppm 失败：{proc.stderr.strip()}"}

    images = []
    for f in sorted(outdir.glob("page-*.png")):
        m = re.search(r"page-(\d+)", f.stem)
        page = int(m.group(1)) if m else 0
        size = _png_size(f) or (0, 0)
        images.append({
            "page": page, "num": page, "type": "render", "width": size[0],
            "height": size[1], "color": "rgb", "comp": 3, "bpc": 8, "enc": "png",
            "xppi": dpi, "yppi": dpi, "file": f.name, "sha256": sha256_file(f),
        })
    manifest = {
        "source_pdf": str(pdf.relative_to(ROOT)) if str(pdf).startswith(str(ROOT)) else str(pdf),
        "source_pdf_sha256": sha256_file(pdf),
        "engine": "pdftoppm (纯矢量页整页渲染)",
        "dpi": dpi,
        "extracted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(images),
        "images": images,
    }
    (outdir / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not quiet:
        print(f"[渲染] {outdir}  ←  {manifest['source_pdf']}  共 {len(images)} 页（{dpi} dpi）")
    return {"status": "rendered", "count": len(images), "manifest": str(outdir / MANIFEST_NAME)}


def extract_pdf(pdf: Path, outdir: Path, force: bool = False, quiet: bool = False,
                render: bool = False, dpi: int = 600) -> Dict[str, object]:
    """对单个 PDF 执行无损提取并写出 manifest。返回结果字典。"""
    outdir = Path(outdir)
    manifest_path = outdir / MANIFEST_NAME
    pdf_hash = sha256_file(pdf) if pdf.is_file() else ""

    if manifest_path.is_file() and not force:
        try:
            old = json.loads(manifest_path.read_text(encoding="utf-8"))
            if old.get("source_pdf_sha256") == pdf_hash:
                return {"status": "skipped", "reason": "已存在且源 PDF 未变", "manifest": str(manifest_path)}
        except (OSError, json.JSONDecodeError):
            pass

    if not pdf.is_file():
        return {"status": "error", "error": f"源 PDF 不存在：{pdf}"}

    outdir.mkdir(parents=True, exist_ok=True)
    prefix = outdir / "p"

    list_proc = subprocess.run(
        ["pdfimages", "-list", str(pdf)], capture_output=True, text=True
    )
    if list_proc.returncode != 0:
        return {"status": "error", "error": f"pdfimages -list 失败：{list_proc.stderr.strip()}"}
    metas = parse_pdfimages_list(list_proc.stdout)
    meta_by_num = {int(m["num"]): m for m in metas}

    if not metas:
        if render:
            return _render_pages(pdf, outdir, dpi, quiet)
        return {"status": "empty", "reason": "PDF 无内嵌位图（可加 --render 用 pdftoppm 整页渲染）", "manifest": None}

    # 清理旧的 p*_* / p-* 残件后重新提取
    for old in list(outdir.glob("p-*")) + list(outdir.glob("p*_*.*")):
        if old.is_file():
            old.unlink()

    proc = subprocess.run(
        ["pdfimages", "-all", str(pdf), str(prefix)], capture_output=True, text=True
    )
    if proc.returncode != 0:
        return {"status": "error", "error": f"pdfimages -all 失败：{proc.stderr.strip()}"}

    num_to_file = _rename_extracted(outdir, prefix, meta_by_num)

    images = []
    for m in metas:
        num = int(m["num"])
        fname = num_to_file.get(num)
        if not fname:
            continue
        entry = dict(m)
        entry["file"] = fname
        entry["sha256"] = sha256_file(outdir / fname)
        images.append(entry)

    manifest = {
        "source_pdf": str(pdf.relative_to(ROOT)) if str(pdf).startswith(str(ROOT)) else str(pdf),
        "source_pdf_sha256": pdf_hash,
        "engine": "pdfimages (poppler)",
        "extracted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(images),
        "images": images,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not quiet:
        print(f"[提取] {outdir}  ←  {manifest['source_pdf']}  共 {len(images)} 张")
    return {"status": "extracted", "count": len(images), "manifest": str(manifest_path)}


def process_dir(proc_dir: Path, base_roots: List[Path], force: bool, quiet: bool,
                render: bool = False, dpi: int = 600) -> Dict[str, object]:
    ovis_md = proc_dir / "ovis" / "output.md"
    fm = read_front_matter(ovis_md)
    source_name = fm.get("source") or fm.get("title")
    if not source_name:
        return {"status": "error", "error": f"缺少 ovis/output.md 或其中无 source 字段：{proc_dir}"}
    if not source_name.lower().endswith(".pdf"):
        source_name += ".pdf"
    proc_dir = proc_dir.resolve()
    proc_root = find_processing_root(proc_dir)
    pdf = locate_source_pdf(proc_dir, proc_root or proc_dir, source_name, base_roots)
    if pdf is None:
        return {"status": "error", "error": f"未找到源 PDF「{source_name}」：{proc_dir}"}
    result = extract_pdf(pdf, proc_dir / OUTDIR_NAME, force=force, quiet=quiet,
                         render=render, dpi=dpi)
    result["processing_dir"] = str(proc_dir)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="从源 PDF 无损提取内嵌图片（pdfimages 封装）")
    parser.add_argument("paths", nargs="*", help="处理目录（含 ovis/output.md）")
    parser.add_argument("--root", action="append", default=[], help="递归查找的处理根目录（可重复）")
    parser.add_argument("--pdf", help="单文件模式：源 PDF 路径")
    parser.add_argument("--out", help="单文件模式：输出目录")
    parser.add_argument("--force", action="store_true", help="覆盖已有提取结果")
    parser.add_argument("--render", action="store_true",
                        help="纯矢量页（无内嵌位图）用 pdftoppm 整页渲染兜底")
    parser.add_argument("--render-dpi", type=int, default=600, help="整页渲染 DPI（默认 600）")
    parser.add_argument("--quiet", action="store_true", help="仅输出问题")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    args = parser.parse_args(argv)

    base_roots = [ROOT / r for r in BASE_ROOTS]

    # 单文件模式
    if args.pdf:
        if not args.out:
            print("[错误] 单文件模式需要 --out 指定输出目录", file=sys.stderr)
            return 2
        result = extract_pdf(Path(args.pdf).resolve(), Path(args.out).resolve(),
                             force=args.force, quiet=args.quiet,
                             render=args.render, dpi=args.render_dpi)
        if args.json:
            print(json.dumps(result, ensure_ascii=False))
        return 0 if result["status"] in ("extracted", "skipped", "empty", "rendered") else 1

    roots = [Path(p) for p in args.paths] or [ROOT / r for r in (args.root or DEFAULT_ROOTS)]
    dirs = find_processing_dirs(roots)
    if not dirs:
        print("未找到任何处理目录（含 ovis/output.md）。", file=sys.stderr)
        return 1

    results = []
    problems = 0
    skipped = 0
    for d in dirs:
        r = process_dir(d, base_roots, args.force, args.quiet,
                        render=args.render, dpi=args.render_dpi)
        results.append(r)
        if r["status"] == "error":
            problems += 1
            print(f"[错误] {r.get('error')}", file=sys.stderr)
        elif r["status"] in ("skipped", "empty"):
            skipped += 1

    if args.json:
        print(json.dumps({"results": results}, ensure_ascii=False))
    elif not args.quiet:
        print(f"\n完成：处理目录 {len(dirs)} 个，出错 {problems} 个，跳过/无图 {skipped} 个。")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

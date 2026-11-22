#!/usr/bin/env python3
"""tools/figsize_audit.py —— 图片尺寸处理前的全库/分卷审计。

只读扫描，不改图片、不改 .tex、不写仓库内文件。输出：

* 每卷的源 PDF、材料产物、图片格式、引用数、当前尺寸覆盖情况；
* 全库汇总：缺 PDF、缺材料、SVG/JPG、无 recipe/manifest、缺尺寸键等；
* `--json PATH` 可把完整结果写到临时目录，供后续 figsize_plan 使用。

用法::

    python3 tools/figsize_audit.py
    python3 tools/figsize_audit.py 试卷/2000 试卷/2026/云南
    python3 tools/figsize_audit.py --json /tmp/opencode/figsize-audit.json
    python3 tools/figsize_audit.py --probe-pdf 试卷/1992/湖南云南海南

注意：`--probe-pdf` 会调用 `pdftotext` 判断 PDF 是否有文字层，较慢；默认不开启。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

ROOT = Path(__file__).resolve().parent.parent
IMG_EXTS = {".png", ".jpg", ".jpeg", ".svg", ".pdf"}
FIG_RE = re.compile(r"figs/[A-Za-z0-9_./-]+")
PIC_RE = re.compile(r"\\(one|two|three|four|five|six|seven|eight|nine)picture\b")
CHOICE_RE = re.compile(r"\\(one|two|three|four|five|six|seven|eight|nine)choices\b")
NUMBER_WORD = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9,
}
LETTERS = "ABCDEFGHI"
SIZE_W = {"w", "width"}
SIZE_H = {"h", "height"}
SIZE_S = {"scale", "s"}
OPT_RE = re.compile(r"([A-Za-z][A-Za-z0-9]*)\s*=\s*([^,\]]+)")


def _strip_ext(name: str) -> str:
    p = Path(name)
    if p.suffix.lower() in IMG_EXTS:
        return str(p.with_suffix(""))
    return name


def _fig_key(value: str) -> str:
    value = value.strip().strip("{}")
    if not value.startswith("figs/"):
        return ""
    return _strip_ext(value)


def _scan_balanced(text: str, start: int, opener: str, closer: str) -> Tuple[str, int]:
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return text[start + 1:i], i + 1
    return text[start + 1:], len(text)


def _scan_options(text: str, start: int) -> Tuple[str, int]:
    i = start
    while i < len(text) and text[i].isspace():
        i += 1
    if i >= len(text) or text[i] != "[":
        return "", i
    return _scan_balanced(text, i, "[", "]")


def _parse_options(raw: str) -> Dict[str, str]:
    return {m.group(1): m.group(2).strip() for m in OPT_RE.finditer(raw or "")}


def _command_blocks(text: str, regex: re.Pattern) -> Iterable[Tuple[str, str, List[str]]]:
    for m in regex.finditer(text):
        word = m.group(1)
        opts, pos = _scan_options(text, m.end())
        args: List[str] = []
        i = pos
        while i < len(text):
            while i < len(text) and text[i].isspace():
                i += 1
            if i >= len(text) or text[i] != "{":
                break
            arg, i = _scan_balanced(text, i, "{", "}")
            args.append(arg)
        yield word, _parse_options(opts), args


def _first_size(opts: Dict[str, str], n: int, idx: int) -> Optional[str]:
    keys: List[str] = []
    if n == 1:
        keys += ["wA", "widthA", "w", "width",
                 "hA", "heightA", "h", "height", "scaleA", "sA", "scale", "s"]
    else:
        letter = LETTERS[idx]
        keys += [f"w{letter}", f"width{letter}", f"h{letter}", f"height{letter}",
                 f"scale{letter}", f"s{letter}"]
        keys += ["w", "width", "h", "height", "scale", "s"]
    for k in keys:
        if k in opts:
            return opts[k]
    return None


def _size_keys_present(opts: Dict[str, str], n: int) -> bool:
    if any(k in opts for k in SIZE_W | SIZE_H | SIZE_S):
        return True
    for i in range(n):
        letter = LETTERS[i]
        if any(k in opts for k in (f"w{letter}", f"width{letter}",
                                    f"h{letter}", f"height{letter}",
                                    f"scale{letter}", f"s{letter}")):
            return True
    return False


def _collect_refs(text: str) -> Set[str]:
    return {_fig_key(m.group(0)) for m in FIG_RE.finditer(text) if _fig_key(m.group(0))}


def _has_picture_choice(opts: Dict[str, str]) -> bool:
    return opts.get("ispicture", "").lower() == "true"


def _pdf_path(year: str, region: str, manifest: Path, source: Path) -> Optional[Path]:
    if manifest.is_file():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            raw = data.get("source_pdf")
            if raw:
                p = Path(raw)
                if not p.is_absolute():
                    p = ROOT / p
                if p.is_file():
                    return p
        except (OSError, json.JSONDecodeError):
            pass
    if source.is_file():
        try:
            raw = json.loads(source.read_text(encoding="utf-8")).get("path")
            if raw:
                p = Path(raw)
                if p.is_file():
                    return p
        except (OSError, json.JSONDecodeError):
            pass
    common = ROOT / "OriginPDF" / year / f"{year}_{region}.pdf"
    return common if common.is_file() else None


def _probe_pdf(pdf: Optional[Path]) -> str:
    if not pdf or not pdf.is_file():
        return "missing"
    try:
        proc = subprocess.run(
            ["pdftotext", "-f", "1", "-l", "2", str(pdf), "-"],
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    text = (proc.stdout or "").strip()
    if len(text) >= 40:
        return "text"
    return "scan-like"


def _load_json(path: Path) -> Dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def audit_unit(unit: Path, *, probe_pdf: bool = False) -> Dict:
    tex = unit / f"{unit.name}.tex"
    if not tex.is_file():
        candidates = sorted(unit.glob("*.tex"))
        tex = candidates[0] if candidates else unit / f"{unit.name}.tex"
    year, region = unit.parent.name, unit.name
    proc = ROOT / "材料处理" / year / region
    manifest = proc / "pdfimages" / "manifest.json"
    source_json = proc / "source.json"
    pdf = _pdf_path(year, region, manifest, source_json)
    kind = ""
    if source_json.is_file():
        kind = str(_load_json(source_json).get("kind") or "")
    pdf_kind = kind or ("unknown" if pdf else "missing")
    if probe_pdf and pdf and not kind:
        pdf_kind = _probe_pdf(pdf)

    figs_dir = unit / "figs"
    files = [p for p in (figs_dir.rglob("*") if figs_dir.is_dir() else [])
             if p.is_file() and p.suffix.lower() in IMG_EXTS]
    by_ext = Counter(p.suffix.lower().lstrip(".") for p in files)
    text = tex.read_text(encoding="utf-8", errors="ignore") if tex.is_file() else ""
    refs = _collect_refs(text)
    referenced = 0
    for p in files:
        rel = p.relative_to(unit).as_posix()
        if _strip_ext(rel) in refs or rel in refs:
            referenced += 1

    image_sizes: Dict[str, str] = {}
    missing_images: List[str] = []
    commands = 0
    commands_without_size = 0
    for word, opts, args in _command_blocks(text, PIC_RE):
        n = NUMBER_WORD[word]
        commands += 1
        has_size = _size_keys_present(opts, n)
        if not has_size:
            commands_without_size += 1
        for idx, arg in enumerate(args):
            keys = [_fig_key(m.group(0)) for m in FIG_RE.finditer(arg)]
            for key in keys:
                if not key:
                    continue
                size = _first_size(opts, n, idx)
                if size:
                    image_sizes[key] = size
                elif key not in missing_images:
                    missing_images.append(key)
    for word, opts, args in _command_blocks(text, CHOICE_RE):
        if not _has_picture_choice(opts):
            continue
        n = NUMBER_WORD[word]
        commands += 1
        if not _size_keys_present(opts, n):
            commands_without_size += 1
        for idx, arg in enumerate(args):
            for key in (_fig_key(m.group(0)) for m in FIG_RE.finditer(arg)):
                if not key:
                    continue
                size = _first_size(opts, n, idx)
                if size:
                    image_sizes[key] = size
                elif key not in missing_images:
                    missing_images.append(key)

    recrop = unit / ".recrop.json"
    match_recrop = unit / "match.recrop.json"
    figsizes = unit / "figsizes.json"
    unit_manifest = unit / "figures.manifest.json"
    flags = []
    if not pdf:
        flags.append("no_pdf")
    if not (proc / "merged.md").is_file():
        flags.append("no_merged")
    if not manifest.is_file():
        flags.append("no_pdfimages_manifest")
    if not (recrop.is_file() or match_recrop.is_file()):
        flags.append("no_recrop")
    if not figsizes.is_file():
        flags.append("no_figsizes")
    if not unit_manifest.is_file():
        flags.append("no_figures_manifest")
    if by_ext.get("svg"):
        flags.append("has_svg")
    if by_ext.get("jpg") or by_ext.get("jpeg"):
        flags.append("has_jpg")
    if missing_images:
        flags.append("missing_size")
    if pdf_kind in ("scan", "scan-like"):
        flags.append("scan_like")

    return {
        "unit": unit.as_posix(),
        "year": year,
        "region": region,
        "tex": tex.as_posix() if tex.is_file() else None,
        "pdf": pdf.as_posix() if pdf else None,
        "pdf_kind": pdf_kind,
        "has_merged": (proc / "merged.md").is_file(),
        "has_pdfimages_manifest": manifest.is_file(),
        "has_recrop": recrop.is_file() or match_recrop.is_file(),
        "has_figsizes": figsizes.is_file(),
        "has_figures_manifest": unit_manifest.is_file(),
        "has_ovis": (proc / "ovis").is_dir(),
        "has_paddle": (proc / "paddle").is_dir(),
        "images": len(files),
        "by_ext": dict(sorted(by_ext.items())),
        "referenced": referenced,
        "unreferenced": len(files) - referenced,
        "picture_commands": commands,
        "commands_without_size": commands_without_size,
        "missing_size_images": missing_images,
        "image_sizes": image_sizes,
        "flags": flags,
    }


def iter_units(paths: Sequence[Path]) -> List[Path]:
    out: Set[Path] = set()
    for p in paths:
        if p.is_file() and p.suffix == ".tex":
            if p.parent.name != "TikZ":
                out.add(p.parent)
        elif p.is_dir():
            for tex in sorted(p.rglob("*.tex")):
                if tex.parent.name != "TikZ":
                    out.add(tex.parent)
    return sorted(out)


def summarize(rows: Sequence[Dict]) -> Dict:
    units = len(rows)
    total_images = sum(r["images"] for r in rows)
    flags = Counter(f for r in rows for f in r["flags"])
    by_year: Dict[str, Dict] = {}
    for r in rows:
        y = by_year.setdefault(r["year"], {"units": 0, "images": 0, "flags": Counter()})
        y["units"] += 1
        y["images"] += r["images"]
        y["flags"].update(r["flags"])
    for y in by_year.values():
        y["flags"] = dict(sorted(y["flags"].items()))
    ext_total: Counter = Counter()
    for r in rows:
        ext_total.update(r["by_ext"])
    return {
        "units": units,
        "images": total_images,
        "by_ext": dict(sorted(ext_total.items())),
        "flags": dict(sorted(flags.items())),
        "by_year": dict(sorted(by_year.items())),
    }


def print_table(rows: Sequence[Dict]) -> None:
    header = ("年份", "地区", "图", "SVG", "JPG", "PDF", "merged", "recipe", "manifest", "缺尺寸")
    print(" | ".join(header))
    print(" | ".join("---" for _ in header))
    for r in rows:
        print(" | ".join([
            r["year"], r["region"], str(r["images"]),
            str(r["by_ext"].get("svg", 0)), str(r["by_ext"].get("jpg", 0) + r["by_ext"].get("jpeg", 0)),
            "有" if r["pdf"] else "无",
            "有" if r["has_merged"] else "无",
            "有" if r["has_recrop"] else "无",
            "有" if r["has_figures_manifest"] else "无",
            str(len(r["missing_size_images"])),
        ]))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="图片尺寸处理前审计（只读）")
    parser.add_argument("paths", nargs="*", default=["试卷"], help="试卷目录或 .tex（默认 试卷/）")
    parser.add_argument("--json", help="把完整结果写到指定 JSON（建议 /tmp/opencode/…）")
    parser.add_argument("--probe-pdf", action="store_true", help="用 pdftotext 判断扫描/文字 PDF")
    parser.add_argument("--table", action="store_true", help="输出逐卷表格（默认只输出汇总）")
    args = parser.parse_args(argv)

    paths = [Path(p) for p in args.paths]
    units = iter_units(paths)
    if not units:
        print("未找到试卷目录", file=sys.stderr)
        return 1
    rows = [audit_unit(u, probe_pdf=args.probe_pdf) for u in units]
    summary = summarize(rows)
    print(f"审计单元：{summary['units']} 套，图片：{summary['images']} 张")
    print(f"格式：{summary['by_ext']}")
    print("标记：")
    for k, v in summary["flags"].items():
        print(f"  {k}: {v}")
    print("按年份：")
    for year, data in summary["by_year"].items():
        flags = ", ".join(f"{k}={v}" for k, v in data["flags"].items())
        print(f"  {year}: {data['units']} 套 / {data['images']} 图 / {flags}")
    if args.table:
        print()
        print_table(rows)
    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = {"summary": summary, "units": rows}
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"\n[写入] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

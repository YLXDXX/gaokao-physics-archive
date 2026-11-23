#!/usr/bin/env python3
"""tools/figsize_review.py —— 图片尺寸批量复核清单（只读）。

汇总 `figures.manifest.json` 中需要人工关注的条目，便于按年份/批次复验：

- 缺失 manifest（有配图却未处理）；无配图卷单独标注；
- `final.width_cm/height_cm` 为 `None`；
- `source.deviation > --min-deviation`（默认 5%）；
- 最终尺寸异常（宽 < 0.4cm、高 < 0.2cm 或任一边 > 17cm）；
- 被 17cm 上限缩放（`final.capped`）；
- 未被正文引用的 `figs/` 文件；
- 可选 `--check` 同时运行 `figsize_check`。

用法::

    python3 tools/figsize_review.py 试卷/2000 试卷/2001
    python3 tools/figsize_review.py --only-issues
    python3 tools/figsize_review.py --json /tmp/opencode/figsize-review.json --strict
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
from figsize_audit import (  # noqa: E402
    IMG_EXTS,
    _collect_refs,
    _strip_ext,
    audit_unit,
    iter_units,
)
from figsize_check import check_unit  # noqa: E402

MIN_W_CM = 0.4
MIN_H_CM = 0.2
MAX_CM = 17.0


def _tex_path(unit: Path) -> Optional[Path]:
    tex = unit / f"{unit.name}.tex"
    if tex.is_file():
        return tex
    cands = sorted(unit.glob("*.tex"))
    return cands[0] if cands else None


def unreferenced_files(unit: Path) -> List[str]:
    figs = unit / "figs"
    tex = _tex_path(unit)
    if not figs.is_dir() or tex is None:
        return []
    files = [
        p for p in figs.rglob("*")
        if p.is_file() and p.suffix.lower() in IMG_EXTS
        and not any(part.startswith(".") for part in p.relative_to(figs).parts)
    ]
    refs = _collect_refs(tex.read_text(encoding="utf-8", errors="ignore"))
    out = []
    for p in files:
        rel = p.relative_to(unit).as_posix()
        if not (_strip_ext(rel) in refs or rel in refs):
            out.append(rel)
    return sorted(out)


def review_unit(unit: Path, *, min_deviation: float = 0.05,
                with_unreferenced: bool = True, run_check: bool = False) -> Dict:
    row: Dict = {
        "unit": unit.as_posix(),
        "entries": 0,
        "status": Counter(),
        "issues": [],
        "warnings": [],
        "no_images": False,
        "unreferenced": [],
    }
    manifest = unit / "figures.manifest.json"
    if not manifest.is_file():
        info = audit_unit(unit)
        if info.get("images") == 0 and info.get("referenced") == 0:
            row["no_images"] = True
        else:
            row["issues"].append("缺少 figures.manifest.json（有配图未处理）")
    else:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        entries = data.get("entries", [])
        row["entries"] = len(entries)
        for e in entries:
            row["status"][str(e.get("status", ""))] += 1
            target = e.get("target", "?")
            final = e.get("final") or {}
            w = final.get("width_cm")
            h = final.get("height_cm")
            if not (w and h):
                row["issues"].append(f"None 尺寸：{target}")
                continue
            dev = (e.get("source") or {}).get("deviation") or 0.0
            if dev > min_deviation:
                row["warnings"].append(
                    f"d={dev:.1%} {e.get('status')} {target} → {w:.2f}×{h:.2f}cm")
            if final.get("capped"):
                row["warnings"].append(f"超过 17cm 已缩放：{target} → {w:.2f}×{h:.2f}cm")
            if w < MIN_W_CM or h < MIN_H_CM or w > MAX_CM or h > MAX_CM:
                row["issues"].append(f"尺寸异常：{target} → {w:.2f}×{h:.2f}cm")
        if run_check:
            errs = check_unit(unit)
            row["issues"].extend(f"check：{x}" for x in errs)
    if with_unreferenced:
        row["unreferenced"] = unreferenced_files(unit)
    return row


def _fmt_counter(c: Counter) -> str:
    return " / ".join(f"{c[k]} {k}" for k in ("auto", "review", "manual") if c[k]) or "—"


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="图片尺寸批量复核清单")
    ap.add_argument("paths", nargs="*", default=["试卷"], help="试卷目录或 .tex（默认 试卷/）")
    ap.add_argument("--min-deviation", type=float, default=0.05,
                    help="列出 source.deviation 超过该阈值的条目（默认 0.05）")
    ap.add_argument("--only-issues", action="store_true", help="只输出有 issue/warning 的卷")
    ap.add_argument("--no-unreferenced", action="store_true", help="不检查未引用 figs 文件")
    ap.add_argument("--check", action="store_true", help="同时运行 figsize_check")
    ap.add_argument("--json", help="把完整结果写到 JSON（建议 /tmp/opencode/…）")
    ap.add_argument("--strict", action="store_true", help="存在 issue 时返回非零")
    args = ap.parse_args(argv)

    units = iter_units([Path(p) for p in args.paths])
    rows = [review_unit(u, min_deviation=args.min_deviation,
                        with_unreferenced=not args.no_unreferenced,
                        run_check=args.check) for u in units]

    n_issue = n_warn = 0
    for r in rows:
        has = bool(r["issues"] or r["warnings"] or r["unreferenced"])
        if r["issues"]:
            n_issue += 1
        if r["warnings"] or r["unreferenced"]:
            n_warn += 1
        if args.only_issues and not has and not r["no_images"]:
            continue
        tag = "ISSUE" if r["issues"] else ("WARN" if (r["warnings"] or r["unreferenced"]) else "OK")
        note = "无配图" if r["no_images"] else f"{r['entries']} 条（{_fmt_counter(r['status'])}）"
        print(f"[{tag}] {r['unit']}：{note}")
        for x in r["issues"]:
            print(f"  !! {x}")
        for x in r["warnings"]:
            print(f"  !  {x}")
        for x in r["unreferenced"]:
            print(f"  ?  未引用：{x}")

    print(f"\n汇总：{len(rows)} 套；issue {n_issue} 套，warning/未引用 {n_warn} 套。")
    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "total": len(rows),
            "issue_units": n_issue,
            "warning_units": n_warn,
            "units": [
                {**r, "status": dict(r["status"])}
                for r in rows
            ],
        }
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
        print(f"[写入] {out}")
    return 1 if (args.strict and n_issue) else 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""tools/figsize_status.py —— 列出图片尺寸“已完成/待处理”的卷，避免重复处理。

判定“已完成”的条件：存在 `figures.manifest.json` 且 `figsize_check` 无错误；
无配图卷（`figs/` 为空且正文无图片命令）也视为已完成。
全面铺开时先跑本脚本，`done` 的卷直接跳过；只有 `todo` 的卷需要重新
生成候选/映射/回填。

用法::

    python3 tools/figsize_status.py
    python3 tools/figsize_status.py 试卷/2020 试卷/2021
    python3 tools/figsize_status.py --only-todo
    python3 tools/figsize_status.py --json /tmp/opencode/figsize-status.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
from figsize_audit import _collect_refs, audit_unit, iter_units
from figsize_check import check_unit


def status_unit(unit: Path, *, strict_assets: bool = False) -> Dict:
    manifest = unit / "figures.manifest.json"
    if not manifest.is_file():
        # 无配图卷（figs/ 为空、正文无图片命令）无需 manifest，直接视为完成。
        try:
            info = audit_unit(unit)
        except Exception:
            info = {}
        tex = unit / f"{unit.name}.tex"
        if not tex.is_file():
            cands = sorted(unit.glob("*.tex"))
            tex = cands[0] if cands else None
        refs = _collect_refs(tex.read_text(encoding="utf-8", errors="ignore")) if tex else set()
        if info.get("images") == 0 and info.get("referenced") == 0 and not refs:
            return {"unit": unit.as_posix(), "status": "done", "reason": "无配图"}
        return {"unit": unit.as_posix(), "status": "todo", "reason": "无 figures.manifest.json"}
    errs = check_unit(unit, strict_assets=strict_assets)
    if errs:
        return {"unit": unit.as_posix(), "status": "todo", "reason": "figsize-check 未通过",
                "errors": errs}
    return {"unit": unit.as_posix(), "status": "done", "reason": ""}


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="图片尺寸完成状态（done / todo）")
    ap.add_argument("paths", nargs="*", default=["试卷"], help="试卷目录或 .tex（默认 试卷/）")
    ap.add_argument("--only-todo", action="store_true", help="只打印待处理卷")
    ap.add_argument("--json", help="把完整结果写到 JSON（建议 /tmp/opencode/…）")
    ap.add_argument("--strict", action="store_true", help="存在 todo 时返回非零")
    ap.add_argument("--strict-assets", action="store_true",
                    help="把仍为 SVG 的矢量资产视为 todo")
    args = ap.parse_args(argv)

    units = iter_units([Path(p) for p in args.paths])
    rows = [status_unit(u, strict_assets=args.strict_assets) for u in units]
    done = [r for r in rows if r["status"] == "done"]
    todo = [r for r in rows if r["status"] != "done"]

    if not args.only_todo:
        print(f"已完成：{len(done)} / {len(rows)} 套；待处理：{len(todo)} 套")
    for r in todo:
        errs = r.get("errors") or []
        detail = f"（{len(errs)} 处错误）" if errs else ""
        print(f"[todo] {r['unit']}：{r['reason']}{detail}")
    if args.only_todo and not todo:
        print("全部已完成，无需处理。")

    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = {"total": len(rows), "done": len(done), "todo": len(todo), "units": rows}
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
        print(f"[写入] {out}")
    return 1 if (args.strict and todo) else 0


if __name__ == "__main__":
    raise SystemExit(main())

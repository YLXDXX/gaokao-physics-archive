#!/usr/bin/env python3
"""tools/figsize_fix_refs.py —— 给无扩展名但实际为 PNG 的图片引用补 `.png`。

背景：`\\onepicture{figs/02_an}` 这类省略扩展名的写法本地检查可通过，但外部
`ocrpipe figsize check` 会按 manifest 的 `figs/02_an.png` 找尺寸键，误报
「.tex 中未找到尺寸键」。本脚本只处理同时满足下列条件的引用：

- 引用的 basename 不含扩展名；
- 同目录存在 `<name>.png`；
- 同目录**不**存在 `<name>.svg`（避免把 `\\includesvg{figs/05}` 改成 PNG）。

默认只预览，加 `--write` 落盘。

用法::

    python3 tools/figsize_fix_refs.py 试卷/2025/河南
    python3 tools/figsize_fix_refs.py 试卷/2025/河南 --write
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
REF_RE = re.compile(r"figs/([A-Za-z0-9_./-]+)\}")


def fix_unit(unit: Path, write: bool) -> int:
    tex = unit / f"{unit.name}.tex"
    if not tex.is_file():
        print(f"[跳过] 未找到 {tex}", file=sys.stderr)
        return 0
    text = tex.read_text(encoding="utf-8")
    figs = unit / "figs"
    edits: List[Tuple[int, int, str]] = []
    for m in REF_RE.finditer(text):
        name = m.group(1)
        if "." in os.path.basename(name):
            continue
        if (figs / f"{name}.png").is_file() and not (figs / f"{name}.svg").is_file():
            edits.append((m.start(1), m.end(1), name + ".png"))
    if not edits:
        print(f"{unit.name}: 无需改动")
        return 0
    out = text
    for s, e, new in sorted(edits, key=lambda x: x[0], reverse=True):
        out = out[:s] + new + out[e:]
    if write:
        tex.write_text(out, encoding="utf-8")
        names = ", ".join(sorted({text[s:e] for s, e, _ in edits}))
        print(f"[写入] {tex.relative_to(ROOT)}（{len(edits)} 处：{names}）")
    else:
        for s, e, new in edits:
            line = text.count("\n", 0, s) + 1
            print(f"{tex.name}:{line} figs/{text[s:e]} → figs/{new}")
        print(f"完成：{len(edits)} 处（预览；加 --write 落盘）")
    return len(edits)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="为实际为 PNG 的无扩展名引用补 .png")
    ap.add_argument("units", nargs="+")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)
    total = 0
    for raw in args.units:
        p = Path(raw)
        unit = p.resolve() if p.is_absolute() else (ROOT / p).resolve()
        if not unit.is_dir():
            print(f"[跳过] 非目录：{raw}", file=sys.stderr)
            continue
        total += fix_unit(unit, args.write)
    print(f"完成：{total} 处")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

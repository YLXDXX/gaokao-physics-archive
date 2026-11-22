#!/usr/bin/env python3
"""tools/figsize_check.py —— 校验 figures.manifest.json ↔ .tex 尺寸键。

只检查 manifest 中登记的图，不要求全卷图片都已登记。

用法::

    python3 tools/figsize_check.py 试卷/2000/天津
    python3 tools/figsize_check.py 试卷/2000/天津 试卷/2022/上海
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from figsize_apply import (
    CH_RE, L, N, PIC_RE, balanced, desired, fig_key, load_manifest, options,
    parse_opts,
)

ROOT = Path(__file__).resolve().parent.parent


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except (ValueError, OSError):
        return path.as_posix()


def command_keys(text: str) -> Dict[str, Tuple[str, str]]:
    out: Dict[str, Tuple[str, str]] = {}
    for regex in (PIC_RE, CH_RE):
        for m in regex.finditer(text):
            raw, os_, oe = options(text, m.end())
            if regex is CH_RE and "ispicture=true" not in raw.replace(" ", ""):
                continue
            opts = {k: v for k, v, _ in parse_opts(raw)}
            i = oe + 1
            idx = 0
            while i < len(text):
                while i < len(text) and text[i].isspace():
                    i += 1
                if i >= len(text) or text[i] != "{":
                    break
                arg, end = balanced(text, i, "{", "}")
                fig = None
                for tok in arg.replace("{", " ").replace("}", " ").split():
                    if tok.startswith("figs/"):
                        fig = fig_key(tok)
                        break
                if fig:
                    n = N[m.group(1)]
                    if n == 1:
                        dims = [("w", "w"), ("h", "h"), ("width", "w"), ("height", "h")]
                    else:
                        suf = L[idx]
                        dims = [(f"w{suf}", "w"), (f"h{suf}", "h"),
                                (f"width{suf}", "w"), (f"height{suf}", "h")]
                    for key, dim in dims:
                        if key in opts and opts[key]:
                            out[fig] = (dim, opts[key])
                            break
                idx += 1
                i = end
    return out


def check_unit(unit: Path) -> List[str]:
    errs: List[str] = []
    tex = unit / f"{unit.name}.tex"
    if not tex.is_file():
        return [f"{rel(unit)}: 缺少 {unit.name}.tex"]
    manifest = load_manifest(unit)
    if not manifest:
        return [f"{rel(unit)}: 缺少 figures.manifest.json"]
    text = tex.read_text(encoding="utf-8")
    got = command_keys(text)
    for key, e in manifest.items():
        target = ROOT / e["target"]
        if not target.is_file():
            errs.append(f"{rel(unit)}: 目标不存在 {e['target']}")
            continue
        dim, val = desired(e)
        if key not in got:
            errs.append(f"{rel(unit)}: {key} 在 .tex 中未找到尺寸键")
            continue
        got_dim, got_val = got[key]
        if got_dim != dim:
            errs.append(f"{rel(unit)}: {key} 尺寸键 {got_dim}={got_val}，"
                        f"manifest 期望 {dim}={val}")
            continue
        def num(x: str) -> float:
            try:
                return float(x.replace("cm", "").strip())
            except ValueError:
                return -1.0
        if abs(num(got_val) - num(val)) > 0.02:
            errs.append(f"{rel(unit)}: {key} 尺寸 {got_val} ≠ manifest {val}")
    return errs


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="校验图片尺寸 manifest 与 .tex")
    ap.add_argument("units", nargs="+")
    args = ap.parse_args(argv)
    errs: List[str] = []
    for raw in args.units:
        unit = Path(raw).resolve()
        errs.extend(check_unit(unit))
    for e in errs:
        print(f"[错误] {e}", file=sys.stderr)
    if errs:
        print(f"结果：{len(errs)} 处错误 ❌", file=sys.stderr)
        return 1
    print(f"结果：{len(args.units)} 套通过 ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

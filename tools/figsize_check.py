#!/usr/bin/env python3
"""tools/figsize_check.py —— 校验 figures.manifest.json ↔ .tex 尺寸键与资产尺寸。

只检查 manifest 中登记的图，不要求全卷图片都已登记；PNG 校验 pHYs，PDF/SVG 校验纵横比。

用法::

    python3 tools/figsize_check.py 试卷/2000/天津
    python3 tools/figsize_check.py 试卷/2000/天津 试卷/2022/上海
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from PIL import Image

try:
    import pymupdf  # type: ignore
except ImportError:  # pragma: no cover
    import fitz as pymupdf  # type: ignore

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
            # 无选项时 oe 指向第一个 "{"（oe==os），不能 +1。
            i = oe + 1 if raw else oe
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
                                (f"width{suf}", "w"), (f"height{suf}", "h"),
                                ("w", "w"), ("h", "h"), ("width", "w"), ("height", "h")]
                    for key, dim in dims:
                        if key in opts and opts[key]:
                            out[fig] = (dim, opts[key])
                            break
                idx += 1
                i = end
    return out


def png_size_cm(path: Path) -> Optional[Tuple[float, float]]:
    """读取 PNG 的 pHYs 并换算为 cm；无/非法 pHYs 返回 None。"""
    try:
        with Image.open(path) as im:
            px_w, px_h = im.size
            dpi = im.info.get("dpi")
    except OSError:
        return None
    if not dpi:
        return None
    if isinstance(dpi, (tuple, list)):
        dx, dy = float(dpi[0]), float(dpi[1])
    else:
        dx = dy = float(dpi)
    if dx <= 0 or dy <= 0:
        return None
    return px_w / dx * 2.54, px_h / dy * 2.54


def svg_aspect(path: Path) -> Optional[float]:
    try:
        head = path.read_text(encoding="utf-8", errors="ignore")[:4000]
    except OSError:
        return None
    m = re.search(r"<svg\b[^>]*>", head, re.S)
    if not m:
        return None
    tag = m.group(0)
    mw = re.search(r'\bwidth\s*=\s*"([^"]+)"', tag)
    mh = re.search(r'\bheight\s*=\s*"([^"]+)"', tag)

    def num(raw: str) -> Optional[float]:
        mm = re.match(r"\s*([0-9.]+)", raw)
        return float(mm.group(1)) if mm else None

    if mw and mh:
        w, h = num(mw.group(1)), num(mh.group(1))
        if w and h:
            return w / h
    mv = re.search(r'\bviewBox\s*=\s*"([^"]+)"', tag)
    if mv:
        parts = re.split(r"[\s,]+", mv.group(1).strip())
        if len(parts) == 4:
            try:
                w, h = float(parts[2]), float(parts[3])
                return w / h if w and h else None
            except ValueError:
                return None
    return None


def pdf_aspect(path: Path) -> Optional[float]:
    try:
        doc = pymupdf.open(str(path))
        try:
            r = doc[0].rect
            return r.width / r.height if r.height else None
        finally:
            doc.close()
    except Exception:
        return None


def check_unit(unit: Path, *, strict_assets: bool = False) -> List[str]:
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

    # 资产侧校验：PNG 必须带与 manifest 一致的 pHYs；PDF 校验 MediaBox 纵横比
    # （页尺寸 PDF 可能保留整页 bbox，由 .tex 缩放，故只比较纵横比）。
    for key, e in manifest.items():
        target = ROOT / e["target"]
        if not target.is_file():
            continue
        want_w = float(e["width_cm"])
        want_h = float(e["height_cm"])
        suf = target.suffix.lower()
        if suf == ".png":
            got_size = png_size_cm(target)
            if got_size is None:
                errs.append(f"{rel(unit)}: {key} PNG 缺少 pHYs（请先 figsize-apply --write）")
            else:
                gw, gh = got_size
                if (abs(gw - want_w) > max(0.05, want_w * 0.01)
                        or abs(gh - want_h) > max(0.05, want_h * 0.01)):
                    errs.append(f"{rel(unit)}: {key} pHYs {gw:.2f}×{gh:.2f}cm "
                                f"≠ manifest {want_w:.2f}×{want_h:.2f}cm")
        elif suf == ".pdf":
            a = pdf_aspect(target)
            want_a = want_w / want_h
            if a and abs(a / want_a - 1) > 0.02:
                errs.append(f"{rel(unit)}: {key} PDF MediaBox 纵横比 {a:.3f} "
                            f"≠ manifest {want_a:.3f}")
        elif suf == ".svg":
            if strict_assets:
                errs.append(f"{rel(unit)}: {key} 仍为 SVG，未迁移为 PDF"
                            f"（--strict-assets）")
                continue
            a = svg_aspect(target)
            want_a = want_w / want_h
            if a and abs(a / want_a - 1) > 0.02:
                errs.append(f"{rel(unit)}: {key} SVG 纵横比 {a:.3f} "
                            f"≠ manifest {want_a:.3f}")
    return errs


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="校验图片尺寸 manifest 与 .tex")
    ap.add_argument("units", nargs="+")
    ap.add_argument("--strict-assets", action="store_true",
                    help="要求全部矢量资产为 PDF；SVG 一律报错")
    args = ap.parse_args(argv)
    errs: List[str] = []
    for raw in args.units:
        unit = Path(raw).resolve()
        errs.extend(check_unit(unit, strict_assets=args.strict_assets))
    for e in errs:
        print(f"[错误] {e}", file=sys.stderr)
    if errs:
        print(f"结果：{len(errs)} 处错误 ❌", file=sys.stderr)
        return 1
    print(f"结果：{len(args.units)} 套通过 ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

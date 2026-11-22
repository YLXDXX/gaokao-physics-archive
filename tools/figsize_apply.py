#!/usr/bin/env python3
"""tools/figsize_apply.py —— 只按 figures.manifest.json 回填图片尺寸。

与 `ocrpipe figsize apply` 的区别：本脚本**只处理 manifest 中登记的图**，
不会把其它图片按 PNG pHYs/PDF MediaBox 的自然尺寸一并改写。

用法::

    python3 tools/figsize_apply.py 试卷/2000/天津
    python3 tools/figsize_apply.py 试卷/2000/天津 --write
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
FIG_RE = re.compile(r"figs/[A-Za-z0-9_./-]+")
PIC_RE = re.compile(r"\\(one|two|three|four|five|six|seven|eight|nine)picture\b")
CH_RE = re.compile(r"\\(one|two|three|four|five|six|seven|eight|nine)choices\b")
N = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
     "six": 6, "seven": 7, "eight": 8, "nine": 9}
L = "ABCDEFGHI"
SIZE_KEYS = {"w", "width", "h", "height", "wA", "widthA", "hA", "heightA"}
for _c in L:
    SIZE_KEYS |= {f"w{_c}", f"width{_c}", f"h{_c}", f"height{_c}"}


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except (ValueError, OSError):
        return path.as_posix()


def balanced(text: str, start: int, op: str, cl: str) -> Tuple[str, int]:
    depth = 0
    for i in range(start, len(text)):
        if text[i] == op:
            depth += 1
        elif text[i] == cl:
            depth -= 1
            if depth == 0:
                return text[start + 1:i], i + 1
    return text[start + 1:], len(text)


def options(text: str, start: int) -> Tuple[str, int, int]:
    i = start
    while i < len(text) and text[i].isspace():
        i += 1
    if i >= len(text) or text[i] != "[":
        return "", i, i
    raw, end = balanced(text, i, "[", "]")
    return raw, i + 1, end - 1


def parse_opts(raw: str) -> List[Tuple[str, str, str]]:
    out = []
    for part in (raw or "").split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            out.append((k.strip(), v.strip(), part))
        elif part.strip():
            out.append((part.strip(), "", part))
    return out


def fig_key(raw: str) -> str:
    p = Path(raw.strip().strip("{}"))
    if not raw.startswith("figs/"):
        return ""
    return str(p.with_suffix("")) if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".svg", ".pdf") else str(p)


def load_manifest(unit: Path) -> Dict[str, Dict]:
    p = unit / "figures.manifest.json"
    if not p.is_file():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    out = {}
    for e in data.get("entries", []):
        target = e.get("target", "")
        if not target:
            continue
        # target 形如 试卷/<年>/<地区>/figs/xx.ext → figs/xx
        parts = Path(target).parts
        if "figs" in parts:
            i = parts.index("figs")
            key = str(Path("figs").joinpath(*parts[i + 1:]))
            key = fig_key(key)
        if key and e.get("width_cm") and e.get("height_cm"):
            out[key] = e
    return out


def desired(e: Dict) -> Tuple[str, str]:
    ref = ((e.get("final") or {}).get("reference") or "width")
    if ref == "height":
        return "h", f"{float(e['height_cm']):.2f}cm"
    return "w", f"{float(e['width_cm']):.2f}cm"


def update_command(text: str, start: int, end: int, raw_opts: str,
                   args: List[Tuple[str, int, int]], n: int,
                   manifest: Dict[str, Dict]) -> Optional[str]:
    parts = parse_opts(raw_opts)
    keys = {k for k, _, _ in parts}
    targets: List[Tuple[int, Dict]] = []
    for idx, (arg, _, _) in enumerate(args):
        m = FIG_RE.search(arg)
        if not m:
            continue
        key = fig_key(m.group(0))
        if key in manifest:
            targets.append((idx, manifest[key]))
    if not targets:
        return None
    all_mapped = len(targets) == len(args)
    if all_mapped:
        parts = [(k, v, p) for k, v, p in parts
                 if k not in {"w", "width", "h", "height"}]
    for idx, e in targets:
        dim, val = desired(e)
        if n == 1:
            keys_to_remove = {"w", "width", "h", "height"}
            key = dim
        else:
            suf = L[idx]
            keys_to_remove = {f"w{suf}", f"width{suf}", f"h{suf}", f"height{suf}"}
            key = dim + suf
        parts = [(k, v, p) for k, v, p in parts if k not in keys_to_remove]
        parts.append((key, val, f"{key}={val}"))
    return ", ".join(p.strip() for _, _, p in parts)


def write_png_phys(unit: Path, manifest: Dict[str, Dict], write: bool) -> int:
    n = 0
    for e in manifest.values():
        target = ROOT / e["target"]
        if target.suffix.lower() != ".png" or not target.is_file():
            continue
        w_cm, h_cm = e.get("width_cm"), e.get("height_cm")
        if not w_cm or not h_cm:
            continue
        with Image.open(target) as im:
            px_w, px_h = im.size
            dpi = (px_w / (float(w_cm) / 2.54), px_h / (float(h_cm) / 2.54))
            if write:
                im.save(target, dpi=dpi)
                n += 1
    if n:
        print(f"[pHYs] {rel(unit)}：{n} 张 PNG 已写入物理尺寸")
    return n


def process_unit(unit: Path, write: bool) -> int:
    tex = unit / f"{unit.name}.tex"
    if not tex.is_file():
        print(f"[跳过] 未找到 {rel(tex)}", file=sys.stderr)
        return 0
    manifest = load_manifest(unit)
    if not manifest:
        print(f"[跳过] {rel(unit)} 无 figures.manifest.json", file=sys.stderr)
        return 0
    text = tex.read_text(encoding="utf-8")
    edits: List[Tuple[int, int, str]] = []
    for regex in (PIC_RE, CH_RE):
        for m in regex.finditer(text):
            word = m.group(1)
            n = N[word]
            raw_opts, os, oe = options(text, m.end())
            if regex is CH_RE and "ispicture=true" not in raw_opts.replace(" ", ""):
                continue
            args: List[Tuple[str, int, int]] = []
            # 无选项时 options() 返回 oe==os 指向第一个 "{"，不能再 +1，否则会跳过参数。
            i = oe + 1 if raw_opts else oe
            while i < len(text):
                while i < len(text) and text[i].isspace():
                    i += 1
                if i >= len(text) or text[i] != "{":
                    break
                arg, end = balanced(text, i, "{", "}")
                args.append((arg, i, end))
                i = end
            new = update_command(text, os, oe, raw_opts, args, n, manifest)
            if new is not None and new != raw_opts:
                # 原命令无选项时 update_command 返回的只是选项内容，需要补上方括号。
                edits.append((os, oe, new if raw_opts else f"[{new}]"))
    if not edits:
        if write:
            write_png_phys(unit, manifest, write)
        print(f"{unit.name}: 无改动")
        return 0
    # apply reverse order; options spans are inside command args and may overlap? no.
    out = text
    for s, e, new in sorted(edits, key=lambda x: x[0], reverse=True):
        out = out[:s] + new + out[e:]
    if write:
        tex.write_text(out, encoding="utf-8")
        print(f"[写入] {rel(tex)}（{len(edits)} 处）")
        write_png_phys(unit, manifest, write)
    else:
        for s, e, new in edits:
            line = text.count("\n", 0, s) + 1
            print(f"{tex.name}:{line} [{text[s:e]}] → [{new}]")
        print(f"完成：{len(edits)} 处（预览；加 --write 落盘）")
    return len(edits)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="按 figures.manifest.json 回填尺寸")
    ap.add_argument("units", nargs="+")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)
    total = 0
    for raw in args.units:
        p = Path(raw)
        unit = p.resolve() if p.is_file() else p.resolve()
        if not unit.is_dir():
            print(f"[跳过] 非目录：{raw}", file=sys.stderr)
            continue
        total += process_unit(unit, args.write)
    print(f"完成：{total} 处")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

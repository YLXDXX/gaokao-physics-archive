#!/usr/bin/env python3
"""tools/figsize_merge_fallback.py —— 为未匹配的复合图回退生成 merge 映射。

`figsize_automap.py` 只接受单候选 + 相似度/纵横比阈值；PDF 版面检测常把一张
复合图（如「图(a)+图(b)」、A–D 四选项整行）拆成多个子图候选，于是正常图会被
判为 `-- keep current`。若该图在 `.tex` 中又没有现成尺寸键，
`figsize_plan --keep-current` 只能给出 `None×None`。

本脚本只处理 manifest 中 `status=missing_source` 且**正文确实引用**的图：

1. 在 free candidates（未被已有 map 使用）中，枚举同一页的 1–4 个候选组合；
2. 用组合的 union bbox 从源 PDF 裁出图像，与资产图做灰度相似度；
3. 选 ``sim - min(d,1)`` 最大的组合，写回 `figures.map.json`（单候选写
   ``candidate``，多候选写 ``merge``，并带 ``reference``）。

之后仍需运行 ``figsize_plan --write --keep-current``、``figsize_apply``、
``figsize_check``。低相似度（``sim<0.35``）的组合建议人工复核；必要时在 map 中
改 ``final_width_cm/final_height_cm``。

用法::

    python3 tools/figsize_merge_fallback.py 试卷/2023/湖南 --report
    python3 tools/figsize_merge_fallback.py 试卷/2023/湖南 --write

依赖：Pillow、numpy、PyMuPDF；SVG 渲染同 `figsize_automap.py`。
"""
from __future__ import annotations

import argparse
import io
import itertools
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image

try:  # pragma: no cover
    import pymupdf  # type: ignore
except ImportError:  # pragma: no cover
    import fitz as pymupdf  # type: ignore

try:
    from tools.figsize_automap import (
        ROOT, TMP_ROOT, candidate_manifest, feature, load_candidates,
    )
    from tools.figsize_plan import merge_candidates
except ImportError:  # 直接运行 tools/figsize_merge_fallback.py
    from figsize_automap import (
        ROOT, TMP_ROOT, candidate_manifest, feature, load_candidates,
    )
    from figsize_plan import merge_candidates


def tex_refs(tex: Path) -> set:
    """返回 TeX 中所有 figs/ 引用的键（去扩展名）。"""
    text = tex.read_text(encoding="utf-8", errors="ignore")
    out = set()
    for m in re.finditer(r"figs/([A-Za-z0-9_./-]+?)(?:\.[A-Za-z0-9]+)?\}", text):
        out.add(os.path.splitext(m.group(1))[0])
    return out


def union_rect(rects: List[List[float]]) -> List[float]:
    return [min(r[0] for r in rects), min(r[1] for r in rects),
            max(r[2] for r in rects), max(r[3] for r in rects)]


def feature_image(im: Image.Image, size: int = 40) -> np.ndarray:
    arr = np.asarray(im.convert("L"))
    mask = arr < 240
    if mask.any():
        ys, xs = np.where(mask)
        arr = arr[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    small = Image.fromarray(arr).resize((size, size), Image.BILINEAR)
    vec = np.asarray(small, dtype=np.float32).ravel()
    vec -= vec.mean()
    norm = np.linalg.norm(vec)
    return vec / norm if norm else vec


def render_page(pdf: Path, page: int, dpi: int = 110) -> Image.Image:
    doc = pymupdf.open(str(pdf))
    try:
        pix = doc[page - 1].get_pixmap(dpi=dpi)
        return Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
    finally:
        doc.close()


def choose_combo(unit: Path, name: str, cand_manifest: Dict,
                 cands: List[Dict], used: set, page_cache: Dict[int, Image.Image],
                 tmp: Path, max_combo: int = 4) -> Optional[Dict]:
    cmap = {f["candidate"]: f for f in cand_manifest["figures"]}
    asset = unit / "figs" / name
    avec, ar = feature(asset, tmp)
    by_page: Dict[int, List[Dict]] = {}
    for c in cands:
        if c["candidate"] not in used:
            by_page.setdefault(c["page"], []).append(c)
    best = None
    for page, group in by_page.items():
        if page not in page_cache:
            page_cache[page] = render_page(Path(cand_manifest["source_pdf"]), page)
        page_img = page_cache[page]
        W, H = page_img.size
        for k in range(1, min(max_combo, len(group)) + 1):
            for combo in itertools.combinations(group, k):
                idxs = [c["candidate"] for c in combo]
                try:
                    merged = combo[0] if k == 1 else merge_candidates(
                        cand_manifest["figures"], idxs)
                except Exception:
                    continue
                cw, ch = float(merged["width_cm"]), float(merged["height_cm"])
                d = abs(ar / (cw / ch) - 1.0) if ch else 9.0
                rects = [cmap[i]["rect_norm"] for i in idxs]
                r = union_rect(rects)
                cim = page_img.crop((int(r[0] * W), int(r[1] * H),
                                     int(r[2] * W), int(r[3] * H)))
                sim = float(np.dot(avec, feature_image(cim)))
                score = sim - min(d, 1.0)
                cand = {"score": score, "sim": sim, "d": d, "idxs": idxs,
                        "page": page, "merged": merged}
                if best is None or cand["score"] > best["score"]:
                    best = cand
    return best


def process_unit(unit: Path, write: bool, report: bool, max_combo: int) -> int:
    tex = unit / f"{unit.name}.tex"
    map_path = unit / "figures.map.json"
    manifest_path = unit / "figures.manifest.json"
    if not (tex.is_file() and map_path.is_file() and manifest_path.is_file()):
        print(f"[跳过] {unit}：缺 tex/map/manifest", file=sys.stderr)
        return 0
    refs = tex_refs(tex)
    mapping = json.loads(map_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    missing = [Path(e["target"]).name for e in manifest.get("entries", [])
               if e.get("status") == "missing_source"]
    if not missing:
        print(f"{unit.name}: 无 missing_source")
        return 0
    cm_path = candidate_manifest(unit)
    if not cm_path.is_file():
        print(f"[跳过] {unit}：无候选 manifest", file=sys.stderr)
        return 0
    cand_manifest = json.loads(cm_path.read_text(encoding="utf-8"))
    cands = load_candidates(cm_path)
    used = {e["candidate"] for e in mapping.get("entries", []) if "candidate" in e}
    entries = {Path(e["target"]).name: e for e in mapping.get("entries", [])}
    tmp = Path(tempfile.mkdtemp(prefix="figsize-merge-", dir=TMP_ROOT))
    page_cache: Dict[int, Image.Image] = {}
    changed = 0
    try:
        for name in missing:
            key = os.path.splitext(name)[0]
            if key not in refs:
                print(f"  -- {name}: 未被正文引用，保留为 missing_source（建议排除 manifest）")
                continue
            best = choose_combo(unit, name, cand_manifest, cands, used,
                                page_cache, tmp, max_combo)
            if not best:
                print(f"  !! {name}: 无可枚举候选")
                continue
            idxs = best["idxs"]
            ent = entries.get(name, {"target": f"试卷/{unit.parent.name}/{unit.name}/figs/{name}"})
            ent.pop("candidate", None)
            ent.pop("merge", None)
            if len(idxs) == 1:
                ent["candidate"] = idxs[0]
            else:
                ent["merge"] = idxs
            # 竖长资产用高度为基准
            ent["reference"] = "height" if (best["merged"]["height_cm"] >
                                            best["merged"]["width_cm"]) else "width"
            ent["notes"] = (f"fallback merge: sim={best['sim']:.2f}, "
                            f"d={best['d']:.2f}")
            entries[name] = ent
            used.update(idxs)
            changed += 1
            if report:
                print(f"  {name:14} {'+'.join(map(str, idxs)):12} p{best['page']} "
                      f"{best['merged']['width_cm']:.2f}x{best['merged']['height_cm']:.2f} "
                      f"sim={best['sim']:.3f} d={best['d']*100:5.1f}%")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if write and changed:
        mapping["entries"] = list(entries.values())
        map_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
        print(f"[写入] {map_path.relative_to(ROOT)}（{changed} 条）")
    return changed


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="为 missing_source 复合图回退生成 merge 映射")
    ap.add_argument("units", nargs="+")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--report", action="store_true", help="打印每个回退组合")
    ap.add_argument("--max-combo", type=int, default=4, help="最多合并的候选数（默认 4）")
    args = ap.parse_args(argv)
    total = 0
    for raw in args.units:
        p = Path(raw)
        unit = p.resolve() if p.is_absolute() else (ROOT / p).resolve()
        if not unit.is_dir():
            print(f"[跳过] 非目录：{raw}", file=sys.stderr)
            continue
        total += process_unit(unit, args.write, args.report, args.max_combo)
    print(f"完成：{total} 条回退")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

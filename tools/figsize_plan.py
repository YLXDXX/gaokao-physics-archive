#!/usr/bin/env python3
"""tools/figsize_plan.py —— 由人工映射 + PDF 候选尺寸生成 figures.manifest.json。

流程：
1. 人工在 `试卷/<年>/<地区>/figures.map.json` 指定每个目标图对应的候选（1 基）；
2. 读取 `材料处理/<年>/<地区>/pdf_figures/figures.manifest.json` 的候选尺寸；
3. 按图片实际纵横比与 5%/15% 规则计算最终 cm 尺寸；
4. 输出 `试卷/<年>/<地区>/figures.manifest.json`（本地、不入库）。

map 示例::

    {
      "entries": [
        {"target": "试卷/2000/天津/figs/05.png", "candidate": 1},
        {"target": "试卷/2022/上海/figs/02a.png", "candidate": 1}
      ]
    }

候选 manifest 可用外部工具生成::

    ocrpipe figsize layout 材料处理/<年>/<地区> --json
    ocrpipe figsize draft 材料处理/<年>/<地区> --pdf OriginPDF/<年>/<年>_<地区>.pdf
    ocrpipe figsize extract 材料处理/<年>/<地区>/figures.draft.json

用法::

    python3 tools/figsize_plan.py 试卷/2000/天津
    python3 tools/figsize_plan.py 试卷/2000/天津 --write
    python3 tools/figsize_plan.py 试卷/2022/上海 --map /tmp/opencode/map.json --write
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from PIL import Image

try:
    import pymupdf  # type: ignore
except ImportError:  # pragma: no cover
    import fitz as pymupdf  # type: ignore

ROOT = Path(__file__).resolve().parent.parent
MAX_WIDTH_CM = 17.0
ASPECT_AUTO = 0.05
ASPECT_MANUAL = 0.15


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except (ValueError, OSError):
        return path.as_posix()


def infer_unit(path: Path) -> Path:
    p = path.resolve()
    if p.is_file():
        return p.parent
    return p


def load_json(path: Path) -> Dict:
    return json.loads(path.read_text(encoding="utf-8"))


def asset_aspect(path: Path) -> Optional[float]:
    suf = path.suffix.lower()
    if suf in (".png", ".jpg", ".jpeg"):
        with Image.open(path) as im:
            w, h = im.size
            return w / h if h else None
    if suf == ".pdf":
        doc = pymupdf.open(str(path))
        try:
            r = doc[0].rect
            return r.width / r.height if r.height else None
        finally:
            doc.close()
    if suf == ".svg":
        head = path.read_text(encoding="utf-8", errors="ignore")[:4000]
        m = re.search(r"<svg\b[^>]*>", head, re.S)
        if not m:
            return None
        tag = m.group(0)
        mw = re.search(r'\bwidth\s*=\s*"([^"]+)"', tag)
        mh = re.search(r'\bheight\s*=\s*"([^"]+)"', tag)
        if not mw or not mh:
            return None
        def num(raw: str) -> Optional[float]:
            mm = re.match(r"\s*([0-9.]+)", raw)
            return float(mm.group(1)) if mm else None
        w, h = num(mw.group(1)), num(mh.group(1))
        return w / h if w and h else None
    return None


def candidate_sizes(candidate: Dict) -> Tuple[float, float]:
    w = candidate.get("width_cm")
    h = candidate.get("height_cm")
    if w and h:
        return float(w), float(h)
    if candidate.get("true_width_cm") and candidate.get("true_height_cm"):
        return float(candidate["true_width_cm"]), float(candidate["true_height_cm"])
    raise ValueError("候选缺少 width_cm/height_cm")


def load_map(unit: Path, map_path: Optional[Path]) -> Dict[str, Dict]:
    path = map_path or (unit / "figures.map.json")
    if not path.is_file():
        raise FileNotFoundError(f"未找到映射文件：{rel(path)}")
    data = load_json(path)
    out: Dict[str, Dict] = {}
    for e in data.get("entries", []):
        target = str(e.get("target", "")).strip()
        if not target:
            continue
        p = Path(target)
        if not p.is_absolute():
            p = ROOT / p
        out[rel(p)] = e
    return out


def find_candidate_manifest(unit: Path) -> Path:
    year, region = unit.parent.name, unit.name
    return ROOT / "材料处理" / year / region / "pdf_figures" / "figures.manifest.json"


def build_entry(unit: Path, target: Path, spec: Dict, cand: Dict,
                cand_manifest: Dict) -> Dict:
    if not target.is_file():
        return {"target": rel(target), "status": "missing_source",
                "notes": "目标图片不存在"}
    aspect = asset_aspect(target)
    cw, ch = candidate_sizes(cand)
    source_aspect = cw / ch if ch else None
    d = abs(aspect / source_aspect - 1.0) if aspect and source_aspect else None
    strategy = spec.get("strategy") or "measure"

    final_w = final_h = None
    basis = "pdf_bbox"
    reference = str(spec.get("reference") or "width")
    status = "auto"
    notes = str(spec.get("notes") or "")

    if spec.get("final_width_cm") and spec.get("final_height_cm"):
        final_w = float(spec["final_width_cm"])
        final_h = float(spec["final_height_cm"])
        basis = "manual"
        status = "manual"
    elif d is None:
        status = "manual"
        notes = (notes + "；无法读取纵横比").strip("；")
    elif d <= ASPECT_AUTO:
        if reference == "height":
            final_h = ch
            final_w = final_h * aspect
        else:
            final_w = cw
            final_h = final_w / aspect
        status = "auto"
    elif d <= ASPECT_MANUAL:
        if reference == "height":
            final_h = ch
            final_w = final_h * aspect
        else:
            final_w = cw
            final_h = final_w / aspect
        status = "review"
        notes = (notes + f"；纵横比偏差 {d:.1%}，已保留资产比例").strip("；")
    elif spec.get("reference") in ("width", "height"):
        if reference == "height":
            final_h = ch
            final_w = final_h * aspect
        else:
            final_w = cw
            final_h = final_w / aspect
        status = "manual"
        basis = "manual"
        notes = (notes + f"；纵横比偏差 {d:.1%}，按 {reference} 人工裁定").strip("；")
    else:
        status = "manual"
        notes = (notes + f"；纵横比偏差 {d:.1%}，需人工确认").strip("；")

    capped = False
    if final_w and final_w > MAX_WIDTH_CM:
        scale = MAX_WIDTH_CM / final_w
        final_w *= scale
        final_h *= scale
        capped = True
        notes = (notes + "；超过 17cm 已缩放").strip("；")

    return {
        "target": rel(target),
        "strategy": strategy,
        "asset": {"kind": target.suffix.lower().lstrip("."), "aspect": aspect},
        "source": {
            "pdf": cand_manifest.get("source_pdf"),
            "page": cand.get("page"),
            "bbox_norm": cand.get("rect_norm"),
            "kind": cand.get("kind"),
            "width_cm": cw,
            "height_cm": ch,
            "aspect": source_aspect,
            "deviation": d,
            "measure": "layout+draft",
        },
        "final": {
            "width_cm": round(final_w, 2) if final_w else None,
            "height_cm": round(final_h, 2) if final_h else None,
            "basis": basis,
            "reference": reference,
            "capped": capped,
        },
        "width_cm": round(final_w, 2) if final_w else None,
        "height_cm": round(final_h, 2) if final_h else None,
        "status": status,
        "notes": notes,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="生成图片尺寸 figures.manifest.json")
    ap.add_argument("units", nargs="+")
    ap.add_argument("--map", help="映射 JSON（默认 <unit>/figures.map.json）")
    ap.add_argument("--candidates", help="候选 manifest（默认材料处理/.../pdf_figures/figures.manifest.json）")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)

    total = 0
    for raw in args.units:
        unit = infer_unit(Path(raw))
        try:
            mapping = load_map(unit, Path(args.map) if args.map else None)
        except Exception as e:
            print(f"[跳过] {unit}: {e}", file=sys.stderr)
            continue
        cand_path = Path(args.candidates) if args.candidates else find_candidate_manifest(unit)
        if not cand_path.is_file():
            print(f"[跳过] {unit}: 未找到候选 manifest {rel(cand_path)}", file=sys.stderr)
            continue
        cand_manifest = load_json(cand_path)
        cands = cand_manifest.get("figures", [])
        entries: List[Dict] = []
        for key, spec in mapping.items():
            target = ROOT / key
            try:
                idx = int(spec["candidate"])
            except (KeyError, ValueError, TypeError):
                print(f"[警告] {key}: 缺少 candidate 索引", file=sys.stderr)
                continue
            if not (1 <= idx <= len(cands)):
                print(f"[警告] {key}: candidate {idx} 越界（共 {len(cands)}）", file=sys.stderr)
                continue
            entries.append(build_entry(unit, target, spec, cands[idx - 1], cand_manifest))
        payload = {
            "version": 1,
            "unit": rel(unit),
            "policy": {
                "scale_mode": "auto",
                "max_width_cm": MAX_WIDTH_CM,
                "precision": 2,
                "aspect_tolerance": ASPECT_AUTO,
                "manual_aspect_tolerance": ASPECT_MANUAL,
            },
            "entries": entries,
        }
        auto = sum(1 for e in entries if e.get("status") == "auto")
        review = sum(1 for e in entries if e.get("status") == "review")
        manual = sum(1 for e in entries if e.get("status") == "manual")
        print(f"=== {unit.as_posix()}：{len(entries)} 条（auto {auto} / review {review} / manual {manual}）")
        for e in entries:
            f = e.get("final") or {}
            print(f"  {e.get('status','?'):7} {e['target'].split('/')[-1]:16} "
                  f"cand#{mapping[e['target']].get('candidate')} → "
                  f"{f.get('width_cm')}×{f.get('height_cm')}cm")
        if args.write:
            out = unit / "figures.manifest.json"
            out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
            print(f"[写入] {rel(out)}")
        total += len(entries)
    print(f"完成：{total} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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
        {"target": "试卷/2020/北京/figs/16d.png", "merge": [23, 24, 25, 26]}
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
        m = re.search(r"<(?:[\w.-]+:)?svg\b[^>]*>", head, re.S)
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
        # 无 width/height 时退回 viewBox="minx miny w h"。
        mv = re.search(r'\bviewBox\s*=\s*"([^"]+)"', tag)
        if mv:
            parts = re.split(r"[\s,]+", mv.group(1).strip())
            if len(parts) == 4:
                try:
                    w, h = float(parts[2]), float(parts[3])
                    return w / h if w and h else None
                except ValueError:
                    return None
        # 无 width/height/viewBox 时退回 clipPath 的 rect（部分导出 SVG 仅有裁剪框）。
        mclip = re.search(r"<(?:[\w.-]+:)?clipPath\b.*?</(?:[\w.-]+:)?clipPath>", head, re.S)
        if mclip:
            mrect = re.search(r"<(?:[\w.-]+:)?rect\b[^>]*>", mclip.group(0))
            if mrect:
                rw = re.search(r'\bwidth\s*=\s*"([0-9.]+)"', mrect.group(0))
                rh = re.search(r'\bheight\s*=\s*"([0-9.]+)"', mrect.group(0))
                if rw and rh and float(rh.group(1)):
                    return float(rw.group(1)) / float(rh.group(1))
        return None
    return None


def merge_candidates(candidates: List[Dict], indices: List[int]) -> Dict:
    """把同一页的多个候选按 union bbox 合并成一个“候选”。"""
    picked = [candidates[i - 1] for i in indices]
    pages = {f.get("page") for f in picked}
    if len(pages) != 1:
        raise ValueError(f"合并候选跨页：pages={sorted(pages)}")
    base = picked[0]
    r = base.get("rect_norm")
    if not r:
        raise ValueError("合并候选缺少 rect_norm")
    x0, y0, x1, y1 = map(float, r)
    bw, bh = candidate_sizes(base)
    if x1 <= x0 or y1 <= y0:
        raise ValueError("合并候选 rect_norm 非法")
    sx, sy = bw / (x1 - x0), bh / (y1 - y0)
    xs: List[float] = []
    ys: List[float] = []
    for f in picked:
        fr = f.get("rect_norm")
        if not fr:
            raise ValueError("合并候选中存在缺少 rect_norm 的项")
        xs += [float(fr[0]), float(fr[2])]
        ys += [float(fr[1]), float(fr[3])]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    return {
        "page": base.get("page"),
        "rect_norm": [minx, miny, maxx, maxy],
        "kind": "merged",
        "source": "merged",
        "caption": "+".join(str(f.get("caption") or "") for f in picked),
        "width_cm": round((maxx - minx) * sx, 3),
        "height_cm": round((maxy - miny) * sy, 3),
    }


def candidate_sizes(candidate: Dict) -> Tuple[float, float]:
    w = candidate.get("width_cm")
    h = candidate.get("height_cm")
    if w and h:
        return float(w), float(h)
    if candidate.get("true_width_cm") and candidate.get("true_height_cm"):
        return float(candidate["true_width_cm"]), float(candidate["true_height_cm"])
    raise ValueError("候选缺少 width_cm/height_cm")


def current_sizes(unit: Path) -> Dict[str, Tuple[str, str]]:
    try:
        from figsize_check import command_keys
    except ImportError:
        from tools.figsize_check import command_keys
    tex = unit / f"{unit.name}.tex"
    if not tex.is_file():
        return {}
    return command_keys(tex.read_text(encoding="utf-8", errors="ignore"))


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


def make_current_entry(unit: Path, target: Path, dim: str, val: str) -> Dict:
    aspect = asset_aspect(target)
    value = float(val.replace("cm", "").strip())
    if dim == "w":
        w, h = value, (value / aspect if aspect else None)
    else:
        h, w = value, (value * aspect if aspect else None)
    return {
        "target": rel(target),
        "strategy": "manual",
        "asset": {"kind": target.suffix.lower().lstrip("."), "aspect": aspect},
        "source": {"kind": "current", "measure": "kept", "width_cm": w,
                   "height_cm": h, "reference": "width" if dim == "w" else "height"},
        "final": {"width_cm": round(w, 2) if w else None,
                  "height_cm": round(h, 2) if h else None,
                  "basis": "manual",
                  "reference": "width" if dim == "w" else "height",
                  "capped": False},
        "width_cm": round(w, 2) if w else None,
        "height_cm": round(h, 2) if h else None,
        "status": "manual",
        "notes": "保留当前尺寸（未匹配 PDF 候选）",
    }


def tex_refs(tex: Path) -> set:
    """TeX 中所有 figs/ 引用的键（去扩展名），用于跳过未引用图。"""
    if not tex.is_file():
        return set()
    text = tex.read_text(encoding="utf-8", errors="ignore")
    out = set()
    for m in re.finditer(r"figs/([A-Za-z0-9_./-]+)\}", text):
        name = m.group(1)
        out.add("figs/" + (str(Path(name).with_suffix("")) if Path(name).suffix else name))
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="生成图片尺寸 figures.manifest.json")
    ap.add_argument("units", nargs="+")
    ap.add_argument("--map", help="映射 JSON（默认 <unit>/figures.map.json）")
    ap.add_argument("--candidates", help="候选 manifest（默认材料处理/.../pdf_figures/figures.manifest.json）")
    ap.add_argument("--keep-current", action="store_true",
                    help="未在 map 中登记的图沿用当前 .tex 尺寸并写入 manifest")
    ap.add_argument("--skip-unreferenced", action="store_true",
                    help="配合 --keep-current：跳过未被 .tex 引用的 figs 文件")
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
            cand: Optional[Dict] = None
            if spec.get("merge"):
                try:
                    indices = [int(x) for x in spec["merge"]]
                except (TypeError, ValueError):
                    print(f"[警告] {key}: merge 必须是候选序号数组", file=sys.stderr)
                    continue
                if not indices or any(not (1 <= i <= len(cands)) for i in indices):
                    print(f"[警告] {key}: merge 候选越界（共 {len(cands)}）", file=sys.stderr)
                    continue
                try:
                    cand = merge_candidates(cands, indices)
                except ValueError as exc:
                    print(f"[警告] {key}: {exc}", file=sys.stderr)
                    continue
            elif (spec.get("final_width_cm") and spec.get("final_height_cm")):
                # 没有候选（如 PDF 未识别出的复合图）但已人工给定最终尺寸。
                cand = {"page": 0, "kind": "manual",
                        "width_cm": float(spec["final_width_cm"]),
                        "height_cm": float(spec["final_height_cm"]),
                        "rect_norm": []}
            else:
                try:
                    idx = int(spec["candidate"])
                except (KeyError, ValueError, TypeError):
                    print(f"[警告] {key}: 缺少 candidate 索引", file=sys.stderr)
                    continue
                if not (1 <= idx <= len(cands)):
                    print(f"[警告] {key}: candidate {idx} 越界（共 {len(cands)}）", file=sys.stderr)
                    continue
                cand = cands[idx - 1]
            entries.append(build_entry(unit, target, spec, cand, cand_manifest))
        if args.keep_current:
            mapped = {ROOT / k for k in mapping}
            cur = current_sizes(unit)
            refs = tex_refs(unit / f"{unit.name}.tex") if args.skip_unreferenced else None
            for p in sorted((unit / "figs").rglob("*")):
                if not p.is_file() or p.suffix.lower() not in (".png", ".jpg", ".jpeg", ".svg", ".pdf"):
                    continue
                if any(part.startswith(".") for part in p.relative_to(unit / "figs").parts):
                    continue
                if p in mapped:
                    continue
                key = "figs/" + p.relative_to(unit / "figs").as_posix()
                key = key.rsplit(".", 1)[0] if Path(key).suffix.lower() in (".png", ".jpg", ".jpeg", ".svg", ".pdf") else key
                if refs is not None and key not in refs:
                    continue
                if key in cur:
                    dim, val = cur[key]
                    entries.append(make_current_entry(unit, p, dim, val))
                else:
                    entries.append({
                        "target": rel(p), "strategy": "manual",
                        "asset": {"kind": p.suffix.lower().lstrip("."), "aspect": asset_aspect(p)},
                        "source": {"kind": "missing", "measure": "none"},
                        "final": {"width_cm": None, "height_cm": None,
                                  "basis": "manual", "reference": "width", "capped": False},
                        "width_cm": None, "height_cm": None,
                        "status": "missing_source", "notes": "未找到候选，也未找到当前尺寸",
                    })
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
        missing_final = [
            e for e in entries
            if not ((e.get("final") or {}).get("width_cm")
                    and (e.get("final") or {}).get("height_cm"))
        ]
        print(f"=== {unit.as_posix()}：{len(entries)} 条（auto {auto} / review {review} / manual {manual}）")
        for e in entries:
            f = e.get("final") or {}
            print(f"  {e.get('status','?'):7} {e['target'].split('/')[-1]:16} "
                  f"→ {f.get('width_cm')}×{f.get('height_cm')}cm")
        if missing_final:
            names = "、".join(e["target"].split("/")[-1] for e in missing_final)
            print(f"[警告] {len(missing_final)} 条缺少最终尺寸（{names}）；"
                  f"请在 map 中补 reference 或 final_width_cm/final_height_cm。",
                  file=sys.stderr)
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

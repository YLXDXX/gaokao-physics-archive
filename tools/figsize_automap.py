#!/usr/bin/env python3
"""tools/figsize_automap.py —— 自动生成 figures.map.json（一对一候选匹配）。

在 `ocrpipe figsize layout/draft/extract` 生成候选之后，用
「去白边灰度图相似度 + 资产/候选纵横比」组成代价矩阵，做**一对一**指派
（匈牙利算法），为每张 figs 资产选择最可能的 PDF 候选。

只接受同时满足下列条件的配对：

- 图像相似度 ``sim >= --min-sim``（默认 0.20）；
- 完整资产纵横比与候选纵横比偏差 ``d <= --max-dev``（默认 0.15）。

不满足的资产不写入 map，交由 ``figsize_plan --keep-current`` 沿用当前尺寸。
映射结果仍**必须人工抽查**：建议对 ``sim < 0.35`` 的条目查看原图/候选对照。

用法::

    python3 tools/figsize_automap.py 试卷/2026/北京 --write
    python3 tools/figsize_automap.py 试卷/2025/上海 --report
    python3 tools/figsize_automap.py 试卷/2024/湖北 --min-sim 0.25 --max-dev 0.12 --write

依赖：Pillow、numpy、PyMuPDF；SVG 渲染优先 ``rsvg-convert``，退回 ``inkscape``。
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image

try:  # pragma: no cover - 环境相关
    import pymupdf  # type: ignore
except ImportError:  # pragma: no cover
    import fitz as pymupdf  # type: ignore

ROOT = Path(__file__).resolve().parent.parent
IMG_EXTS = {".png", ".jpg", ".jpeg", ".svg", ".pdf"}
TMP_ROOT = Path(os.environ.get("FIGSize_TMP") or os.environ.get("TMPDIR") or tempfile.gettempdir())


# --------------------------------------------------------------------------- #
# 匈牙利算法（最小代价，n <= m）
# --------------------------------------------------------------------------- #
def hungarian_min(a: List[List[float]]) -> Dict[int, int]:
    """返回行→列的最优指派；a 为 n×m 代价矩阵（n<=m）。"""
    n, m = len(a), len(a[0]) if a else 0
    if n == 0 or m == 0:
        return {}
    if n > m:
        raise ValueError("hungarian_min 要求 n <= m")
    inf = float("inf")
    u = [0.0] * (n + 1)
    v = [0.0] * (m + 1)
    p = [0] * (m + 1)
    way = [0] * (m + 1)
    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = [inf] * (m + 1)
        used = [False] * (m + 1)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = inf
            j1 = 0
            for j in range(1, m + 1):
                if used[j]:
                    continue
                cur = a[i0 - 1][j - 1] - u[i0] - v[j]
                if cur < minv[j]:
                    minv[j] = cur
                    way[j] = j0
                if minv[j] < delta:
                    delta = minv[j]
                    j1 = j
            for j in range(0, m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    return {p[j] - 1: j - 1 for j in range(1, m + 1) if p[j] != 0}


# --------------------------------------------------------------------------- #
# 图像读取与特征
# --------------------------------------------------------------------------- #
def _render_svg(path: Path, tmpdir: Path) -> Image.Image:
    out = tmpdir / (path.stem + "-" + str(abs(hash(str(path)))) + ".png")
    rsvg = shutil.which("rsvg-convert")
    if rsvg:
        subprocess.run([rsvg, "-o", str(out), str(path)], check=False,
                       capture_output=True)
    else:
        inkscape = shutil.which("inkscape")
        if not inkscape:
            raise RuntimeError("需要 rsvg-convert 或 inkscape 渲染 SVG")
        subprocess.run([inkscape, str(path), "--export-type=png",
                        f"--export-filename={out}"], check=False,
                       capture_output=True)
    if not out.is_file():
        raise RuntimeError(f"SVG 渲染失败：{path}")
    return Image.open(out)


def load_image(path: Path, tmpdir: Path) -> Image.Image:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        doc = pymupdf.open(str(path))
        try:
            pix = doc[0].get_pixmap(dpi=110)
            im = Image.open(io.BytesIO(pix.tobytes("png")))
        finally:
            doc.close()
    elif suffix == ".svg":
        im = _render_svg(path, tmpdir)
    else:
        im = Image.open(path)
    im = im.convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    bg.alpha_composite(im)
    return bg.convert("L")


def feature(path: Path, tmpdir: Path, size: int = 40) -> Tuple[np.ndarray, float]:
    """返回 (归一化灰度特征, 完整图像纵横比)。特征先去白边再缩放。"""
    im = load_image(path, tmpdir)
    full_aspect = im.width / im.height if im.height else None
    arr = np.asarray(im)
    mask = arr < 240
    if mask.any():
        ys, xs = np.where(mask)
        arr = arr[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    small = Image.fromarray(arr).resize((size, size), Image.BILINEAR)
    vec = np.asarray(small, dtype=np.float32).ravel()
    vec -= vec.mean()
    norm = np.linalg.norm(vec)
    return (vec / norm if norm else vec), full_aspect


# --------------------------------------------------------------------------- #
# 候选与指派
# --------------------------------------------------------------------------- #
def candidate_manifest(unit: Path) -> Path:
    year, region = unit.parent.name, unit.name
    return ROOT / "材料处理" / year / region / "pdf_figures" / "figures.manifest.json"


def load_candidates(manifest: Path) -> List[Dict]:
    data = json.loads(manifest.read_text(encoding="utf-8"))
    out = []
    for idx, f in enumerate(data.get("figures", []), 1):
        path = f.get("png") or f.get("pdf")
        if not path:
            continue
        out.append({
            "candidate": int(f.get("candidate", idx)),
            "page": f.get("page"),
            "path": ROOT / path if not Path(path).is_absolute() else Path(path),
            "width_cm": float(f["width_cm"]),
            "height_cm": float(f["height_cm"]),
            "aspect": float(f["width_cm"]) / float(f["height_cm"]),
        })
    return out


def list_assets(unit: Path) -> List[Tuple[str, Path]]:
    figs = unit / "figs"
    out = []
    for p in sorted(figs.iterdir()):
        if p.is_file() and p.suffix.lower() in IMG_EXTS and not p.name.startswith("."):
            out.append((p.name, p))
    return out


def build_pairs(cands: List[Dict], assets: List[Tuple[str, Path]],
                tmpdir: Path) -> Tuple[List[Dict], Dict[int, np.ndarray]]:
    cfeat = {c["candidate"]: feature(c["path"], tmpdir)[0] for c in cands}
    pairs = []
    for ai, (_, path) in enumerate(assets):
        vec, full_aspect = feature(path, tmpdir)
        for c in cands:
            sim = float(np.dot(vec, cfeat[c["candidate"]]))
            dev = abs(full_aspect / c["aspect"] - 1.0) if (full_aspect and c["aspect"]) else 9.0
            pairs.append({"ai": ai, "c": c, "sim": sim, "dev": dev,
                          "ar": full_aspect,
                          "cost": sim - 1.5 * min(dev, 1.0)})
    return pairs, cfeat


def assign_pairs(pairs: List[Dict], n_assets: int, n_cands: int,
                 min_sim: float, max_dev: float) -> Dict[int, Dict]:
    """一对一指派；不满足阈值的资产不分配。"""
    neg = -1e6
    weight = [[neg] * (n_cands + n_assets) for _ in range(n_assets)]
    by_key = {}
    for q in pairs:
        key = (q["ai"], q["c"]["candidate"])
        by_key[key] = q
        if q["sim"] >= min_sim and q["dev"] <= max_dev and q["cost"] > 0:
            weight[q["ai"]][q["c"]["candidate"] - 1] = q["cost"]
    # 虚拟列（未匹配）代价 0；真实候选里负权重不会胜出
    for ai in range(n_assets):
        for ci in range(n_cands):
            if weight[ai][ci] == neg:
                weight[ai][ci] = neg
        for dj in range(n_cands, n_cands + n_assets):
            weight[ai][dj] = 0.0
    cost = [[-w for w in row] for row in weight]
    res = hungarian_min(cost)
    out = {}
    for ai, col in res.items():
        if col is None or col >= n_cands:
            continue
        q = by_key.get((ai, col + 1))
        if q and q["sim"] >= min_sim and q["dev"] <= max_dev and q["cost"] > 0:
            out[ai] = q
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="自动生成 figures.map.json（一对一）")
    ap.add_argument("units", nargs="+")
    ap.add_argument("--write", action="store_true", help="写入 figures.map.json")
    ap.add_argument("--out", help="只处理一个单元时指定输出路径")
    ap.add_argument("--report", action="store_true", help="打印每张资产的匹配结果")
    ap.add_argument("--min-sim", type=float, default=0.20)
    ap.add_argument("--max-dev", type=float, default=0.15)
    args = ap.parse_args(argv)
    if args.out and len(args.units) != 1:
        ap.error("--out 只能与单个单元一起使用")

    rc = 0
    tmp_root = Path(tempfile.mkdtemp(prefix="figsize-automap-", dir=TMP_ROOT))
    try:
        for raw in args.units:
            unit = (ROOT / raw).resolve() if not Path(raw).is_absolute() else Path(raw)
            if not unit.is_dir():
                print(f"[跳过] 非目录：{raw}", file=sys.stderr)
                rc = 1
                continue
            manifest = candidate_manifest(unit)
            if not manifest.is_file():
                print(f"[跳过] 未找到候选 manifest：{manifest}", file=sys.stderr)
                rc = 1
                continue
            cands = load_candidates(manifest)
            assets = list_assets(unit)
            if not cands or not assets:
                print(f"[跳过] {unit}：候选或资产为空", file=sys.stderr)
                rc = 1
                continue
            pairs, _ = build_pairs(cands, assets, tmp_root)
            mapping = assign_pairs(pairs, len(assets), len(cands),
                                   args.min_sim, args.max_dev)
            entries = []
            rows = []
            for ai, (name, _) in enumerate(assets):
                q = mapping.get(ai)
                if not q:
                    rows.append((name, None, None, 0.0, 0.0, 0.0))
                    continue
                c = q["c"]
                ref = "height" if (q.get("ar") or 1) < 1 else "width"
                entries.append({
                    "target": f"试卷/{unit.parent.name}/{unit.name}/figs/{name}",
                    "candidate": c["candidate"],
                    "reference": ref,
                })
                rows.append((name, c["candidate"], c["page"], q["sim"], q["dev"], q["cost"]))
            out = Path(args.out) if args.out else unit / "figures.map.json"
            print(f"== {unit.relative_to(ROOT).as_posix()}: {len(entries)}/{len(assets)} mapped "
                  f"(min_sim={args.min_sim}, max_dev={args.max_dev})")
            if args.report:
                for name, cand, page, sim, dev, cost in rows:
                    if cand is None:
                        print(f"  -- {name:14} (kept current)")
                    else:
                        print(f"  OK {name:14} cand{cand:>2} p{page:<2} "
                              f"sim={sim:.3f} d={dev * 100:5.1f}% cost={cost:.3f}")
            if args.write:
                out.write_text(json.dumps({"entries": entries}, ensure_ascii=False,
                                          indent=2) + "\n", encoding="utf-8")
                print(f"[写入] {out}")
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())

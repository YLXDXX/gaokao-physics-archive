#!/usr/bin/env python3
"""tools/match_figures.py

把试卷目录中 `.tex` 引用的 `figs/*` 旧图，**逐一匹配**到原 PDF 内嵌图
（`<处理目录>/pdfimages/p*.jpg`），给出候选的**源内嵌图**与（若为多子图）
**裁剪矩形**，作为 `tools/recrop_figures.py apply` 与单图无损复制的**草表**。

定位：这是“多子图裁剪与回填”流程（`材料处理与OCR规范.md` 第五节）的**分诊/匹配辅助**，
生产“候选 + 置信度”，**不替代人工逐张核对**：低置信、冲突、旧图为拼合图者仍须人工裁定。

匹配思路（两阶段）：
    1. 把旧图与 `<处理目录>/ovis/images/page_N_bbox_*.jpg`（OCR 裁切图）比对，取最相似者
       得到**页码**（OCR 图文件名含页码）；
    2. 仅在**同一处理目录（同一源 PDF）且该页**的内嵌图中，用“整图 +
       `splitpicture --panels` 子框”比对，取最相似者。
       同一课有多个源 PDF（多课时 / 多资源）时，各 PDF 的页码相互独立、按**源 PDF 分域**，
       故不会因“页码相同”而串图。
若阶段 2 最佳分过低（< 0.60，通常是“旧图为多图拼合、无单张内嵌源”），再做一次
不限定页码的**整图**兜底匹配。

旧图来源（按优先级，均可选）：
    a. `figs/.ocr_before/<名>.<ext>`（裁剪回填前的备份，最准）；
    b. `git show HEAD:<相对路径>`（替换前提交的版本）；
    c. 当前 `figs/<名>.<ext>`（已替换时仅作兜底）。

用法::

    # 单个处理目录（含 pdfimages/ 与 ovis/images/）
    python3 tools/match_figures.py 试卷/<年>/<地区> 材料处理/<年>/<地区>

    # 多课时（多个处理目录）
    python3 tools/match_figures.py 试卷/<年>/<地区> 材料处理/<年>/<地区>/第1课时,材料处理/<年>/<地区>/第2课时

    # 输出 JSON 草表
    python3 tools/match_figures.py 试卷/<年>/<地区> <处理目录> --out /tmp/match.json

输出列：`旧图  A=OCR相似度 p=页  B=内嵌图相似度 源内嵌图 整图/panel 矩形`

依赖：numpy、Pillow；`splitpicture` 在 PATH 中或设环境变量 `SPLITPICTURE`。
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import subprocess
import tempfile
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageFilter

# 复用 recrop_figures 的 splitpicture 调用与内置分幅
sys.path.insert(0, str(Path(__file__).resolve().parent))
from recrop_figures import split_subfigures, splitpicture_panels  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SPLITPICTURE = os.environ.get("SPLITPICTURE", "splitpicture")
FIG_RE = re.compile(r"figs/([A-Za-z0-9_]+)\.(jpg|jpeg|png)", re.I)
FALLBACK_WHOLE = 0.60      # 低于此分触发“跨源整图兜底”
_PANEL_CACHE: Dict[str, list] = {}


def _panels(f: str, im: Image.Image, splitpicture: str, tight: bool = False) -> list:
    """按文件缓存 splitpicture --panels 结果（同源图被多个 fig 复用，避免重复调用）。"""
    if f not in _PANEL_CACHE:
        try:
            _PANEL_CACHE[f] = splitpicture_panels(Path(f), splitpicture, tight=tight) or \
                split_subfigures(im.convert("L"))
        except Exception:
            _PANEL_CACHE[f] = []
    return _PANEL_CACHE[f]


def _prefetch_panels(files: List[str], splitpicture: str, tight: bool = False) -> None:
    """用一次批量 ``detect --panels --save-rects --per-file-subdir`` 预填充
    ``_PANEL_CACHE``，避免逐图启动子进程；失败则静默退回逐图调用（``_panels``）。"""
    todo = [f for f in files if f not in _PANEL_CACHE]
    if not todo:
        return
    # --per-file-subdir 以文件名（stem）为子目录名：同名者会互相覆盖，故仅批量处理
    # 同批内 stem 唯一的文件，重名者留给逐图 _panels()（跨处理目录常见 pN_M.jpg 重名）。
    by_stem: Dict[str, List[str]] = {}
    for f in todo:
        by_stem.setdefault(Path(f).stem, []).append(f)
    todo = [fs[0] for fs in by_stem.values() if len(fs) == 1]
    if not todo:
        return
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    with tempfile.TemporaryDirectory(prefix="match_panels_") as td:
        cmd = [splitpicture, "detect"]
        for f in todo:
            cmd += ["-i", f]
        cmd += ["--panels", "--save-rects", "--per-file-subdir", "-d", td, "--json"]
        if tight:
            cmd.append("--tight")
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
        except OSError:
            return
        if proc.returncode != 0:
            return
        for f in todo:
            try:
                arr = json.loads(
                    (Path(td) / Path(f).stem / "rects.json").read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            panels = [(int(r["x"]), int(r["y"]), int(r["w"]), int(r["h"])) for r in arr]
            if panels:  # 空结果不缓存，保留 _panels() 的内置分幅兜底
                _PANEL_CACHE[f] = panels


# ---------------------------------------------------------------------------
# 图像归一化与相似度（对比例/边距/细线差异较鲁棒）
# ---------------------------------------------------------------------------
def _content_box(im: Image.Image, thr: int = 200):
    g = np.asarray(im.convert("L"), dtype=np.int16)
    ys, xs = np.where(g < thr)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def _norm(im: Image.Image, size: int = 128, thr: int = 200, blur: float = 2.2) -> np.ndarray:
    b = _content_box(im, thr)
    if b is None:
        return np.full((size, size), 255, np.float32)
    c = im.convert("L").crop(b)
    w, h = c.size
    s = size / max(w, h)
    c = c.resize((max(1, int(w * s)), max(1, int(h * s))), Image.LANCZOS)
    canvas = Image.new("L", (size, size), 255)
    canvas.paste(c, ((size - c.width) // 2, (size - c.height) // 2))
    if blur:
        canvas = canvas.filter(ImageFilter.GaussianBlur(blur))
    return np.asarray(canvas, np.float32)


def _score(a: np.ndarray, b: np.ndarray) -> float:
    x, y = 255.0 - a, 255.0 - b
    x, y = x - x.mean(), y - y.mean()
    d = np.sqrt((x * x).sum()) * np.sqrt((y * y).sum())
    return float((x * y).sum() / d) if d > 0 else 0.0


# ---------------------------------------------------------------------------
# 载入 OCR 图（带页码）与内嵌图（带页码）
# ---------------------------------------------------------------------------
def _load_ocr(procdir: Path, idx: int) -> List[Tuple[np.ndarray, str, Optional[int], Image.Image, int]]:
    """OCR 裁切图 + 页码；idx 标记其所属处理目录（用于按源 PDF 分域）。"""
    out = []
    for f in glob.glob(str(procdir / "ovis" / "images" / "*.jpg")):
        m = re.search(r"page_(\d+)_bbox_", os.path.basename(f))
        page = int(m.group(1)) if m else None
        try:
            im = Image.open(f)
            out.append((_norm(im), f, page, im, idx))
        except Exception:
            pass
    return out


def _load_emb(pairs: List[Tuple[Path, Path]], min_side: int
              ) -> List[Tuple[str, Optional[int], Image.Image, int]]:
    """内嵌图 + 页码 + 所属处理目录序号（同一 PDF 的页码才可比）。"""
    out = []
    for idx, (_proc, pd) in enumerate(pairs):
        for f in sorted(glob.glob(str(pd / "p*_*.jpg"))):
            m = re.match(r"p(\d+)_\d+\.jpg", os.path.basename(f))
            page = int(m.group(1)) if m else None
            try:
                im = Image.open(f)
                if min(im.size) < min_side:
                    continue
                if im.size[0] >= 4000 and im.size[1] < 260:  # 页眉/装饰长条
                    continue
                out.append((f, page, im, idx))
            except Exception:
                pass
    return out


# ---------------------------------------------------------------------------
# 旧图定位
# ---------------------------------------------------------------------------
def _old_image(section: Path, name: str) -> Optional[Image.Image]:
    for f in glob.glob(str(section / "figs" / f"{name}.*")):
        if not f.lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        base = Path(f).name
        backup = section / "figs" / ".ocr_before" / base
        if backup.is_file():
            return Image.open(backup)
        rel = os.path.relpath(f, ROOT)
        proc = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=ROOT,
                              capture_output=True)
        if proc.returncode == 0 and proc.stdout:
            tmp = Path(tempfile.gettempdir()) / "opencode_match_old" / base
            tmp.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_bytes(proc.stdout)
            return Image.open(tmp)
        return Image.open(f)
    return None


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def referenced_figs(section: Path) -> List[str]:
    names = set()
    for t in glob.glob(str(section / "*.tex")):
        if "教案" in t:
            continue
        s = Path(t).read_text(encoding="utf-8", errors="ignore")
        names |= {m.group(1) for m in FIG_RE.finditer(s)}
    return sorted(names)


def match(section: Path, pairs: List[Tuple[Path, Path]],
          min_side: int, splitpicture: str, tight: bool = False) -> Dict[str, dict]:
    """pairs：[(处理目录, 其 pdfimages)] 列表；每个 PDF 的页码独立，按源 PDF 分域。"""
    ocr = []
    for idx, (proc, _pd) in enumerate(pairs):
        ocr += _load_ocr(proc, idx)
    emb = _load_emb(pairs, min_side)
    _prefetch_panels([f for f, _p, _im, _i in emb], splitpicture, tight=tight)
    emb_norm = [(f, p, _norm(im), idx, im) for f, p, im, idx in emb]

    results: Dict[str, dict] = {}
    for name in referenced_figs(section):
        oi = _old_image(section, name)
        if oi is None:
            print(f"{name:18s} 未找到旧图（figs/{name}.*）")
            results[name] = {"error": "no-old"}
            continue
        on = _norm(oi)
        # 阶段 1：OCR → （所属源 PDF 域, 页码）
        cand_ocr = sorted(((_score(on, n), page, idx, f) for n, f, page, _im, idx in ocr),
                          key=lambda t: t[0], reverse=True)
        top = cand_ocr[0] if cand_ocr else (0.0, None, None, None)
        page, srcidx = top[1], top[2]
        # 阶段 2：**同一源 PDF 域**且同页的内嵌图（整图 + 子框）
        best = (0.0, None, None, None)
        for f, p, norm, idx, im in emb_norm:
            if page is not None and (p != page or idx != srcidx):
                continue
            s = _score(on, norm)
            if s > best[0]:
                best = (s, f, None, "whole")
            for j, (x, y, w, h) in enumerate(_panels(f, im, splitpicture, tight=tight)):
                if w < 60 or h < 60:
                    continue
                s = _score(on, _norm(im.crop((x, y, x + w, y + h))))
                if s > best[0]:
                    best = (s, f, (x, y, w, h), f"panel{j}")
        # 兜底：旧图为拼合图时，跨所有源的整图匹配
        if best[0] < FALLBACK_WHOLE:
            for f, p, norm, idx, im in emb_norm:
                s = _score(on, norm)
                if s > best[0]:
                    best = (s, f, None, "whole*")
        results[name] = {
            "ocr_score": round(top[0], 3),
            "ocr": os.path.basename(top[3]) if top[3] else None,
            "page": page,
            "score": round(best[0], 3),
            "source": os.path.basename(best[1]) if best[1] else None,
            "source_rel": os.path.relpath(best[1], ROOT) if best[1] else None,
            "rect": list(best[2]) if best[2] else None,
            "kind": best[3],
        }
        v = results[name]
        print(f"{name:18s} A={v['ocr_score']:.2f} p={v['page']}  "
              f"B={v['score']:.2f} {v['source'] or '-':12s} {v['kind'] or '':8s} rect={v['rect']}")
    return results


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="旧 figs 图 → 原 PDF 内嵌图/裁剪框 匹配草表")
    ap.add_argument("section", help="试卷目录（含 .tex 与 figs/）")
    ap.add_argument("procdirs", help="处理目录（含 pdfimages/ 与 ovis/images/），多个用逗号分隔")
    ap.add_argument("--out", help="结果 JSON 输出路径")
    ap.add_argument("--min-side", type=int, default=110, help="内嵌图最小边阈值（默认 110px）")
    ap.add_argument("--splitpicture", default=DEFAULT_SPLITPICTURE)
    ap.add_argument("--tight", action="store_true",
                    help="透传 splitpicture --tight（≥0.4）：收敛相互侵入的候选框；"
                         "仅分诊/预览用，会收缩框、可能切内容，勿作最终实裁框")
    args = ap.parse_args(argv)

    section = (ROOT / args.section).resolve() if not Path(args.section).is_absolute() \
        else Path(args.section)
    if not section.is_dir():
        sys.exit(f"目录不存在：{section}")
    procdirs = [(ROOT / p).resolve() if not Path(p).is_absolute() else Path(p)
                for p in args.procdirs.split(",")]
    pairs = [(p, p / "pdfimages") for p in procdirs if (p / "pdfimages").is_dir()]
    if not pairs:
        sys.exit("未找到 pdfimages/，请先运行 make extract-images")
    res = match(section, pairs, args.min_side, args.splitpicture, tight=args.tight)
    if args.out:
        Path(args.out).write_text(json.dumps(res, ensure_ascii=False, indent=1),
                                  encoding="utf-8")
        print(f"\n结果已写入：{args.out}")
    print("\n提示：B≥0.98 通常可信；B<0.98、多个 fig 指向同一源、或旧图为拼合图者，"
          "请按 材料处理与OCR规范.md 第五节人工核对后再写 recipe/复制。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""tools/recrop_figures.py

把「从 PDF 无损提取出的内嵌图」按子图裁剪，**回填**到试卷的 ``figs/``
（替换当前的 OCR 裁切图），并为每个受影响的 LaTeX 文档生成一张
「裁剪前后对比大图」（每行：左=裁剪输入，右=裁剪后的各子图，从左到右排列；
有 ``erase``/``erase_labels`` 的条目在左栏原图上用**红框**标出擦除区，便于核对是否越界）。

定位与流程
----------
1. ``scan``：对整个 ``pdfimages/`` 批量生成候选框预览（splitpicture ``detect --panels``）并列出
   **多子图（≥2）候选与标签数**，快速定位需要裁剪的内嵌图（输出到 ``<pdfimages>/review/``）；
2. ``split``：对单张内嵌图做**空白带/标签行分幅**，输出候选框预览（也可用 splitpicture GUI 手动框选），
   供**人工逐张核对**；
3. ``labels``：对单张内嵌图调用 splitpicture ``detect --json``，打印**图形框与标签框**
   （标签含 kind/text），可导出标签 JSON 与标注预览——用于写 recipe 的 ``erase``/``erase_labels``；
4. **写 recipe**：登记 ``source`` 内嵌图与其 ``crops``（每块 ``rect`` 与目标 ``target``）；
   ``rect`` 可人工微调——这是“裁剪一个核对一个”的落点；
5. ``preview``（**只读**，需 splitpicture ≥0.4）：按 recipe 生成 splitpicture ``detect --preview``
   叠加预览——**绿=recipe 实裁框（crops.rect）、黄=擦除框（erase + erase_labels）**，红/蓝为
   splitpicture 自身的检出图形/标签，供 ``apply`` 前核对“打算怎么切、擦哪里”；
6. ``apply``：按 recipe 调用 **splitpicture** 逐块裁剪，回填 ``figs/``（原图备份到
   ``figs/.ocr_before/``，Git 忽略），并按文档生成「裁剪前后对比大图」。

> **所有裁剪/擦除结果都必须逐张核对**：``apply`` 会为每个受影响文档在 ``crop_compare/``
> 生成 ``<文档>_裁剪前后.png``，请逐行打开对比“左=原图（红框=擦除区） / 右=回填子图”，
> 确认无多裁、少裁、残留标签（甲乙丙丁、A–D、图题）后再编译。

recipe 格式（路径相对项目根目录）::

    {
      "entries": [
        {
          "source": "材料处理/<年>/<地区>/pdfimages/p6_26.jpg",
          "crops": [
            {"rect": [x, y, w, h], "target": "试卷/<年>/<地区>/figs/pqA.jpg"},
            ...
          ],
          "erase": [[x, y, w, h], ...],
          "erase_labels": "panels",
          "trim": {"padding": 8}
        }
      ]
    }

- 可选 ``erase``：手工给出的擦除矩形（源坐标）。用于「子图标签与图内文字同高、无法用矩形裁剪
  单独排除」（如 2.1 `hw1C` 的 丙 与 电源 同高）；
- 可选 ``erase_labels``：由 **splitpicture 自动检测标签**再擦除，取值 ``"panels"``（默认）、
  ``"options"`` 或 ``"default"``。用于无需手算标签坐标的情形（仍须在对比图中核对擦除是否正确）；
  与 ``erase`` 可同时使用，二者合并为 ``labels.json``，交 **splitpicture ``--labels-file``**
  在**裁剪前原生擦除**。源文件不变；输入仍是原图（JPEG 质量估计正确），不产生中间 PNG；
  对比图左栏为原图并用**红框**标出擦除区。
- 可选 ``trim``（**建议开启**）：裁剪后调用 **splitpicture ``--trim``** 逐块去掉内容四周的空白边，
  使回填图更紧凑（避免图上出现多余留白）。取值 ``true`` 或 ``{"padding": N, "threshold": N}``
  （``padding`` 为保留的内容外边距像素，``threshold`` 为判白阈值 0–255）；也可按 entry 单独给。
  **开启 trim 后 target 尺寸会小于 ``rect``**，故 ``check_recrop`` 对开启 trim 的 recipe
  只校验 target 尺寸「不大于 rect」而非严格相等。

用法::

    # 1) 批量分诊（列出多子图候选与标签数）
    python3 tools/recrop_figures.py scan <处理目录>/pdfimages

    # 2) 预览单张子图候选框（人工核对 rect）
    python3 tools/recrop_figures.py split <内嵌图>.jpg -o preview.png

    # 2b) 查看/导出某内嵌图的图形框与标签框（辅助写 recipe）
    python3 tools/recrop_figures.py labels <内嵌图>.jpg --mode panels -o labels.json

    # 2c) 只读叠加预览：绿=recipe 实裁框、黄=擦除框（需 splitpicture ≥0.4）
    python3 tools/recrop_figures.py preview "试卷/<年>/<地区>/.recrop.json"

    # 3) 裁剪回填并生成对比大图
    python3 tools/recrop_figures.py apply "试卷/<年>/<地区>/.recrop.json"

> ``split``/``scan`` 的 ``--tight``（splitpicture ≥0.4）只做**分诊/预览**：它沿重叠区中线
> **收缩**相互侵入的检测框，可能切掉边缘内容，**不能替代按内容取框、不得作为最终实裁框**；
> 最终 ``rect`` 仍以人工按图形实际内容取框、并以 ``crop_compare/``（及 ``preview`` 预览）核对为准。

说明：裁剪实际由 splitpicture 完成（``split -i <source> --rects-file <rects> --json``；
有擦除时再加 ``--labels-file <labels>``）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SPLITPICTURE = os.environ.get("SPLITPICTURE", "splitpicture")
FIG_BACKUP_DIR = ".ocr_before"
OUT_DIRNAME = "crop_compare"  # apply 的「裁剪前后对比图」存放目录（Git 忽略）
OUT_PREVIEW_DIRNAME = "crop_preview"  # preview 的「只读叠加预览」存放目录（Git 忽略）


# --------------------------------------------------------------------------
# 子图分割（空白带投影，600dpi 内嵌图）
# --------------------------------------------------------------------------
def _segments(ink: np.ndarray, min_gap: int, min_size: int) -> List[Tuple[int, int]]:
    idx = np.flatnonzero(ink)
    if idx.size == 0:
        return []
    segs: List[Tuple[int, int]] = []
    start = prev = int(idx[0])
    for i in idx[1:].tolist():
        if i - prev - 1 >= min_gap:
            segs.append((start, prev))
            start = i
        prev = i
    segs.append((start, prev))
    return [(a, b) for a, b in segs if b - a + 1 >= min_size]


def split_subfigures(img: Image.Image, threshold: int = 200, min_gap: int = 25,
                     min_size: int = 80, pad: int = 6) -> List[Tuple[int, int, int, int]]:
    """返回子图矩形 ``(x, y, w, h)`` 列表（阅读顺序：先上排后下排，行内从左到右）。"""
    g = np.asarray(img.convert("L"), dtype=np.int16)
    ink = g < threshold  # True=有内容
    if not ink.any():
        return []
    H, W = ink.shape
    row_ink = ink.any(axis=1)
    col_ink = ink.any(axis=0)
    rows = _segments(row_ink, min_gap, min_size)
    boxes: List[Tuple[int, int, int, int]] = []

    def add_cols(y0: int, y1: int):
        sub = ink[y0:y1 + 1, :]
        sub_col = sub.any(axis=0)
        cols = _segments(sub_col, min_gap, min_size)
        for x0, x1 in cols:
            bx0 = max(0, x0 - pad)
            by0 = max(0, y0 - pad)
            bx1 = min(W - 1, x1 + pad)
            by1 = min(H - 1, y1 + pad)
            boxes.append((bx0, by0, bx1 - bx0 + 1, by1 - by0 + 1))

    if len(rows) >= 2:
        for y0, y1 in rows:
            add_cols(y0, y1)
    else:
        add_cols(0, H - 1)
    return boxes


# --------------------------------------------------------------------------
# 文档引用与内嵌图定位
# --------------------------------------------------------------------------
FIGS_REF_RE = re.compile(r"\{figs/([^}]+)\.(?:jpg|jpeg|png)\}", re.I)


def referenced_figs(tex: Path) -> List[str]:
    text = tex.read_text(encoding="utf-8", errors="ignore")
    out = []
    for m in FIGS_REF_RE.finditer(text):
        out.append(m.group(1))
    return out


# --------------------------------------------------------------------------
# split 预览（优先用 splitpicture --panels：自动排除 A/B/C/D、图甲 等标签）
# --------------------------------------------------------------------------
def splitpicture_detect(source: Path, splitpicture: str, mode: str = "default",
                        extra: Optional[List[str]] = None) -> Optional[Dict]:
    """调用 splitpicture ``detect --json``，返回 ``{"figures":[...], "labels":[...]}``。

    ``mode``：``"default"`` / ``"panels"`` / ``"options"``。失败返回 None。
    ``labels`` 为 splitpicture ≥0.2 输出的标签框（旧版无该字段时为空列表）。
    """
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    cmd = [splitpicture, "detect", "-i", str(source), "--json"]
    if mode == "panels":
        cmd.append("--panels")
    elif mode == "options":
        cmd.append("--options")
    if extra:
        cmd += extra
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        return None
    try:
        data = json.loads(proc.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return None
    figures = [(int(r["x"]), int(r["y"]), int(r["w"]), int(r["h"]))
               for r in data.get("rects", [])]
    labels = data.get("labels", []) or []
    return {"figures": figures, "labels": labels}


def splitpicture_panels(source: Path, splitpicture: str,
                        tight: bool = False) -> Optional[List[Tuple[int, int, int, int]]]:
    """调用 splitpicture ``detect --panels`` 得到子图框（已排除标签），失败返回 None。

    ``tight``（splitpicture ≥0.4）：对相互侵入的检测框沿重叠区中线收缩。**仅用于分诊/预览**，
    会收缩框、可能切掉边缘内容，**不可作为最终实裁框**。
    """
    res = splitpicture_detect(source, splitpicture, mode="panels",
                              extra=["--tight"] if tight else None)
    if not res or not res["figures"]:
        return None
    return res["figures"]


def splitpicture_capabilities(splitpicture: str) -> Optional[Dict]:
    """调用 splitpicture ``--capabilities`` 返回能力对象；不支持或解析失败返回 None。

    旧版（<0.4）无 ``--capabilities``，此时返回 None，调用方应保守处理。
    """
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        proc = subprocess.run([splitpicture, "--capabilities"],
                              capture_output=True, text=True, env=env)
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    try:
        data = json.loads(proc.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return None
    return data if isinstance(data, dict) else None


def splitpicture_features(splitpicture: str) -> Optional[set]:
    """取 ``--capabilities`` 的 ``features`` 集合；不支持或解析失败返回 None（保守跳过预检）。"""
    cap = splitpicture_capabilities(splitpicture)
    feats = cap.get("features") if cap else None
    return set(feats) if isinstance(feats, list) else None


def _version_ge(version: str, major: int, minor: int) -> bool:
    """版本号 ``a.b`` 是否 ≥ ``major.minor``（无法解析时返回 False）。"""
    nums = re.findall(r"\d+", version or "")
    if len(nums) < 2:
        return False
    return (int(nums[0]), int(nums[1])) >= (major, minor)


def entry_label_rects(ent: Dict, source: Path, splitpicture: str) -> Optional[List[List[int]]]:
    """返回一个 recipe entry 的擦除框（手工 ``erase`` + ``erase_labels`` 自动检测外扩）。

    供 ``apply`` 与 ``preview`` 共用，确保预览与实际擦除完全一致；检测失败返回 None。
    """
    label_rects: List[List[int]] = [list(r) for r in (ent.get("erase") or [])]
    el = ent.get("erase_labels")
    if el:
        mode = el if isinstance(el, str) else "panels"
        res = splitpicture_detect(source, splitpicture, mode=mode)
        if res is None:
            return None
        for l in res["labels"]:
            pad = max(4, int(round(0.10 * max(int(l["w"]), int(l["h"])))))
            label_rects.append([int(l["x"]) - pad, int(l["y"]) - pad,
                                int(l["w"]) + 2 * pad, int(l["h"]) + 2 * pad])
    return label_rects


def _draw_detect_preview(source: Path, figures, labels, out: Path) -> None:
    """把图形框（红）与标签框（蓝）画到图上另存，便于人工核对。"""
    rgb = Image.open(source).convert("RGB")
    d = ImageDraw.Draw(rgb)
    for i, (x, y, w, h) in enumerate(figures, 1):
        d.rectangle([x, y, x + w, y + h], outline=(255, 0, 0), width=3)
        d.text((x + 3, y + 3), f"F{i}", fill=(255, 0, 0))
    for i, l in enumerate(labels, 1):
        x, y, w, h = (int(l[k]) for k in ("x", "y", "w", "h"))
        d.rectangle([x, y, x + w, y + h], outline=(0, 0, 255), width=3)
        d.text((x + 3, y + h - 14), f"L{i}", fill=(0, 0, 255))
    out.parent.mkdir(parents=True, exist_ok=True)
    rgb.save(out)


def cmd_labels(source: Path, mode: str, out: Optional[Path], preview: Optional[Path],
               splitpicture: str) -> int:
    """打印（并可导出）splitpicture 检测到的图形框与标签框，辅助写 recipe。"""
    res = splitpicture_detect(source, splitpicture, mode=mode)
    if res is None:
        print(f"[错误] splitpicture detect 失败：{source}", file=sys.stderr)
        return 1
    print(f"{source.name}: 图形 {len(res['figures'])} 个，标签 {len(res['labels'])} 个"
          f"（mode={mode}）")
    for i, (x, y, w, h) in enumerate(res["figures"], 1):
        print(f"  图形{i}: [{x}, {y}, {w}, {h}]")
    for i, l in enumerate(res["labels"], 1):
        print(f"  标签{i}: [{int(l['x'])}, {int(l['y'])}, {int(l['w'])}, {int(l['h'])}]"
              f" kind={l.get('kind', '')} text={l.get('text', '')!r}")
    if out:
        rects = [{k: int(l[k]) for k in ("x", "y", "w", "h")} for l in res["labels"]]
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(rects, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  标签框已写入: {out}")
    if preview:
        _draw_detect_preview(source, res["figures"], res["labels"], preview)
        print(f"  标注预览: {preview}")
    print("  提示：检测结果仅供参考，请打开预览逐张核对后再写入 recipe。")
    return 0


def cmd_split(source: Path, min_gap: int, min_size: int, out: Optional[Path],
              splitpicture: str, tight: bool = False) -> int:
    boxes = splitpicture_panels(source, splitpicture, tight=tight)
    used = "splitpicture --panels（已排除标签）" + ("＋--tight" if tight else "")
    if boxes is None:
        boxes = split_subfigures(Image.open(source).convert("L"), min_gap=min_gap, min_size=min_size)
        used = "内置空白带分割（splitpicture 不可用时的兜底）"
    print(f"{source}: 检出 {len(boxes)} 个子图（{used}）")
    for i, (x, y, w, h) in enumerate(boxes, 1):
        print(f"   {i}: [{x}, {y}, {w}, {h}]")
    prev = out or (source.with_suffix(".split_preview.png"))
    rgb = Image.open(source).convert("RGB")
    d = ImageDraw.Draw(rgb)
    for i, (x, y, w, h) in enumerate(boxes, 1):
        d.rectangle([x, y, x + w, y + h], outline=(255, 0, 0), width=3)
        d.text((x + 3, y + 3), str(i), fill=(255, 0, 0))
    rgb.save(prev)
    print(f"   预览: {prev}")
    return 0


# --------------------------------------------------------------------------
# scan：批量预览候选框（splitpicture --panels），用于分诊“单图 / 多子图”
# --------------------------------------------------------------------------
def cmd_scan(target: Path, out: Optional[Path], jobs: int, min_side: int, splitpicture: str,
             tight: bool = False, recipe_out: Optional[Path] = None) -> int:
    if (target / "manifest.json").is_file():
        pdfdir = target
    elif (target / "pdfimages" / "manifest.json").is_file():
        pdfdir = target / "pdfimages"
    else:
        print(f"[错误] 未找到 pdfimages/manifest.json：{target}（先运行 make extract-images）",
              file=sys.stderr)
        return 1
    data = json.loads((pdfdir / "manifest.json").read_text(encoding="utf-8"))
    files = [e["file"] for e in data.get("images", [])
             if min(int(e["width"]), int(e["height"])) >= min_side]
    if not files:
        print("没有符合条件的候选图（尺寸都小于阈值）。")
        return 0
    out = out or (pdfdir / "review")
    out.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    # splitpicture ≥0.3 基线：直接统计标签，不再用返回码探测旧版支持
    cmd = [splitpicture, "detect"]
    for f in files:
        cmd += ["-i", str(pdfdir / f)]
    cmd += ["--panels", "--save-rects", "--save-labels", "--preview",
            "--per-file-subdir", "-d", str(out), "--jobs", str(jobs), "--json"]
    if tight:
        cmd.append("--tight")
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        print(f"[错误] splitpicture 批量检测失败：{proc.stderr.strip()[:300]}", file=sys.stderr)
        return 1

    def _count(path: Path) -> int:
        if not path.is_file():
            return 0
        try:
            return len(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            return 0

    rows = []
    for f in files:
        d = out / Path(f).stem
        rows.append((_count(d / "rects.json"), _count(d / "labels.json"), f))
    rows.sort(key=lambda r: (-r[0], r[1]))

    def rel(p: Path) -> str:
        try:
            return str(p.resolve().relative_to(ROOT))
        except ValueError:
            return str(p)

    print(f"批量检测完成：候选 {len(files)} 张，其中多子图（≥2）"
          f"{sum(1 for r in rows if r[0] >= 2)} 张（含标签统计）。")
    print(f"候选预览/矩形目录：{rel(out)}")
    print(f"{'子图数':>6}{'标签数':>8}  文件")
    for n, nl, f in rows:
        if n >= 2 or nl > 0:
            print(f"{n:>6}{nl:>8}  {f}")
    print("说明：仅列出子图≥2 或检出标签的候选；请逐个打开 preview.png 核对后写入 recipe；单图不裁。")

    # 可选：为多子图候选生成 .recrop.json 草稿（rect 取自 scan 结果，target 为占位名，
    # 需人工按题号把 target 改成 figs/<题号><子图字母>.<ext> 后核对/apply）。
    if recipe_out is not None:
        base = _propose_figs_base(pdfdir)
        if base is None:
            print("[提示] 无法从路径推断 试卷/<年>/<地区>/figs，跳过 recipe 草稿。")
        else:
            entries = []
            for n, _nl, f in rows:
                if n < 2:
                    continue
                rects_path = out / Path(f).stem / "rects.json"
                try:
                    arr = json.loads(rects_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                crops = []
                for j, r in enumerate(arr):
                    crops.append({
                        "rect": [int(r["x"]), int(r["y"]), int(r["w"]), int(r["h"])],
                        "target": f"{base}/{Path(f).stem}{chr(ord('a') + j)}.png",
                    })
                if crops:
                    entries.append({
                        "source": str((pdfdir / f).resolve().relative_to(ROOT)),
                        "crops": crops,
                        "trim": {"padding": 8},
                    })
            recipe_out.parent.mkdir(parents=True, exist_ok=True)
            recipe_out.write_text(
                json.dumps({"entries": entries}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            print(f"recipe 草稿已写入：{rel(recipe_out)}（{len(entries)} 条；"
                  "请把各 target 改名到 figs/<题号><子图字母>.png 并逐张核对后 apply）")
    return 0


def _propose_figs_base(pdfdir: Path) -> Optional[str]:
    """由 <...>/材料处理/<年>/<地区>/pdfimages 推断 试卷/<年>/<地区>/figs 前缀。"""
    parts = pdfdir.resolve().parts
    if "材料处理" not in parts:
        return None
    i = parts.index("材料处理")
    if len(parts) < i + 3:
        return None
    year, region = parts[i + 1], parts[i + 2]
    return f"试卷/{year}/{region}/figs"


# --------------------------------------------------------------------------
# apply：裁剪回填 + 对比大图
# --------------------------------------------------------------------------
def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for p in ["/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
              "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
              "/usr/share/fonts/wenquanyi/wqy-zenhei/wqy-zenhei.ttc",
              "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _fit(im: Image.Image, h: int) -> Image.Image:
    if im.height == 0:
        return im
    w = max(1, int(im.width * h / im.height))
    return im.resize((w, h), Image.LANCZOS)


def _crop_removes_ink(source: Path, rect) -> bool:
    """裁剪矩形之外（被切除的区域）是否含非空白内容（如“图甲/图1/A”等标签）。

    仅有空白 → 视为“去白边”，无需 crop_compare；含明显墨迹 → 需要人工核对。
    源图无法读取时保守返回 True（要求比对）。
    """
    try:
        img = Image.open(source)
    except Exception:
        return True
    x, y, w, h = (int(v) for v in rect)
    W, H = img.size
    g = np.asarray(img.convert("L"), dtype=np.int16)
    mask = np.ones(g.shape, dtype=bool)
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(W, x + w), min(H, y + h)
    mask[y0:y1, x0:x1] = False
    removed = g[mask]
    if removed.size == 0:
        return False
    return int((removed < 200).sum()) > max(50, int(removed.size * 0.001))


def cmd_apply(recipe_path: Path, splitpicture: str) -> int:
    recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
    entries = recipe.get("entries", [])
    splitpicture = recipe.get("splitpicture", splitpicture)
    recipe_trim = recipe.get("trim")
    # P3：能力预检（旧版无 --capabilities 时 splitpicture_features 返回 None，保守跳过）
    feats = splitpicture_features(splitpicture)
    if feats is not None and "json-items" not in feats:
        print(f"[错误] splitpicture 过旧（缺少 `split --json` 的 `items`）：请升级到 ≥0.3；"
              f"可用 `{splitpicture} --capabilities` 查看能力", file=sys.stderr)
        return 1

    def _trim_args(trim) -> List[str]:
        """把 recipe/entry 的 ``trim`` 配置转成 splitpicture 命令行参数。"""
        if not trim:
            return []
        args = ["--trim"]
        if isinstance(trim, dict):
            if trim.get("padding") is not None:
                args += ["--white-padding", str(int(trim["padding"]))]
            if trim.get("threshold") is not None:
                args += ["--threshold", str(int(trim["threshold"]))]
        return args

    # 1) 裁剪并回填
    applied: List[Dict] = []
    for ent in entries:
        source = (ROOT / ent["source"]).resolve() if not Path(ent["source"]).is_absolute() else Path(ent["source"])
        crops = ent["crops"]
        trim_args = _trim_args(ent.get("trim", recipe_trim))
        # 可选 erase：手工擦除矩形（源坐标）；erase_labels：由 splitpicture 自动检测标签。
        # 二者合并为 labels.json，交 splitpicture 在裁剪前原生擦除（不动源文件）；
        # 输入仍是原图（JPEG 质量估计正确），也不再产生 PIL 中间 PNG。
        label_rects = entry_label_rects(ent, source, splitpicture)
        if label_rects is None:
            print(f"[错误] erase_labels 检测失败：{source}", file=sys.stderr)
            return 1
        if ent.get("erase_labels"):
            n_manual = len(ent.get("erase") or [])
            print(f"[擦除] {source.name}: erase_labels 检出 {len(label_rects) - n_manual} 个标签")
        tmp = source.parent / ".recrop_tmp"
        if tmp.exists():
            shutil.rmtree(tmp)
        tmp.mkdir(parents=True)
        # 逐矩形写 output（落在 tmp，文件名保留目标扩展名）：splitpicture 按 output
        # 扩展名选择编码器，避免“PNG 字节写进 .jpg”这类字节与扩展名不符的问题。
        rects = []
        for i, c in enumerate(crops):
            tgt = (ROOT / c["target"]) if not Path(c["target"]).is_absolute() else Path(c["target"])
            rects.append({"x": int(c["rect"][0]), "y": int(c["rect"][1]),
                          "w": int(c["rect"][2]), "h": int(c["rect"][3]),
                          "output": str(tmp / f"{i:03d}_{tgt.name}")})
        rects_file = tmp / "rects.json"
        rects_file.write_text(json.dumps(rects), encoding="utf-8")
        split_args = [splitpicture, "split", "-i", str(source),
                      "--rects-file", str(rects_file), "--json", *trim_args]
        if label_rects:
            # splitpicture --labels-file 消费与 --save-labels 同格式的矩形数组（{x,y,w,h}），
            # 在裁剪前把标签/手工框涂白；手工框与自动标签在此合并。源文件不变。
            labels_file = tmp / "labels.json"
            labels_file.write_text(json.dumps(
                [{"x": int(x), "y": int(y), "w": int(w), "h": int(h)}
                 for x, y, w, h in label_rects], ensure_ascii=False), encoding="utf-8")
            split_args += ["--labels-file", str(labels_file)]
        env = dict(os.environ)
        env.setdefault("QT_QPA_PLATFORM", "offscreen")
        proc = subprocess.run(split_args, capture_output=True, text=True, env=env)
        if proc.returncode != 0:
            shutil.rmtree(tmp, ignore_errors=True)
            print(f"[错误] splitpicture 失败：{source}\n{proc.stderr}", file=sys.stderr)
            return 1
        # 以 splitpicture ``split --json`` 的 ``items``（rect → output → skipped/ok）
        # 建立权威映射：序与 crops 一一对应，且显式标注被 --trim 跳过的全白块。
        try:
            split_data = json.loads(proc.stdout.strip().splitlines()[-1])
        except (json.JSONDecodeError, IndexError):
            shutil.rmtree(tmp, ignore_errors=True)
            print(f"[错误] 无法解析 splitpicture 输出：{source}", file=sys.stderr)
            return 1
        items = split_data.get("items")
        if not isinstance(items, list) or len(items) != len(crops):
            shutil.rmtree(tmp, ignore_errors=True)
            got = len(items) if isinstance(items, list) else "无 items"
            print(f"[错误] 裁剪项数不符：{source} 期望 {len(crops)} 实得 {got}"
                  "（需 splitpicture ≥0.3）", file=sys.stderr)
            return 1
        skipped = [(c, it) for c, it in zip(crops, items)
                   if it.get("skipped") or not it.get("output")]
        if skipped:
            shutil.rmtree(tmp, ignore_errors=True)
            for crop, it in skipped:
                print(f"[错误] 裁剪为全白被跳过：{source.name} "
                      f"rect={it.get('rect') or crop['rect']}"
                      "（rect 取值有误或 erase 擦到了整块，请修正 recipe）", file=sys.stderr)
            return 1
        # 逐块回填：items 与 crops 一一对应，故 target 取 crops 顺序即可
        for crop, item in zip(crops, items):
            target = (ROOT / crop["target"]) if not Path(crop["target"]).is_absolute() else Path(crop["target"])
            target.parent.mkdir(parents=True, exist_ok=True)
            backup = target.parent / FIG_BACKUP_DIR / target.name
            if target.is_file() and not backup.exists():
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup)
            shutil.copy2(Path(item["output"]), target)
        shutil.rmtree(tmp, ignore_errors=True)
        # 是否生成 crop_compare 对比图：
        #   - 条目显式给 "compare": true/false 以覆盖默认；
        #   - 默认规则：
        #       * 切成多块（>=2）                → 生成（多子图切分必须核对）；
        #       * 有 erase / erase_labels（擦除）  → 生成（擦除必须核对）；
        #       * 单块但**切掉了非空白内容**（如“图甲/图1/A”等标签）→ 生成；
        #       * 单块且**仅去白边**（被切掉的区域全是空白）→ **不生成**
        #         （本身即一张独立图，无需比对；该内容也就不需要 crop_compare 目录）。
        compare = ent.get("compare")
        if compare is None:
            if ent.get("erase") or ent.get("erase_labels"):
                compare = True
            elif len(crops) >= 2:
                compare = True
            else:
                compare = _crop_removes_ink(source, crops[0]["rect"])
        if compare:
            applied.append({"source": source,
                            "crops": [(c, str((ROOT / c["target"]).relative_to(ROOT))) for c in crops],
                            "erase": label_rects})
        print(f"[回填] {source.name}: {len(crops)} 块" + ("" if compare else "（仅去白边，不生成 crop_compare）"))

    # 2) 每个受影响文档生成对比大图
    make_sheets(applied)
    return 0


def cmd_preview(recipe_path: Path, out_dir: Optional[Path], splitpicture: str) -> int:
    """只读：对 recipe 每个 source 生成 splitpicture 叠加预览，供 apply 前核对。

    需要 splitpicture ≥0.4 的 ``detect --preview`` 外部框叠加：**绿=recipe 实裁框**
    （``crops.rect``）、**黄=擦除框**（``erase`` + ``erase_labels`` 自动检测框，与 ``apply``
    完全一致）；红/蓝为 splitpicture 自身检出的图形/标签。不动 ``figs/``、不裁剪。
    """
    recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
    entries = recipe.get("entries", [])
    splitpicture = recipe.get("splitpicture", splitpicture)
    # 外部框叠加（--rects-file/--labels-file 于 detect）为 splitpicture ≥0.4 能力；
    # 旧版会静默不画绿/黄框，故先按版本拒绝，避免给出误导性的“成功”预览。
    cap = splitpicture_capabilities(splitpicture)
    version = str((cap or {}).get("version", ""))
    if not _version_ge(version, 0, 4):
        print(f"[错误] preview 需要 splitpicture ≥0.4（detect --preview 外部框叠加）；"
              f"当前版本 {version or '未知'}", file=sys.stderr)
        return 1
    out = out_dir or (recipe_path.parent / OUT_PREVIEW_DIRNAME)
    out.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    rc = 0
    for ei, ent in enumerate(entries):
        source = (ROOT / ent["source"]).resolve() if not Path(ent["source"]).is_absolute() \
            else Path(ent["source"])
        if not source.is_file():
            print(f"[错误] source 不存在：{source}", file=sys.stderr)
            rc = 1
            continue
        label_rects = entry_label_rects(ent, source, splitpicture)
        if label_rects is None:
            print(f"[错误] erase_labels 检测失败：{source}", file=sys.stderr)
            rc = 1
            continue
        preview = out / f"{source.stem}.splitpicture.png"
        if preview.exists():
            preview = out / f"{source.stem}_{ei}.splitpicture.png"
        with tempfile.TemporaryDirectory(prefix="recrop_preview_") as td:
            rects_file = Path(td) / "rects.json"
            rects_file.write_text(json.dumps(
                [{"x": int(c["rect"][0]), "y": int(c["rect"][1]),
                  "w": int(c["rect"][2]), "h": int(c["rect"][3])} for c in ent["crops"]]),
                encoding="utf-8")
            args = [splitpicture, "detect", "-i", str(source),
                    "--preview", str(preview), "--rects-file", str(rects_file), "--json"]
            if label_rects:
                labels_file = Path(td) / "labels.json"
                labels_file.write_text(json.dumps(
                    [{"x": int(x), "y": int(y), "w": int(w), "h": int(h)}
                     for x, y, w, h in label_rects], ensure_ascii=False), encoding="utf-8")
                args += ["--labels-file", str(labels_file)]
            proc = subprocess.run(args, capture_output=True, text=True, env=env)
        if proc.returncode != 0:
            print(f"[错误] splitpicture 预览失败：{source}\n{proc.stderr}", file=sys.stderr)
            rc = 1
            continue
        try:
            rel = preview.relative_to(ROOT)
        except ValueError:
            rel = preview
        print(f"[预览] {rel}（绿=实裁框、黄=擦除框、红=检出图形、蓝=检出标签）")
    return rc


def make_sheets(applied: List[Dict], row_h: int = 240, pad: int = 12) -> None:
    """为每个受影响的 LaTeX 文档生成「裁剪前后对比大图」。

    每行：左=裁剪输入（提取原图；有 ``erase``/``erase_labels`` 时在图上用**红框**标出
    擦除区），右=各子图裁剪结果（从左到右）。仅列出实际被裁剪的图（单一图不入表）。
    """
    font = _load_font(20)
    # 文档 -> {source: {"source": Path, "hits": [(crop, target_rel)], "erase": [rects]}}
    docs: Dict[Path, Dict[str, Dict]] = {}
    for ent in applied:
        source: Path = ent["source"]
        crops = ent["crops"]  # [(crop_dict, target_rel)]
        # 目标 figs 所在目录的上一级即课题目录
        for doc_dir in { (ROOT / t).parent.parent for _, t in crops }:
            for tex in sorted(doc_dir.glob("*.tex")):
                refs = set(referenced_figs(tex))
                hit = [(c, t) for c, t in crops if Path(t).stem in refs]
                if not hit:
                    continue
                info = docs.setdefault(tex, {}).setdefault(
                    str(source), {"source": source, "hits": [], "erase": []})
                info["hits"].extend(hit)
                info["erase"].extend(ent.get("erase") or [])

    for tex, source_map in docs.items():
        rows = []
        left_w = right_w = 0
        for info in source_map.values():
            source = info["source"]
            hit = info["hits"]
            orig = Image.open(source).convert("RGB")
            left = _fit(orig, row_h)
            if info["erase"]:
                # 在左栏原图上用红框叠加画出擦除区域，便于核对“擦得对不对”
                left = left.copy()
                ld = ImageDraw.Draw(left)
                sx = left.width / orig.width if orig.width else 1.0
                sy = left.height / orig.height if orig.height else 1.0
                for x, y, w, h in info["erase"]:
                    ld.rectangle([x * sx, y * sy, (x + w) * sx, (y + h) * sy],
                                 outline=(255, 0, 0), width=2)
            rights = [_fit(Image.open(ROOT / t).convert("RGB"), row_h) for _, t in hit]
            rw = sum(im.width for im in rights) + pad * max(0, len(rights) - 1)
            left_w = max(left_w, left.width)
            right_w = max(right_w, rw)
            rows.append((source, info["erase"], left, hit, rights))
        if not rows:
            continue

        label_h = 30
        gap = 22
        title_h = 56
        col_gap = 44
        mid = pad + left_w + col_gap // 2
        width = mid + col_gap // 2 + right_w + pad
        block_h = row_h + label_h
        total_h = title_h + len(rows) * (block_h + gap) + pad
        canvas = Image.new("RGB", (width, total_h), (255, 255, 255))
        d = ImageDraw.Draw(canvas)
        f18 = _load_font(18)
        f14 = _load_font(14)
        d.text((pad, 10), f"裁剪前后对比：{tex.name}", fill=(0, 0, 0), font=font)
        d.text((pad, 32), "左：原图（红框＝擦除区）　右：裁剪后（回填到 figs/；已排除图中 A/B/C/D、图甲 等标签）",
               fill=(90, 90, 90), font=f14)
        d.rectangle([0, 0, width - 1, total_h - 1], outline=(120, 120, 120), width=1)

        y = title_h
        for source, erase, left, hit, rights in rows:
            top = y
            bottom = top + block_h
            # 行与行之间的分隔线（画在本行底部间隙中间）
            d.line([(pad, bottom + gap // 2), (width - pad, bottom + gap // 2)],
                   fill=(150, 150, 150), width=2)
            # 裁剪输入 / 裁剪后 的分隔竖线
            d.line([(mid, top), (mid, bottom)], fill=(120, 120, 120), width=2)
            # 左：原图（有 erase 时叠红框）
            canvas.paste(left, (pad, top))
            label = f"裁剪输入（红框＝擦除区）：{source.name}" if erase else f"裁剪输入：{source.name}"
            d.text((pad, top + row_h + 4), label, fill=(150, 0, 0), font=f18)
            # 右：各子图（裁剪后），图与图之间加细分隔线
            x = mid + col_gap // 2
            for j, ((crop, target_rel), im) in enumerate(zip(hit, rights)):
                canvas.paste(im, (x, top))
                d.text((x, top + row_h + 4), Path(target_rel).name, fill=(0, 90, 0), font=f18)
                x += im.width
                if j < len(rights) - 1:
                    d.line([(x + pad // 2, top), (x + pad // 2, bottom)],
                           fill=(210, 210, 210), width=1)
                    x += pad
            y = bottom + gap

        out_dir = tex.parent / OUT_DIRNAME
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"{tex.stem}_裁剪前后.png"
        canvas.save(out)
        print(f"[对比图] {out.relative_to(ROOT)}")



def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="内嵌图子图裁剪回填与裁剪前后对比图")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_split = sub.add_parser("split", help="对单张内嵌图做子图分割预览（splitpicture --panels）")
    p_split.add_argument("source")
    p_split.add_argument("--min-gap", type=int, default=25)
    p_split.add_argument("--min-size", type=int, default=80)
    p_split.add_argument("--splitpicture", default=DEFAULT_SPLITPICTURE)
    p_split.add_argument("--tight", action="store_true",
                         help="透传 splitpicture --tight（≥0.4）：收敛相互侵入的候选框；"
                              "仅分诊/预览用，会收缩框、可能切内容，勿作最终实裁框")
    p_split.add_argument("-o", "--out")

    p_labels = sub.add_parser("labels",
                              help="打印/导出内嵌图的图形框与标签框（splitpicture detect --json）")
    p_labels.add_argument("source")
    p_labels.add_argument("--mode", choices=["default", "panels", "options"], default="panels",
                          help="检测模式（默认 panels）")
    p_labels.add_argument("-o", "--out", help="标签框 JSON 输出路径")
    p_labels.add_argument("--preview", help="画出图形框(红)/标签框(蓝)的预览 PNG")
    p_labels.add_argument("--splitpicture", default=DEFAULT_SPLITPICTURE)

    p_apply = sub.add_parser("apply", help="按 recipe 裁剪回填并生成对比图")
    p_apply.add_argument("recipe")
    p_apply.add_argument("--splitpicture", default=DEFAULT_SPLITPICTURE)

    p_preview = sub.add_parser(
        "preview", help="只读：按 recipe 生成 splitpicture 叠加预览（≥0.4；绿=实裁框、黄=擦除框）")
    p_preview.add_argument("recipe")
    p_preview.add_argument("-o", "--out", help="预览输出目录（默认 recipe 同目录的 crop_preview/）")
    p_preview.add_argument("--splitpicture", default=DEFAULT_SPLITPICTURE)

    p_scan = sub.add_parser("scan", help="批量预览候选框并列出多子图（splitpicture --panels）")
    p_scan.add_argument("target", help="pdfimages 目录（或含 pdfimages/ 的处理/课题目录）")
    p_scan.add_argument("-o", "--out", help="预览/矩形输出目录（默认 <pdfimages>/review）")
    p_scan.add_argument("-j", "--jobs", type=int, default=4, help="并行数（默认 4）")
    p_scan.add_argument("--min-side", type=int, default=150, help="最小边阈值（默认 150px）")
    p_scan.add_argument("--splitpicture", default=DEFAULT_SPLITPICTURE)
    p_scan.add_argument("--tight", action="store_true",
                        help="透传 splitpicture --tight（≥0.4）：收敛相互侵入的候选框；"
                             "仅分诊/预览用，会收缩框、可能切内容，勿作最终实裁框")
    p_scan.add_argument("--recipe-out", help="为多子图候选生成 .recrop.json 草稿（占位 target，需人工改名）")

    args = parser.parse_args(argv)
    if args.cmd == "split":
        return cmd_split(Path(args.source).resolve(), args.min_gap, args.min_size,
                         Path(args.out) if args.out else None, args.splitpicture, args.tight)
    if args.cmd == "labels":
        return cmd_labels(Path(args.source).resolve(), args.mode,
                          Path(args.out) if args.out else None,
                          Path(args.preview) if args.preview else None,
                          args.splitpicture)
    if args.cmd == "scan":
        return cmd_scan(Path(args.target).resolve(),
                        Path(args.out).resolve() if args.out else None,
                        args.jobs, args.min_side, args.splitpicture, args.tight,
                        Path(args.recipe_out).resolve() if args.recipe_out else None)
    if args.cmd == "apply":
        return cmd_apply(Path(args.recipe).resolve(), args.splitpicture)
    if args.cmd == "preview":
        return cmd_preview(Path(args.recipe).resolve(),
                           Path(args.out).resolve() if args.out else None, args.splitpicture)
    return 1


if __name__ == "__main__":
    sys.exit(main())

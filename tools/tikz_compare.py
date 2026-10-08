#!/usr/bin/env python3
"""重绘 TikZ 图片与原始提取图的「重绘前后对比图」生成工具。

背景
----
各套高考真题中，**只有非常简单**的示意图、受力图、坐标图才由
TikZ 重画（``TikZ/<名>.tex`` → ``TikZ/<名>.pdf``）；稍微复杂或实物图一律用原 PDF 提取的原图放
``figs/``。为便于**人工逐张核对** TikZ 重绘是否忠实于原题图（形状、方向、标注、比例等），
本工具仿照 ``tools/recrop_figures.py`` 的 ``crop_compare/`` 机制，生成 ``tikz_compare/``：

    tikz_compare/<文档名>_重绘前后.png     # 每份文档（导学案/教案/分层作业/课件/试卷/作业）一份，
                                           # 左=原图，右=重绘 TikZ；与该文档无关的图不入表

即与 ``crop_compare/<文档名>_裁剪前后.png`` 一一对应的分部分对比图。
**本工具适用于项目内所有含 TikZ 的目录**（各套高考真题）。

映射文件
--------
在目录的 ``TikZ/tikz_sources.json`` 中给出每张 TikZ 对应的原图，例如::

    {
      "entries": [
        {"tikz": "ex3a", "original": "材料处理/<年>/<地区>/ovis/images/page_4_bbox_...jpg",
         "note": "例3 图甲"}
      ]
    }

``original`` 为相对项目根目录的路径（取 ``材料处理/<年>/<地区>/ovis/images/page_*.jpg``；原书纯矢量图可渲染源 PDF 后
裁出存于 ``<处理目录>/tikz_originals/``）。同名 TikZ 只取第一条。
自编题（``%来源: 自编``）等确无原题图者，请登记 ``"original": null`` 显式声明（本工具会跳过、
不生成对比，也不再列为未登记）；一致性可用 ``tools/check_tikz.py``（``make check-tikz``）校验。

用法::

    python3 tools/tikz_compare.py <目录>          # 试卷/<年>/<地区> 目录（含 TikZ/）
    python3 tools/tikz_compare.py <目录> --dpi 200
    python3 tools/tikz_compare.py <目录> --no-orphans   # 只处理正文引用到的 TikZ
    make tikz-compare                            # 全项目（根目录）

两种提交方式都能处理
-------------------
- **标准（推荐）**：``TikZ/`` 下有 ``tikz_sources.json`` 登记原图，且本卷 ``.tex``
  已用 ``\\onepicture{TikZ/<名>.pdf}`` 接入。按文档分张生成对比图。
  原图可直接指向 ``试卷/<年>/<地区>/figs/<名>.png``（项目已把图放在 ``figs/``，
  一般**无需**再建 ``TikZ/originals/``；仅当原图不在 figs 时才另存）。
- **非标准但可处理**：只上传 ``TikZ/*.tex``（未登记、未接入）。**默认**会为这些
  “孤儿源”生成 ``tikz_compare/<目录名>_未引用TikZ_重绘前后.png``：原图按
  ``TikZ/originals/<名>`` → ``figs/<名>``（**同名**）自动推断。故该做法下
  **TikZ 文件名必须与 figs 原图同名**，否则无法配原图（会在输出中列出）。
  用 ``--no-orphans`` 可关闭。
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
from typing import Dict, List, Tuple

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT_DIRNAME = "tikz_compare"
TIKZ_REF = re.compile(r"TikZ/([A-Za-z0-9_\-]+)\.pdf")


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
    if im.height == 0 or im.height == h:
        return im
    w = max(1, int(im.width * h / im.height))
    return im.resize((w, h), Image.LANCZOS)


def load_mapping(lesson: Path) -> Tuple[Dict[str, Dict[str, str]], bool]:
    """返回 (映射, 映射文件是否存在)。缺失时返回空映射，由调用方按“是否有引用的 TikZ”决定是否报错。"""
    mapping = lesson / "TikZ" / "tikz_sources.json"
    if not mapping.exists():
        return {}, False
    data = json.loads(mapping.read_text(encoding="utf-8"))
    entries = data.get("entries", data if isinstance(data, list) else [])
    out: Dict[str, Dict[str, str]] = {}
    for e in entries:
        tikz = str(e.get("tikz", "")).strip()
        if tikz and tikz not in out:
            out[tikz] = e
    return out, True


def referenced_tikz(tex: Path) -> List[str]:
    """按出现顺序返回文档中引用的 TikZ 名（去重）。"""
    names: List[str] = []
    for m in TIKZ_REF.finditer(tex.read_text(encoding="utf-8")):
        n = m.group(1)
        if n not in names:
            names.append(n)
    return names


def tikz_sources(lesson: Path) -> List[str]:
    """返回 ``TikZ/*.tex`` 源文件名（去扩展名，排序）。"""
    d = lesson / "TikZ"
    if not d.is_dir():
        return []
    return sorted(p.stem for p in d.glob("*.tex"))


def render_tikz(pdf: Path, out_png: Path, dpi: int) -> bool:
    cmd = ["pdftoppm", "-r", str(dpi), "-png", "-singlefile", str(pdf), str(out_png.with_suffix(""))]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        return False
    return out_png.exists()


def _ellipsize(text: str, font, max_w: float) -> str:
    """把 text 截断到不超过 max_w 像素宽（超出加省略号）。"""
    if max_w <= 0 or font.getlength(text) <= max_w:
        return text
    ell = "…"
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if font.getlength(text[:mid] + ell) <= max_w:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo] + ell


def make_sheet(rows: List[Tuple[str, str, str, Image.Image, Image.Image]],
               title: str, row_h: int = 300, pad: int = 14) -> Image.Image:
    """rows: (tikz, orig_name, note, orig_img, tikz_img)。

    每行：左＝原图、右＝重绘 TikZ；下方两行标注——
    第一行：`原图：<文件名>` / `重绘：<名>.pdf`（各自截断到本栏宽度）；
    第二行：整行铺开的说明 note（避免与右栏重叠）。
    """
    label_h = 26
    note_h = 24
    gap = 18
    title_h = 58
    col_gap = 40
    f20, f16, f14 = _load_font(20), _load_font(16), _load_font(14)

    left_w = max((o.width for _, _, _, o, _ in rows), default=1)
    right_w = max((t.width for _, _, _, _, t in rows), default=1)
    mid = pad + left_w + col_gap // 2
    right_x = mid + col_gap // 2
    width = right_x + right_w + pad
    # 说明行可能很长，按需加宽画布，避免超出右边框
    note_w = max((f14.getlength(n) for _, _, n, _, _ in rows if n), default=0)
    width = max(width, int(note_w) + 2 * pad)
    maxw_left = mid - pad - 6
    maxw_right = width - right_x - pad
    maxw_note = width - 2 * pad
    block_h = row_h + label_h + note_h
    total_h = title_h + len(rows) * (block_h + gap) + pad
    canvas = Image.new("RGB", (width, total_h), (255, 255, 255))
    d = ImageDraw.Draw(canvas)
    d.text((pad, 8), title, fill=(0, 0, 0), font=f20)
    d.text((pad, 32), "左：原题图（提取原图）　右：重绘 TikZ　—— 请逐行核对形状/方向/标注/比例",
           fill=(90, 90, 90), font=f14)
    d.rectangle([0, 0, width - 1, total_h - 1], outline=(120, 120, 120), width=1)

    y = title_h
    for tikz, orig_name, note, orig, timg in rows:
        top = y
        bottom = top + block_h
        d.line([(mid, top), (mid, bottom)], fill=(120, 120, 120), width=2)
        d.line([(pad, bottom + gap // 2), (width - pad, bottom + gap // 2)],
               fill=(150, 150, 150), width=2)
        canvas.paste(orig, (pad, top))
        canvas.paste(timg, (right_x, top))
        d.text((pad, top + row_h + 4),
               f"原图：{_ellipsize(orig_name, f16, maxw_left - f16.getlength('原图：'))}",
               fill=(150, 0, 0), font=f16)
        d.text((right_x, top + row_h + 4),
               f"重绘：{_ellipsize(tikz + '.pdf', f16, maxw_right - f16.getlength('重绘：'))}",
               fill=(0, 90, 0), font=f16)
        if note:
            d.text((pad, top + row_h + label_h + 3),
                   f"说明：{_ellipsize(note, f14, maxw_note - f14.getlength('说明：'))}",
                   fill=(40, 40, 150), font=f14)
        y = bottom + gap
    return canvas


def _rel(p: Path) -> Path:
    """尽量给出相对项目根的路径，否则原样返回（便于目录在仓库外时也不报错）。"""
    try:
        return p.relative_to(ROOT)
    except ValueError:
        return p


def _infer_original(lesson: Path, tikz: str):
    """未登记时按 ``TikZ/originals/<名>`` → ``figs/<名>`` 推断原图，返回 entry 或 None。"""
    for base in ("TikZ/originals", "figs"):
        for ext in (".png", ".jpg", ".jpeg", ".jfif", ".svg"):
            p = lesson / base / f"{tikz}{ext}"
            if p.exists():
                return {"tikz": tikz, "original": str(_rel(p)), "note": "自动推断（未登记）"}
    return None


def _rasterize_svg(svg: Path, out_png: Path) -> bool:
    """把 SVG 渲染为 PNG（优先 rsvg-convert，退回 Inkscape）；成功返回 True。"""
    cmds = [
        ["rsvg-convert", "-b", "white", "-w", "1400", str(svg), "-o", str(out_png)],
        ["inkscape", str(svg), "-o", str(out_png), "-w", "1400"],
    ]
    for cmd in cmds:
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            continue
        if out_png.exists():
            return True
    return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="生成重绘 TikZ 与原图的分文档对比图（tikz_compare/）")
    ap.add_argument("lesson", help="目录（试卷/<年>/<地区>，含 TikZ/，如 试卷/<年>/<地区>）")
    ap.add_argument("--dpi", type=int, default=200, help="TikZ PDF 渲染 DPI（默认 200）")
    ap.add_argument("--row-h", type=int, default=300, help="每行图片高度（像素，默认 300）")
    ap.add_argument("--no-orphans", dest="include_orphans", action="store_false",
                    help="只处理正文引用到的 TikZ，忽略未接入的 TikZ 源（默认也处理孤儿源）")
    args = ap.parse_args(argv)

    lesson = Path(args.lesson).resolve()
    tikz_dir = lesson / "TikZ"
    out_dir = lesson / OUT_DIRNAME

    mapping, has_mapping = load_mapping(lesson)

    # 本目录各文档实际引用的 TikZ
    referenced_all: Dict[str, List[str]] = {}
    for tex in sorted(lesson.glob("*.tex")):
        refs = referenced_tikz(tex)
        if refs:
            referenced_all[tex.name] = refs
    total_refs = sorted({t for refs in referenced_all.values() for t in refs})

    # “孤儿源”：已上传 TikZ/*.tex 但未被任何 .tex 引用、也未登记原图（半成品/未接线）
    orphans = (sorted(set(tikz_sources(lesson)) - set(total_refs) - set(mapping))
               if args.include_orphans else [])

    if not total_refs and not orphans:
        print(f">> {lesson.name}：无 TikZ 引用，跳过。")
        return 0

    if total_refs and not has_mapping:
        raise SystemExit(
            f"缺少映射文件：{tikz_dir / 'tikz_sources.json'}\n"
            f"本目录的 .tex 引用了 TikZ（{', '.join(total_refs)}），"
            f"请先在 TikZ/tikz_sources.json 中登记每张 TikZ 对应的原图。")

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    tmp = Path(tempfile.mkdtemp(prefix="tikzcmp_"))
    rendered: Dict[str, Path] = {}
    missing: List[str] = []
    used: set = set()

    def make_rows(tikz_list: List[str], infer: bool):
        """把若干 TikZ 名解析为对比行；无法配到原图/未编译者记入 missing。"""
        rows = []
        for tikz in tikz_list:
            e = mapping.get(tikz)
            if e is None and infer:
                e = _infer_original(lesson, tikz)
            if e is None:
                missing.append(f"{tikz}.tex（未登记且未在 figs/ 等找到原图；"
                               "若有原图请登记 tikz_sources.json，或把原图命名为 figs/<名>.png）")
                continue
            # 已显式声明“无原题图”（自编题等，original 为 null/空）：不生成对比。
            if not e.get("original"):
                used.add(tikz)
                continue
            pdf = tikz_dir / f"{tikz}.pdf"
            if not pdf.exists():
                missing.append(f"{tikz}.pdf（未编译，先 make tikz）")
                continue
            original = (ROOT / str(e.get("original", ""))).resolve()
            if original.suffix.lower() == ".svg" and original.exists():
                png = tmp / f"{tikz}_orig.png"
                if _rasterize_svg(original, png):
                    original = png
            if not original.exists():
                missing.append(f"{tikz}: 原图不存在 {e.get('original')}")
                continue
            if tikz not in rendered:
                png = tmp / f"{tikz}.png"
                if not render_tikz(pdf, png, args.dpi):
                    missing.append(f"{tikz}.pdf（渲染失败）")
                    continue
                rendered[tikz] = png
            orig = _fit(Image.open(original).convert("RGB"), args.row_h)
            timg = _fit(Image.open(rendered[tikz]).convert("RGB"), args.row_h)
            rows.append((tikz, original.name, str(e.get("note", "")), orig, timg))
            used.add(tikz)
        return rows

    try:
        sheets = 0
        for tex in sorted(lesson.glob("*.tex")):
            refs = [t for t in referenced_tikz(tex) if t in mapping]
            if not refs:
                continue
            rows = make_rows(refs, infer=False)
            if rows:
                out = out_dir / f"{tex.stem}_重绘前后.png"
                make_sheet(rows, f"重绘前后对比：{tex.name}", row_h=args.row_h).save(out)
                print(f"[对比图] {_rel(out)}（{len(rows)} 张）")
                sheets += 1
        if orphans:
            rows = make_rows(orphans, infer=True)
            if rows:
                out = out_dir / f"{lesson.name}_未引用TikZ_重绘前后.png"
                make_sheet(rows, f"重绘前后对比（未接入正文的 TikZ 源）：{lesson.name}",
                           row_h=args.row_h).save(out)
                print(f"[对比图] {_rel(out)}（{len(rows)} 张，含未引用源）")
                sheets += 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    unused = sorted(set(mapping) - used)
    if unused:
        print("未在任何文档中引用的映射（可删除）：", ", ".join(unused))
    unmapped = sorted(set(total_refs) - set(mapping))
    if unmapped:
        print("\n以下被文档引用的 TikZ 未登记原图（自编题等无原题图者请登记 original: null）：",
              ", ".join(unmapped))
    if missing:
        print("\n未生成对比的条目：")
        for m in missing:
            print("  -", m)
    if sheets == 0:
        print("未生成对比图（引用到的 TikZ 均未登记原图；无原题图者属正常）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

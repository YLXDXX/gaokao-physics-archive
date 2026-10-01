#!/usr/bin/env python3
"""tools/check_recrop.py

校验各试卷目录下的 ``.recrop.json``（多子图裁剪 recipe）与
``figs/`` 的一致性，供 ``make check`` 使用。

检查项（[错误] 使退出码为 1）：

1. recipe 为合法 JSON，``entries`` 为数组，逐条含 ``source`` / ``crops``；
2. ``source`` 内嵌图存在；
3. 每块 ``rect = [x, y, w, h]``：w/h 为正、x/y 非负，且**不超出源图范围**；
4. 每个 ``target``：路径非空、扩展名为图片、**文件存在**，且**像素尺寸与 rect 一致**
   （不一致通常意味着修改 recipe 后未重新 ``apply``，或 figs 被手工替换）；
   若 recipe（或 entry）开启 ``trim``（裁剪后去白边），则只要求 target 尺寸**不大于** rect；
   并校验**文件头与扩展名是否相符**（如 PNG 字节不得名为 ``.jpg``）；
5. 同一 target 不被重复写入（跨 entry 去重）；
6. 可选字段 ``erase``（矩形列表）、``erase_labels``（``true`` / ``"panels"`` /
   ``"options"`` / ``"default"``）与 ``trim``（``true`` / ``{"padding":N,"threshold":N}``）取值合法。

检查项（[提示]，不影响退出码）：

- 同一 entry 内两块 rect 相互重叠（可能误切）；
- ``target`` 未被本目录任何 ``.tex`` 以 ``figs/<名>`` 引用；
- 应按规则生成 ``crop_compare/*_裁剪前后.png`` 的 recipe 目录尚未生成（多子图 / 去标签 /
  填白才需要；纯“去白边”不要求。该目录 Git 忽略）。

> 本脚本只做**结构、尺寸与文件头一致性**校验；**图片内容是否正确（多裁/少裁/残留标签/擦除越界）
> 仍须人工逐张打开 ``crop_compare/`` 对比图核对**。

用法::

    python3 tools/check_recrop.py                 # 默认检查 试卷/
    python3 tools/check_recrop.py 试卷/           # 指定根目录
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None  # type: ignore

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from recrop_figures import _crop_removes_ink  # 判定“仅去白边”还是“切到内容”
except Exception:  # pragma: no cover
    def _crop_removes_ink(source, rect):  # type: ignore
        return True

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ROOTS = ["试卷"]
IMG_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
# 扩展名 → 期望的文件头类型（用于发现“字节与扩展名不符”，如把 PNG 存成 .jpg）
SUFFIX_KIND = {".jpg": "jpeg", ".jpeg": "jpeg", ".png": "png",
               ".bmp": "bmp", ".tif": "tiff", ".tiff": "tiff"}
FIGS_REF_RE = re.compile(r"figs/([^}\s]+?)\.(?:jpg|jpeg|png)", re.I)


def _resolve(path_str: str) -> Path:
    p = Path(path_str)
    return p if p.is_absolute() else (ROOT / p)


def _image_size(path: Path) -> Optional[Tuple[int, int]]:
    if Image is None or not path.is_file():
        return None
    try:
        with Image.open(path) as im:
            return im.size  # (w, h)
    except Exception:
        return None


def _signature_kind(path: Path) -> Optional[str]:
    """按文件头判断真实图片类型（jpeg/png/bmp/tiff）；未知返回 None。"""
    try:
        with open(path, "rb") as fh:
            head = fh.read(12)
    except OSError:
        return None
    if head.startswith(b"\xff\xd8"):
        return "jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"BM"):
        return "bmp"
    if head[:4] in (b"II*\x00", b"MM\x00*"):
        return "tiff"
    return None


def _referenced_stems(directory: Path) -> set:
    """目录下所有 .tex 以 figs/<名> 引用的图片名（去扩展名）。"""
    stems = set()
    for tex in directory.glob("*.tex"):
        try:
            text = tex.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        stems |= {Path(m).stem for m in FIGS_REF_RE.findall(text)}
    return stems


def _overlap(a: List[int], b: List[int]) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return not (ax + aw <= bx or bx + bw <= ax or ay + ah <= by or by + bh <= ay)


def check_recipe(path: Path) -> Tuple[List[str], List[str]]:
    """校验单个 recipe，返回 (errors, warnings)。不依赖全局状态，便于测试。"""
    errors: List[str] = []
    warnings: List[str] = []
    rel = path.relative_to(ROOT) if str(path).startswith(str(ROOT)) else path

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{rel}: 无法解析 JSON（{exc}）"], []

    if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
        return [f"{rel}: 顶层应为含 entries 数组的对象"], []

    # trim：裁剪后自动去白边（target 尺寸会小于 rect，故放宽尺寸校验）
    trim = data.get("trim")
    trim_on = False
    if trim is not None:
        if isinstance(trim, bool):
            trim_on = trim
        elif isinstance(trim, dict):
            trim_on = True
            for k in ("padding", "threshold"):
                if k in trim and not isinstance(trim[k], (int, float)):
                    errors.append(f"{rel}: trim.{k} 应为数字: {trim[k]!r}")
        else:
            errors.append(f"{rel}: trim 应为布尔或对象: {trim!r}")

    directory = path.parent
    referenced = _referenced_stems(directory)
    seen_targets: Dict[str, str] = {}
    expect_compare = False  # 是否应生成 crop_compare（多块 / 填白 / 切到内容）

    for ei, ent in enumerate(data["entries"]):
        tag = f"{rel}: entries[{ei}]"
        if not isinstance(ent, dict):
            errors.append(f"{tag} 应为对象")
            continue

        src_str = ent.get("source")
        if not isinstance(src_str, str) or not src_str:
            errors.append(f"{tag} 缺少 source")
            continue
        src = _resolve(src_str)
        src_size = _image_size(src)
        if src_size is None:
            errors.append(f"{tag} source 不存在或非图片: {src_str}")

        # 该 entry 是否开启去白边（recipe 级或 entry 级）
        ent_trim = trim_on or bool(ent.get("trim"))

        # erase / erase_labels
        erase = ent.get("erase")
        if erase is not None:
            if not isinstance(erase, list):
                errors.append(f"{tag} erase 应为矩形数组")
            else:
                for r in erase:
                    if (not isinstance(r, list) or len(r) != 4
                            or not all(isinstance(v, (int, float)) for v in r)
                            or r[2] <= 0 or r[3] <= 0):
                        errors.append(f"{tag} erase 含非法矩形: {r}")
        if "erase_labels" in ent:
            el = ent["erase_labels"]
            if not (el is True or el in ("panels", "options", "default")):
                errors.append(f"{tag} erase_labels 取值非法: {el!r}"
                              "（应为 true/\"panels\"/\"options\"/\"default\"）")

        crops = ent.get("crops")
        if not isinstance(crops, list) or not crops:
            errors.append(f"{tag} 缺少 crops")
            continue

        # 该 entry 按新规则是否应生成 crop_compare：多块 / 填白 / 切到内容（非纯去白边）
        cmp_flag = ent.get("compare")
        if cmp_flag is True:
            expect_compare = True
        elif cmp_flag is None:
            if ent.get("erase") or ent.get("erase_labels") or len(crops) >= 2:
                expect_compare = True
            elif len(crops) == 1 and src_size is not None and isinstance(crops[0], dict) \
                    and isinstance(crops[0].get("rect"), list) and len(crops[0]["rect"]) == 4:
                if _crop_removes_ink(src, crops[0]["rect"]):
                    expect_compare = True

        rects_in_entry: List[List[int]] = []
        for ci, crop in enumerate(crops):
            ctag = f"{tag}.crops[{ci}]"
            if not isinstance(crop, dict):
                errors.append(f"{ctag} 应为对象")
                continue
            rect = crop.get("rect")
            if (not isinstance(rect, list) or len(rect) != 4
                    or not all(isinstance(v, (int, float)) for v in rect)):
                errors.append(f"{ctag} 的 rect 非法（应为 [x,y,w,h]）: {rect}")
            else:
                x, y, w, h = (int(v) for v in rect)
                if w <= 0 or h <= 0:
                    errors.append(f"{ctag} 的 rect 宽高须为正: {rect}")
                elif x < 0 or y < 0:
                    errors.append(f"{ctag} 的 rect 起点须非负: {rect}")
                elif src_size is not None and (x + w > src_size[0] or y + h > src_size[1]):
                    errors.append(f"{ctag} 的 rect 超出源图范围 "
                                  f"{src_size[0]}x{src_size[1]}: {rect}")
                else:
                    rects_in_entry.append(rect)
                    target = crop.get("target")
                    if not isinstance(target, str) or not target:
                        errors.append(f"{ctag} 缺少 target")
                        continue
                    tgt = _resolve(target)
                    if tgt.suffix.lower() not in IMG_SUFFIXES:
                        errors.append(f"{ctag} target 扩展名非图片: {target}")
                    if str(tgt) in seen_targets:
                        errors.append(f"{ctag} target 重复写入: {target}"
                                      f"（另见 {seen_targets[str(tgt)]}）")
                    else:
                        seen_targets[str(tgt)] = ctag
                    tgt_size = _image_size(tgt)
                    if tgt_size is None:
                        errors.append(f"{ctag} target 不存在或非图片（尚未 apply？）: {target}")
                    else:
                        expected = (min(w, src_size[0] - x) if src_size else w,
                                    min(h, src_size[1] - y) if src_size else h)
                        if ent_trim:
                            # 去白边只会缩小，故只要求 target 不大于 rect
                            if tgt_size[0] > expected[0] or tgt_size[1] > expected[1]:
                                errors.append(
                                    f"{ctag} target 尺寸 {tgt_size[0]}x{tgt_size[1]} "
                                    f"大于 rect 期望 {expected[0]}x{expected[1]}"
                                    "（trim 后不应变大；修改 recipe 后请重新 apply？）")
                        elif tgt_size != expected:
                            errors.append(
                                f"{ctag} target 尺寸 {tgt_size[0]}x{tgt_size[1]} "
                                f"与 rect 期望 {expected[0]}x{expected[1]} 不一致"
                                "（修改 recipe 后未重新 apply？）")
                        want_kind = SUFFIX_KIND.get(tgt.suffix.lower())
                        got_kind = _signature_kind(tgt)
                        if want_kind and got_kind and got_kind != want_kind:
                            errors.append(
                                f"{ctag} target 内容为 {got_kind} 但扩展名为 {tgt.suffix}"
                                f"（字节与扩展名不符，请用 recrop_figures.py apply 重新生成）: "
                                f"{target}")
                        if tgt.stem not in referenced:
                            warnings.append(f"{ctag} target 未被本目录 .tex 引用: {target}")

        # 同一 entry 内 rect 重叠
        for a in range(len(rects_in_entry)):
            for b in range(a + 1, len(rects_in_entry)):
                if _overlap(rects_in_entry[a], rects_in_entry[b]):
                    warnings.append(f"{tag} crops[{a}] 与 crops[{b}] 矩形重叠: "
                                    f"{rects_in_entry[a]} / {rects_in_entry[b]}")

    # crop_compare 是否已生成（仅当按规则确有需要时要求）
    if expect_compare:
        compare_dir = directory / "crop_compare"
        if not compare_dir.is_dir() or not list(compare_dir.glob("*_裁剪前后.png")):
            warnings.append(f"{rel}: 未发现 crop_compare/*_裁剪前后.png（可能尚未 apply；"
                            "该目录 Git 忽略）")

    return errors, warnings


def find_recipes(roots: List[Path]) -> List[Path]:
    out = []
    for root in roots:
        base = root if root.is_absolute() else ROOT / root
        if not base.is_dir():
            continue
        out += sorted(base.rglob(".recrop.json"))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="校验 .recrop.json 与 figs/ 的一致性")
    ap.add_argument("roots", nargs="*", help=f"根目录（默认 {' '.join(DEFAULT_ROOTS)}）")
    ap.add_argument("--quiet", action="store_true", help="只输出问题")
    args = ap.parse_args(argv)

    roots = [Path(r) for r in args.roots] or [Path(r) for r in DEFAULT_ROOTS]
    recipes = find_recipes(roots)
    if not recipes:
        if not args.quiet:
            print("未找到 .recrop.json（无内容可校验）。")
        return 0

    total_err = total_warn = 0
    for r in recipes:
        errors, warnings = check_recipe(r)
        total_err += len(errors)
        total_warn += len(warnings)
        if errors or (warnings and not args.quiet):
            rel = r.relative_to(ROOT) if str(r).startswith(str(ROOT)) else r
            print(f"--- {rel} ---")
            for e in errors:
                print(f"  [错误] {e}")
            for w in warnings:
                print(f"  [提示] {w}")

    if not args.quiet:
        print(f"\n校验完成：recipe {len(recipes)} 个，错误 {total_err}，提示 {total_warn}。")
        if total_err == 0:
            print("提示：本检查只验结构/尺寸/文件头，图片内容仍须逐张核对 crop_compare/ 对比图。")
    return 1 if total_err else 0


if __name__ == "__main__":
    sys.exit(main())

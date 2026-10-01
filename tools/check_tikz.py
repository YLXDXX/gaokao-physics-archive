#!/usr/bin/env python3
"""tools/check_tikz.py

校验各试卷目录下 ``TikZ/tikz_sources.json``（重绘 TikZ → 原图登记）
与本目录 ``.tex`` 引用、`TikZ/` 图片、``tikz_compare/`` 的一致性，供 ``make check`` 使用。

检查项（[错误] 使退出码为 1）：

1. 本目录 ``.tex`` 引用了 ``TikZ/<名>.pdf``，但缺少 ``TikZ/tikz_sources.json``；
2. ``tikz_sources.json`` 为合法 JSON，``entries`` 为数组，逐条含非空 ``tikz``、无重复；
3. 每条 ``original``：为 ``null``/空串表示**显式声明无原题图**（自编题等，允许）；
   否则须为非空字符串、非绝对路径，且**文件存在**；
4. ``.tex`` 引用的每张 TikZ 都已在 ``tikz_sources.json`` 登记（未登记即错误）。

检查项（[提示]，不影响退出码）：

- ``tikz_sources.json`` 中登记了但本目录任何 ``.tex`` 都未引用的 TikZ（可删除）；
- 已登记原图的 TikZ，其 ``TikZ/<名>.pdf`` 尚未编译；
- 有“已登记原图”的 TikZ，但尚未生成 ``tikz_compare/*_重绘前后.png``（该目录 Git 忽略）。

> 本脚本只做**结构与存在性**校验；**重绘是否忠实于原图（形状/方向/标注/比例）
> 仍须人工逐张打开 ``tikz_compare/`` 对比图核对**。

用法::

    python3 tools/check_tikz.py                 # 默认检查 试卷/
    python3 tools/check_tikz.py 试卷/           # 指定根目录
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ROOTS = ["试卷"]
TIKZ_REF_RE = re.compile(r"TikZ/([A-Za-z0-9_\-]+)\.pdf")
OUT_DIRNAME = "tikz_compare"


def referenced_tikz(tex: Path) -> List[str]:
    """按出现顺序返回文档中引用的 TikZ 名（去重）。"""
    names: List[str] = []
    try:
        text = tex.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return names
    for m in TIKZ_REF_RE.finditer(text):
        n = m.group(1)
        if n not in names:
            names.append(n)
    return names


def _lesson_refs(directory: Path) -> List[str]:
    names: List[str] = []
    for tex in sorted(directory.glob("*.tex")):
        for n in referenced_tikz(tex):
            if n not in names:
                names.append(n)
    return names


def check_lesson(directory: Path, root: Path = ROOT) -> Tuple[List[str], List[str], int]:
    """校验单个目录，返回 (errors, warnings, 已登记原图条数)。不依赖全局状态，便于测试。

    ``root`` 为解析 ``original`` 相对路径所依据的项目根（默认项目根，测试可传入临时根）。
    """
    errors: List[str] = []
    warnings: List[str] = []
    rel = directory.relative_to(root) if str(directory).startswith(str(root)) else directory

    referenced = _lesson_refs(directory)
    mapping_path = directory / "TikZ" / "tikz_sources.json"
    if not referenced:
        # 无 TikZ 引用：若有登记文件，提示未使用；否则跳过。
        if mapping_path.exists():
            try:
                data = json.loads(mapping_path.read_text(encoding="utf-8"))
                for e in data.get("entries", []):
                    t = str(e.get("tikz", "")).strip()
                    if t:
                        warnings.append(f"{rel}: 未在任何 .tex 中引用 TikZ/{t}.pdf（可删除该登记）")
            except Exception:
                pass
        return errors, warnings, 0

    if not mapping_path.exists():
        errors.append(f"{rel}: 本目录 .tex 引用了 TikZ（{', '.join(referenced)}），"
                      f"但缺少 {mapping_path.relative_to(ROOT) if str(mapping_path).startswith(str(ROOT)) else mapping_path}")
        return errors, warnings, 0

    try:
        data = json.loads(mapping_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{rel}/TikZ/tikz_sources.json: 无法解析 JSON（{exc}）")
        return errors, warnings, 0

    if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
        errors.append(f"{rel}/TikZ/tikz_sources.json: 顶层应为含 entries 数组的对象")
        return errors, warnings, 0

    registered: Dict[str, dict] = {}
    for ei, ent in enumerate(data["entries"]):
        tag = f"{rel}/TikZ/tikz_sources.json: entries[{ei}]"
        if not isinstance(ent, dict):
            errors.append(f"{tag} 应为对象")
            continue
        tikz = str(ent.get("tikz", "")).strip()
        if not tikz:
            errors.append(f"{tag} 缺少 tikz")
            continue
        if tikz in registered:
            errors.append(f"{tag} tikz 重复: {tikz}")
            continue
        registered[tikz] = ent

    have_original = 0
    for tikz, ent in registered.items():
        original = ent.get("original")
        if original is None or (isinstance(original, str) and not original.strip()):
            # 显式声明“无原题图”（自编题等），允许。
            continue
        if not isinstance(original, str):
            errors.append(f"{rel}: {tikz} 的 original 应为字符串路径或 null")
            continue
        op = Path(original)
        if op.is_absolute():
            errors.append(f"{rel}: {tikz} 的 original 应为相对项目根的路径：{original}")
            continue
        if not (root / original).exists():
            errors.append(f"{rel}: {tikz} 的 original 不存在：{original}")
            continue
        have_original += 1
        if not (directory / "TikZ" / f"{tikz}.pdf").exists():
            warnings.append(f"{rel}: {tikz}.pdf 尚未编译（make tikz）")

    # 未登记的引用 = 错误
    for t in referenced:
        if t not in registered:
            errors.append(f"{rel}: 引用 TikZ/{t}.pdf 但未在 tikz_sources.json 登记"
                          "（自编题等无原图者请登记 original: null）")
    # 登记了但未引用 = 提示
    for t in registered:
        if t not in referenced:
            warnings.append(f"{rel}: 未在任何 .tex 中引用 TikZ/{t}.pdf（可删除该登记）")

    # 已登记原图却未生成对比图 = 提示
    if have_original:
        cmp_dir = directory / OUT_DIRNAME
        if not cmp_dir.is_dir() or not list(cmp_dir.glob("*_重绘前后.png")):
            warnings.append(f"{rel}: 尚未生成 {OUT_DIRNAME}/*_重绘前后.png"
                            "（可运行 make tikz-compare；该目录 Git 忽略）")
    return errors, warnings, have_original


def find_lessons(roots: List[Path]) -> List[Path]:
    out = set()
    for root in roots:
        base = root if root.is_absolute() else ROOT / root
        if not base.is_dir():
            continue
        for tex in base.rglob("*.tex"):
            d = tex.parent
            if d.name == "TikZ":
                continue
            if (d / "TikZ").is_dir():
                out.add(d)
    return sorted(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="校验 tikz_sources.json 与 TikZ 引用/原图的一致性")
    ap.add_argument("roots", nargs="*", help=f"根目录（默认 {' '.join(DEFAULT_ROOTS)}）")
    ap.add_argument("--quiet", action="store_true", help="只输出问题")
    args = ap.parse_args(argv)

    roots = [Path(r) for r in args.roots] or [Path(r) for r in DEFAULT_ROOTS]
    lessons = find_lessons(roots)

    total_err = total_warn = total_orig = 0
    checked = 0
    for d in lessons:
        referenced = _lesson_refs(d)
        mapping_exists = (d / "TikZ" / "tikz_sources.json").exists()
        if not referenced and not mapping_exists:
            continue
        checked += 1
        errors, warnings, n_orig = check_lesson(d)
        total_err += len(errors)
        total_warn += len(warnings)
        total_orig += n_orig
        if errors or (warnings and not args.quiet):
            rel = d.relative_to(ROOT) if str(d).startswith(str(ROOT)) else d
            print(f"--- {rel} ---")
            for e in errors:
                print(f"  [错误] {e}")
            for w in warnings:
                print(f"  [提示] {w}")

    if not args.quiet:
        print(f"\n校验完成：目录 {checked} 个，已登记原图 {total_orig} 张，"
              f"错误 {total_err}，提示 {total_warn}。")
        if total_err == 0:
            print("提示：本检查只验结构/存在性，重绘是否忠实于原图仍须逐张核对 "
                  "tikz_compare/ 对比图。")
    return 1 if total_err else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""tools/tex_links.py

在**试卷/<年份>/<地区>/ 的 TeX 工作目录**中，创建指向项目根目录公共文件的
**相对软链接**。这样：

- 公共样式（`gaokaozhenti.cls`、`PhyUnit.sty`、`ChoiceQuestion.sty`、`package/`）
  只在根目录维护一份；
- 用 TeXStudio 等编辑器打开某卷的 `.tex` 时，无需手动复制公共文件、也无需设置
  `TEXINPUTS`，即可直接编译；
- 根目录的公共文件更新后，各工作目录**读到的即是最新文件**（软链接自动指向）；
- 若工作目录下存在 `TikZ/` 子目录（独立 TikZ 图片文档），**一并为其建立**
  `PhyUnit.sty` 的相对软链接，使 `TikZ/*.tex` 也能用 TeXStudio 直接编译。

用法::

    python3 tools/tex_links.py                 # 扫描并处理 试卷/*/*/
    python3 tools/tex_links.py 试卷/2025/湖北    # 只处理指定目录（可多个）
    python3 tools/tex_links.py --dry-run       # 只预览，不实际创建

说明：软链接为**相对路径**（如试卷目录中 `../../../gaokaozhenti.cls`），可随仓库迁移；
已存在的**真实文件**不会被覆盖（仅提示），已存在的正确软链接会被跳过，错误指向的
软链接会被更正。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 试卷工作目录所需的公共文件（相对项目根）
COMMON = ["gaokaozhenti.cls", "PhyUnit.sty", "ChoiceQuestion.sty", "package"]
# TikZ/ 子目录中的独立图片文档所需的公共文件
TIKZ = ["PhyUnit.sty"]


def link_one(directory: Path, name: str, *, dry_run: bool) -> str:
    target = ROOT / name
    link = directory / name
    if not target.exists():
        return f"  跳过 {name}（根目录不存在）"
    rel = os.path.relpath(target, directory)

    if link.is_symlink():
        if os.readlink(link) == rel:
            return f"  已存在 {name} -> {rel}"
        if not dry_run:
            link.unlink()
            link.symlink_to(rel)
        return f"  更正 {name} -> {rel}"
    if link.exists():
        return f"  跳过 {name}（已存在同名真实文件，未覆盖）"
    if not dry_run:
        link.symlink_to(rel)
    return f"  新建 {name} -> {rel}"


def process(directory: Path, *, dry_run: bool) -> None:
    directory = directory.resolve()
    if not directory.is_dir():
        print(f"[跳过] {directory}（不是目录）")
        return
    print(f"[试卷] {directory}")
    for name in COMMON:
        print(link_one(directory, name, dry_run=dry_run))
    tikz_dir = directory / "TikZ"
    if tikz_dir.is_dir():
        print(f"  [TikZ] {tikz_dir}")
        for name in TIKZ:
            print(link_one(tikz_dir, name, dry_run=dry_run))


def default_dirs() -> list[Path]:
    """发现所有试卷目录：试卷/<年份>/<地区>/（含 .tex 者）。"""
    dirs: list[Path] = []
    base = ROOT / "试卷"
    if not base.is_dir():
        return dirs
    for d in sorted(base.rglob("*")):
        if (
            d.is_dir()
            and d.name != "TikZ"
            and any(f.suffix == ".tex" for f in d.iterdir() if f.is_file())
        ):
            dirs.append(d)
    return dirs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="为试卷 TeX 工作目录创建公共文件的相对软链接")
    ap.add_argument("dirs", nargs="*", type=Path, help="工作目录；缺省扫描 试卷/*/*/")
    ap.add_argument("--dry-run", action="store_true", help="只预览，不创建")
    args = ap.parse_args(argv)

    targets = [Path(d) for d in args.dirs] if args.dirs else default_dirs()
    if not targets:
        print("未找到任何试卷目录。")
        return 0
    for d in targets:
        process(d, dry_run=args.dry_run)
    print(f"完成：共处理 {len(targets)} 个目录" + ("（dry-run）" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())

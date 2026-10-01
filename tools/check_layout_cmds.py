#!/usr/bin/env python3
"""tools/check_layout_cmds.py —— 版面微调命令自查。

学生版 / 教师版两版文档的纯版面微调（断页 / 撑开 / 留白）应使用 `gaokaozhenti.cls`
提供的**公用命令**（在**学生版**执行、**教师版自动隐藏**）：

    \\gknewpage（← \\newpage）   \\gkvfill（← \\vfill）   \\gkvfil（← \\vfil）
    \\gkhfill（← \\hfill）        \\gkhfil（← \\hfil）

直接使用原生命令会在教师版留下大段空白或错位（教师版含答案与详解、版面本就不同）。
详见 `LaTeX_format_ReadMe.md` 第 34 条。

例外：
    * 并排两个 `minipage` 之间的 `\\hfill` 属**版面结构**，仍用原生 `\\hfill`，不在禁止
      之列（本脚本用 `(?![A-Za-z])` 只命中 `\\hfil`，不会误伤 `\\hfill`）；
    * `TikZ/` 下的独立图片文档不参与检查。

用法::

    python3 tools/check_layout_cmds.py 试卷/2025/湖北/湖北.tex
    python3 tools/check_layout_cmds.py 试卷/2025/湖北      # 目录（含 *.tex）
    python3 tools/check_layout_cmds.py                     # 默认扫描 试卷/*/*/*.tex

退出码：0 表示未发现问题；1 表示发现原生版面命令。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 原生命令 -> 应改用的公用命令
RAW_TO_PUBLIC = {
    "newpage": "\\gknewpage",
    "clearpage": "\\gknewpage",
    "vfill": "\\gkvfill",
    "vfil": "\\gkvfil",
    "hfil": "\\gkhfil",
}
# 负向断言 (?![A-Za-z])：\hfill 中的 \hfil 后紧跟 l、\vfilneg 等不命中
RAW_RE = re.compile(r"\\(newpage|clearpage|vfill|vfil|hfil)(?![A-Za-z])")
COMMENT_RE = re.compile(r"(?<!\\)%.*$")


def strip_comment(line: str) -> str:
    return COMMENT_RE.sub("", line)


def collect_tex(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for p in paths:
        if p.is_dir():
            for f in sorted(p.rglob("*.tex")):
                if "TikZ" in f.parts:  # 独立 TikZ 图片文档不参与检查
                    continue
                files.append(f)
        elif p.suffix == ".tex":
            files.append(p)
    return files


def scan(path: Path) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        for m in RAW_RE.finditer(strip_comment(raw)):
            hits.append((lineno, m.group(1)))
    return hits


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="版面微调命令自查（禁止原生断页/撑开命令）")
    ap.add_argument("paths", nargs="*", type=Path,
                    help=".tex 文件或目录；缺省扫描 试卷/*/*/*.tex")
    args = ap.parse_args(argv)

    files = collect_tex(args.paths) if args.paths else collect_tex([ROOT / "试卷"])

    total = 0
    for f in files:
        for lineno, name in scan(f):
            try:
                shown = f.relative_to(ROOT)
            except ValueError:
                shown = f
            print(f"[错误] {shown}:{lineno} 使用了原生 \\{name}，"
                  f"请改用公用命令 {RAW_TO_PUBLIC[name]}（见 LaTeX_format_ReadMe.md 第 34 条）")
            total += 1

    if total:
        print(f"\n结果：{total} 处原生版面命令 ❌")
        return 1
    print("结果：未发现原生版面命令 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())

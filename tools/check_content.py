#!/usr/bin/env python3
"""tools/check_content.py —— 高考真题 LaTeX 文档内容规范检查（lint）。

配合 `tools/check_paper.py`（结构/元数据/图片/答案）使用，本脚本聚焦**内容书写**
的共性问题，规则对应 `LaTeX_format_ReadMe.md`。

错误项（使退出码为 1）：
  1. 物理单位必须使用 PhyUnit 宏（如 \\Ums / \\Umsq / \\Ukmh），禁止裸写 m/s、km/h 等；
  2. 禁止用图片充当公式（\\includegraphics / \\includesvg 出现在数学模式内）。

提示项（仅警告，不影响退出码）：
  3. 编号条目 / 段落疑似未分行（上一行为文字或 `\\textbf` 条目、下一行以 `\\textbf{`
     开头，且上一行末尾无空行 / `\\par`）——见 `LaTeX_format_ReadMe.md` 第 32 条；
  4. 中文之间出现半角标点；中英文之间可能缺少空格（xeCJK 会自动加空，仅提示）。

用法::

    python3 tools/check_content.py 试卷/2025/湖北/湖北.tex
    python3 tools/check_content.py 试卷/2025/湖北      # 目录（含 *.tex）
    python3 tools/check_content.py                     # 默认扫描 试卷/*/*/*.tex
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CJK = r"\u4e00-\u9fff"
UNIT_RE = re.compile(r"(?<![\\A-Za-z])(?:m/s(?:\^?2|²)?|km/h|m/s²)")
MATH_ENV_RE = re.compile(
    r"\\begin\{(equation|align|gather|multline|eqnarray)\*?\}.*?\\end\{\1\*?\}",
    re.S,
)
PICTURE_RE = re.compile(r"\\(?:includegraphics|includesvg)(?![A-Za-z])")
PUNCT_RE = re.compile(rf"[{CJK}][,;:()][{CJK}]")
CJK_LATIN_RE = re.compile(rf"[{CJK}][A-Za-z]|[A-Za-z][{CJK}]")
PARA_BOLD_RE = re.compile(r"^\\textbf\{")


def strip_comment(line: str) -> str:
    return re.sub(r"(?<!\\)%.*$", "", line)


def collect_tex(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for p in paths:
        if p.is_dir():
            for f in sorted(p.rglob("*.tex")):
                if "TikZ" in f.parts:  # 独立 TikZ 图片文档另由 check_tikz.py 校验
                    continue
                files.append(f)
        elif p.suffix == ".tex":
            files.append(p)
    return files


def check_units(name: str, text: str, errors: list) -> None:
    for i, raw in enumerate(text.splitlines(), 1):
        for m in UNIT_RE.finditer(strip_comment(raw)):
            errors.append(
                f"{name}:{i} 裸单位“{m.group(0)}”，请改用 PhyUnit（如 \\Ums/\\Umsq/\\Ukmh）"
            )


def check_image_formula(name: str, text: str, errors: list) -> None:
    for i, raw in enumerate(text.splitlines(), 1):
        line = strip_comment(raw)
        for m in PICTURE_RE.finditer(line):
            if line[: m.start()].count("$") % 2 == 1:
                errors.append(f"{name}:{i} 图片出现在行内数学模式中，禁止用图片充当公式")
    for m in MATH_ENV_RE.finditer(text):
        if PICTURE_RE.search(m.group(0)):
            errors.append(f"{name} 数学环境 {m.group(1)} 内出现图片，禁止用图片充当公式")


def check_paragraph_breaks(name: str, text: str, warnings: list) -> None:
    lines = text.split("\n")
    for i in range(1, len(lines)):
        prev = strip_comment(lines[i - 1]).rstrip()
        nxt = lines[i]
        if not PARA_BOLD_RE.match(nxt.lstrip()):
            continue
        if not prev or prev.endswith("\\par") or prev.endswith("\\\\"):
            continue
        head = prev.lstrip()
        if head.startswith("\\") and not head.startswith("\\textbf"):
            continue
        if not re.search(rf"[{CJK}]", prev):
            continue
        warnings.append(
            f"{name}:{i + 1} 编号条目“{nxt.strip()[:20]}…”疑似未分行（上一行末尾请加空行或 \\par）"
        )


def check_style(name: str, text: str, warnings: list) -> None:
    for i, raw in enumerate(text.splitlines(), 1):
        line = strip_comment(raw)
        if PUNCT_RE.search(line):
            warnings.append(f"{name}:{i} 中文之间出现半角标点")
        if "$" not in line and CJK_LATIN_RE.search(line):
            warnings.append(f"{name}:{i} 中英文之间可能缺少空格")


def check_one(path: Path) -> tuple[list[str], list[str]]:
    text = path.read_text(encoding="utf-8")
    name = path.name
    errors: list[str] = []
    warnings: list[str] = []
    check_units(name, text, errors)
    check_image_formula(name, text, errors)
    check_paragraph_breaks(name, text, warnings)
    check_style(name, text, warnings)
    return errors, warnings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="高考真题 LaTeX 文档内容规范检查")
    ap.add_argument("paths", nargs="*", type=Path,
                    help=".tex 文件或目录；缺省扫描 试卷/*/*/*.tex")
    args = ap.parse_args(argv)

    files = collect_tex(args.paths) if args.paths else collect_tex([ROOT / "试卷"])

    total_err = total_warn = 0
    for f in files:
        errors, warnings = check_one(f)
        for w in warnings:
            print(f"[提示] {w}")
        for e in errors:
            print(f"[错误] {e}")
        total_err += len(errors)
        total_warn += len(warnings)

    if total_err:
        print(f"\n结果：{total_err} 处错误，{total_warn} 处提示 ❌")
        return 1
    print(f"\n结果：无错误，{total_warn} 处提示 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""tools/check_paper.py —— 高考真题 LaTeX 文档规范自查

用法::

    python3 tools/check_paper.py 试卷/2025/湖北/湖北.tex
    python3 tools/check_paper.py 试卷/2025/湖北       # 目录（含 *.tex）
    python3 tools/check_paper.py                      # 默认扫描 试卷/*/*/*.tex

检查项：

1. 文档骨架：``\\documentclass{gaokaozhenti}``、``\\begin{document}``、``\\end{document}``、
   且含 ``\\chapter{...}``；
2. 图片命令：必须使用 ChoiceQuestion 的图片命令，禁止旧式 ``figure`` / ``subfigure`` /
   ``\\subref`` / ``pic/`` / ``tikz/``；
3. 元数据块：每个顶层 ``\\item`` 之后紧跟 12 项固定顺序的 ``%% 字段:`` 注释；
4. 引用标签：``label=YYYY地区QQx`` / ``\\label{...}`` 形如 ``2025湖北10b``，且 ``\\ref``
   都能在本文档找到对应标签；
5. 图片可寻：引用的 ``figs/…``、``TikZ/…`` 文件确实存在；
6. 答案：每题至少含 ``\\xzanswer`` / ``\\tkanswer`` / ``\\jdanswer`` 之一。

退出码 0 表示通过，1 表示存在错误。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 每题元数据字段的固定顺序（body/answer/memo 为段首标记）
FIELDS = [
    "number", "paperName", "typeId", "type", "chapter", "point",
    "method", "score", "degree", "duplicateId", "body", "answer", "memo",
]
LABEL_RE = re.compile(r"^20\d{2}.+\d{2}[a-z]?$")
IMG_REF_RE = re.compile(r"(figs/[A-Za-z0-9_\-]+|TikZ/[A-Za-z0-9_\-]+)")


def collect_tex(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for p in paths:
        if p.is_dir():
            for f in sorted(p.rglob("*.tex")):
                if "TikZ" in f.parts:  # TikZ 独立图片文档另由 tools/check_tikz.py 校验
                    continue
                files.append(f)
        elif p.suffix == ".tex":
            files.append(p)
    return files


def check_one(path: Path) -> list[str]:
    errs: list[str] = []
    base = path.parent
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    # 1. 文档骨架（两版写法：\documentclass[\gkver]{gaokaozhenti}）
    if not re.search(r"\\documentclass(?:\[[^\]]*\])?\{gaokaozhenti\}", text):
        errs.append("缺少 \\documentclass[\\gkver]{gaokaozhenti}")
    if "\\gkver" not in text:
        errs.append(
            "缺少版本开关 \\gkver（源文件顶部应为 "
            "\\ifdefined\\gkver\\else\\def\\gkver{student}\\fi）"
        )
    if "\\begin{document}" not in text:
        errs.append("缺少 \\begin{document}")
    if "\\end{document}" not in text:
        errs.append("缺少 \\end{document}")
    if not re.search(r"\\chapter\{", text):
        errs.append("缺少 \\chapter{...} 章标题")

    # 2. 旧式图片命令
    for pat, msg in [
        (r"\\begin\{figure\}", "禁止 \\begin{figure}，请用 ChoiceQuestion 图片命令"),
        (r"\\begin\{subfigure\}", "禁止 subfigure，请用 ChoiceQuestion 图片命令"),
        (r"\\subref", "禁止 \\subref，请用 \\ref（ChoiceQuestion label）"),
        (r"(?<![A-Za-z0-9_/])pic/", "出现旧路径 pic/，应使用 figs/"),
        (r"(?<![A-Za-z0-9_/])tikz/", "出现旧路径 tikz/，应使用 TikZ/"),
    ]:
        if re.search(pat, text):
            errs.append(msg)

    # 3. 逐题元数据块（以 %% number: 定位，到下一个 %% number: 之间）
    qstarts = [i for i, ln in enumerate(lines) if re.match(r"^%%\s*number\s*[:：]", ln)]
    if not qstarts:
        errs.append("未找到任何 %% number: 元数据块")
    for n, pos in enumerate(qstarts):
        end = qstarts[n + 1] if n + 1 < len(qstarts) else len(lines)
        keys: list[str] = []
        for j in range(pos, end):
            m = re.match(r"^%%\s*([A-Za-z]+)\s*[:：]", lines[j])
            if m:
                keys.append(m.group(1))
        if keys != FIELDS:
            errs.append(
                f"第 {pos + 1} 行题目元数据字段缺失或顺序异常：{keys}；应为 {FIELDS}"
            )
        # 基本详解：每题必须至少有 \memoanswer{...}（作者注解 \memoanswer[作者]{} 不算）
        block_text = "\n".join(lines[pos:end])
        qnum = re.search(r"number\s*[:：]\s*(\d+)", lines[pos]).group(1)
        has_basic = re.search(r"\\memoanswer\s*\{", block_text) is not None
        has_author = re.search(r"\\memoanswer\s*\[", block_text) is not None
        if not has_basic:
            if has_author:
                errs.append(
                    f"第 {qnum} 题只有作者注解 \\memoanswer[…]{{}}，缺少基本详解 \\memoanswer{{}}"
                )
            else:
                errs.append(f"第 {qnum} 题缺少详解 \\memoanswer{{}}")

    # 4. 标签（仅取图片命令选项里的 label/labelA..labelI 与 \label{}）
    PIC_CMD_RE = re.compile(
        r"\\(?:one|two|three|four|five|six|seven|eight|nine)picture\s*\[([^\]]*)\]"
    )
    defined: set[str] = set()
    for m in PIC_CMD_RE.finditer(text):
        for lab in re.findall(r"(?<![A-Za-z])label[A-I]?=([^\s,}\]]+)", m.group(1)):
            defined.add(lab)
    defined |= set(re.findall(r"\\label\{([^}]+)\}", text))
    for lab in defined:
        if not LABEL_RE.match(lab):
            errs.append(f"引用标签 {lab!r} 不符合 YYYY地区QQx 规范")
    for ref in set(re.findall(r"\\ref\{([^}]+)\}", text)):
        if ref not in defined:
            errs.append(f"\\ref{{{ref}}} 在本文档中找不到对应 label")

    # 5. 图片文件存在
    def resolve(rel: str) -> bool:
        p = base / rel
        if p.exists():
            return True
        for ext in (".svg", ".png", ".jpg", ".jpeg", ".pdf"):
            if p.with_suffix(ext).exists():
                return True
        return False

    for rel in set(IMG_REF_RE.findall(text)):
        if not resolve(rel):
            errs.append(f"图片引用 {rel} 找不到对应文件")

    # 6. 答案
    if qstarts and not re.search(r"\\xzanswer|\\tkanswer|\\jdanswer", text):
        errs.append("题目中缺少答案命令（\\xzanswer/\\tkanswer/\\jdanswer）")

    return errs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="高考真题 LaTeX 文档规范自查")
    ap.add_argument("paths", nargs="*", type=Path,
                    help=".tex 文件或目录；缺省扫描 试卷/*/*/*.tex")
    args = ap.parse_args(argv)

    if args.paths:
        files = collect_tex(args.paths)
    else:
        files = collect_tex([ROOT / "试卷"])

    total_err = 0
    for f in files:
        errs = check_one(f)
        if errs:
            total_err += len(errs)
            print(f"[错误] {f}")
            for e in errs:
                print(f"    - {e}")
        else:
            print(f"[通过] {f}")
    if total_err:
        print(f"\n共发现 {total_err} 处问题。")
        return 1
    print(f"\n共检查 {len(files)} 个文件，全部通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

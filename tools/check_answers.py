#!/usr/bin/env python3
"""tools/check_answers.py —— 非选择题答案与“小问一一对应”检查

`check_paper.py` 只要求“全文至少有一处答案命令”，`check_review.py` 只比对选择题答案。
本脚本补上**非选择题**：

1. 非选择题必须给出答案：至少含 `\\jdanswer`（多小问/计算）或 `\\tkanswer`（填空）；
2. **计算题 / 解答题**：题面小问数与 `\\jdanswer` 的 `enumerate` 项数一致（不一致给提示）；
3. 题面有 2 个及以上小问时，必须有 `\\jdanswer`（仅有 `\\tkanswer` 视为缺失）。

**实验题**（`typeId=4`）：题干 `enumerate` 中常含实验步骤、选项等**无需作答**的项，答案可在
`\\jdanswer{}` 内手动编号、不套 `enumerate`，故只要求有答案命令、**不做项数比对**。

小问数按“题干区（`%% body:` 到 `%% answer:`）中嵌套 `\\item` 数”估算，`steps` 环境不计入。

用法::

    python3 tools/check_answers.py 试卷/2000/上海/上海.tex
    python3 tools/check_answers.py 试卷/

退出码：0 通过；1 存在错误。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
CHOICE_IDS = {1, 2}


def collect_tex(paths: List[Path]) -> List[Path]:
    files: List[Path] = []
    for p in paths:
        if p.is_dir():
            for f in sorted(p.rglob("*.tex")):
                if "TikZ" not in f.parts:
                    files.append(f)
        elif p.suffix == ".tex":
            files.append(p)
    return files


def _count_items(text: str) -> int:
    """统计**最外层 enumerate** 的 `\\item` 数（即小问数）。

    排除 steps / itemize / description 等非小问列表；并按 `enumerate` 嵌套
    深度只取最浅一层的 `\\item`，避免把子-子列表的项也算成小问（旧实现用
    `re.findall(r"\\item")` 会重复计数）。
    """
    text = re.sub(
        r"\\begin\{(steps|itemize|description)\}.*?\\end\{\1\}", "", text, flags=re.S)
    depth = 0
    counts: Dict[int, int] = {}
    for tok in re.finditer(r"\\begin\{enumerate\}|\\end\{enumerate\}|\\item\b", text):
        t = tok.group(0)
        if t.startswith("\\begin"):
            depth += 1
        elif t.startswith("\\end"):
            depth = max(0, depth - 1)
        elif depth >= 1:  # 只统计 enumerate 内的 \item
            counts[depth] = counts.get(depth, 0) + 1
    if not counts:
        return 0
    return counts[min(counts)]


def check_file(tex: Path) -> Tuple[List[str], List[str]]:
    errs: List[str] = []
    warns: List[str] = []
    text = tex.read_text(encoding="utf-8")
    for block in re.split(r"(?=^%%\s*number\s*[:：])", text, flags=re.M):
        m = re.match(r"%%\s*number\s*[:：]\s*(\d+)", block)
        if not m:
            continue
        n = int(m.group(1))
        tm = re.search(r"%%\s*typeId\s*[:：]\s*(\d+)", block)
        type_id = int(tm.group(1)) if tm else None
        if type_id in CHOICE_IDS:
            continue
        a = block.find("%% answer:")
        mi = block.find("%% memo")
        body = block[block.find("%% body:"):a] if a >= 0 else block
        ans = block[a:mi] if (a >= 0 and mi >= 0) else (block[a:] if a >= 0 else "")
        subq = _count_items(body)
        has_jd = "\\jdanswer" in ans
        has_tk = "\\tkanswer" in block
        if not has_jd and not has_tk:
            errs.append(f"{tex.name}: 第 {n} 题非选择题缺答案命令（\\jdanswer/\\tkanswer）")
            continue
        if subq >= 2 and not has_jd:
            errs.append(f"{tex.name}: 第 {n} 题有 {subq} 个小问，但缺 \\jdanswer")
        if has_jd:
            jdm = re.search(r"\\jdanswer\*?\s*\{(.*?)\n\}", ans, flags=re.S)
            jitems = _count_items(jdm.group(1)) if jdm else 0
            # 实验题（typeId=4）题干常混入实验步骤/选项等无需作答项，答案可手动编号，
            # 故不做项数比对；计算题（typeId=6 等）仍比对。
            # 仅当题干只有一个 enumerate（视为唯一小问列表）时才比对项数，
            # 避免把“实验步骤写成 enumerate”等多列表情况误报。
            n_env = len(re.findall(r"\\begin\{enumerate\}", body))
            if type_id != 4 and n_env == 1 and subq and jitems and jitems != subq:
                warns.append(f"{tex.name}: 第 {n} 题小问数 {subq} 与 \\jdanswer 项数 {jitems} 不一致")
    return errs, warns


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="非选择题答案与小问对应检查")
    ap.add_argument("paths", nargs="*", type=Path, help=".tex 文件或目录；缺省 试卷/")
    args = ap.parse_args(argv)
    files = collect_tex(args.paths) if args.paths else collect_tex([ROOT / "试卷"])
    total_err = total_warn = 0
    for f in files:
        errs, warns = check_file(f)
        for w in warns:
            print(f"[提示] {w}")
            total_warn += 1
        if errs:
            total_err += len(errs)
            print(f"[错误] {f}")
            for e in errs:
                print(f"    - {e}")
        else:
            print(f"[通过] {f}")
    if total_err:
        print(f"\n共发现 {total_err} 处问题（{total_warn} 处提示）。")
        return 1
    print(f"\n共检查 {len(files)} 个文件，全部通过（{total_warn} 处提示）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

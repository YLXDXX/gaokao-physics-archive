#!/usr/bin/env python3
"""tools/check_formula_numbers.py —— 解析中公式编号（①②③…）检查。

各卷 `\\memoanswer` 详解里常用带圈数字 ①②③… 标注公式编号，并出现
“由①式”“联立①②”之类引用。常见问题：

1. **缺号**：编号不连续（如出现 ①②③⑤ 而缺 ④）——通常是 OCR 漏抄或改错；
2. **悬空引用**：某编号只在“由③式”处出现一次（被引用但未给出编号公式）。

本脚本逐题检查，规则：

- 取每道题 `%% memo:` 之后的内容为解析文本；
- 只识别**公式编号**（过滤“①过程”“图象为②”“（2）①从…”等过程名/图号/小问标签；
  公式编号的特征是后跟句读/行尾，或整串后跟“式”，或位于 `\tag{①}`）；
- 收集公式编号（①–⑳）；要求其**从 ① 起连续**（1..max 无缺号）→ [错误]；
- 若某编号在全文中仅出现一次、且紧邻“由/、/和/及/联 …式”等引用语 → [提示]
  （可能只引用未定义）。

> 不处理“（11）（12）”这类 10 以上的全角括号编号（各卷约定不一），只查带圈数字。

用法::

    python3 tools/check_formula_numbers.py 试卷/2008/上海/上海.tex
    python3 tools/check_formula_numbers.py 试卷/2008

退出码：0 无错误；1 存在缺号等错误。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).resolve().parent.parent
CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
IDX = {c: i + 1 for i, c in enumerate(CIRCLED)}


def _is_formula_number(memo: str, i: int) -> bool:
    """判断位置 i 的圈号是否为**公式编号**（而非过程名/图号/小问标签）。

    公式编号的特征：后面跟句读或行尾（`$…$ ④。`），或整串后跟“式”（引用，
    如“联立①②式”）；反例：“①过程”（阶段名）、“图象为②”（图号）、
    “（2）①从…”（小问标签）后面紧跟汉字。
    """
    # 引用：跳过一个连续圈号串后紧跟“式”
    k = i
    while k + 1 < len(memo) and memo[k + 1] in IDX:
        k += 1
    if memo[k + 1:k + 2] == "式":
        return True
    # 图/选项编号：前面是 图象/选项/为/示/是
    if re.search(r"[图象选项为示是]$", memo[max(0, i - 3):i]):
        return False
    after = memo[i + 1] if i + 1 < len(memo) else ""
    # \tag{①} 形式的编号
    j = i - 1
    while j >= 0 and memo[j] in " \t\n":
        j -= 1
    if j >= 0 and memo[j] == "{" and after == "}":
        return True
    return after in "，。；、,;:.）)" or after in ("", "\n", " ")


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


def check_text(text: str) -> Tuple[List[str], List[str]]:
    """返回 (errors, warnings)（不含文件名）。"""
    errs: List[str] = []
    warns: List[str] = []
    for block in re.split(r"(?=^%%\s*number\s*[:：])", text, flags=re.M):
        m = re.match(r"%%\s*number\s*[:：]\s*(\d+)", block)
        if not m:
            continue
        n = int(m.group(1))
        mi = block.find("%% memo")
        if mi < 0:
            continue
        memo = block[mi:]
        # 圈号有四种用途：公式编号 / 过程或阶段名(①过程) / 图片选项(图象为②) /
        # 小问条目标签(（2）①从…)。只保留**公式编号**：其后（跳过一个连续圈号串）
        # 紧跟“式”（引用），或紧跟在数学/右括号/花括号之后（定义）。
        chars = list(memo)
        for i, ch in enumerate(memo):
            if ch in IDX and not _is_formula_number(memo, i):
                chars[i] = " "
        memo = "".join(chars)
        present = sorted({IDX[c] for c in memo if c in IDX})
        if not present:
            continue
        # 1) 连续性：应从 ① 起连续到 max
        for expected in range(1, present[-1] + 1):
            if expected not in present:
                errs.append(f"第 {n} 题：解析缺少公式编号 {CIRCLED[expected - 1]}"
                            f"（现有 {''.join(CIRCLED[i - 1] for i in present)}）")
        # 2) 悬空引用：仅出现一次且被“由X式”等引用
        for c in (CIRCLED[i - 1] for i in present):
            if memo.count(c) == 1 and re.search(
                    r"[由、和及联]" + re.escape(c) + r"|" + re.escape(c) + r"式", memo):
                warns.append(f"第 {n} 题：解析引用“{c}式”，但 {c} 仅出现一次（疑未编号）")
    return errs, warns


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="解析中公式编号（①②③…）检查")
    ap.add_argument("paths", nargs="*", type=Path, help=".tex 文件或目录；缺省 试卷/")
    ap.add_argument("--quiet", action="store_true", help="仅输出问题与汇总")
    args = ap.parse_args(argv)

    files = collect_tex(args.paths) if args.paths else collect_tex([ROOT / "试卷"])
    total_err = total_warn = 0
    for f in files:
        errs, warns = check_text(f.read_text(encoding="utf-8"))
        total_err += len(errs)
        total_warn += len(warns)
        if errs or (warns and not args.quiet):
            print(f"[{'错误' if errs else '提示'}] {f}")
            for e in errs:
                print(f"    - {e}")
            for w in warns:
                print(f"    - {w}")
    if total_err:
        print(f"\n结果：{total_err} 处错误，{total_warn} 处提示 ❌")
        return 1
    print(f"\n结果：无错误，{total_warn} 处提示 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())

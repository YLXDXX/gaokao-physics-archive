#!/usr/bin/env python3
"""tools/check_units.py —— PhyUnit 单位宏检查

`check_content.py` 负责“裸单位”告警；本脚本补一层**宏定义一致性**：

1. 扫描试卷中用到的 `\\Uxxx` 单位宏，核对是否都在 `PhyUnit.sty` 中定义
   （拼写错误如 `\\Ukmh` 误写为 `\\Ukm/h`、`\\Ukgmc` 误写为 `\\Ukgm3` 可提前发现）；
2. `--suggest`：对常见裸单位给出建议的 PhyUnit 宏（默认关闭，避免与 check_content 重复）。

用法::

    python3 tools/check_units.py 试卷/2000/上海/上海.tex
    python3 tools/check_units.py 试卷/ --suggest

退出码：0 通过；1 存在未定义宏。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parent.parent
PHYUNIT = ROOT / "PhyUnit.sty"
USED_RE = re.compile(r"\\(U[A-Za-z]+)")
SUGGEST_MAP = [
    (re.compile(r"(?<![A-Za-z])m\s*/\s*s\s*[\^²]?2(?![A-Za-z0-9])"), r"\Umsq"),
    (re.compile(r"(?<![A-Za-z])m\s*/\s*s(?![A-Za-z0-9^])"), r"\Ums"),
    (re.compile(r"(?<![A-Za-z])km\s*/\s*h(?![A-Za-z])"), r"\Ukmh"),
    (re.compile(r"kg\s*/\s*m\s*[\^³]?3"), r"\Ukgmc"),
    (re.compile(r"(?<![A-Za-z])mA(?![A-Za-z])"), r"\UmA"),
    (re.compile(r"(?<![A-Za-z])kPa(?![A-Za-z])"), r"\UkPa"),
    (re.compile(r"(?<![A-Za-z])eV(?![A-Za-z])"), r"\UeV"),
]


def defined_macros() -> Set[str]:
    if not PHYUNIT.is_file():
        return set()
    t = PHYUNIT.read_text(encoding="utf-8")
    return set(re.findall(r"\\NewDocumentCommand\s+\\(U[A-Za-z]+)", t))


def _strip_comments(text: str) -> str:
    out = []
    for line in text.splitlines():
        # 去除未转义 % 及其后内容
        out.append(re.sub(r"(?<!\\)%.*$", "", line))
    return "\n".join(out)


def check_file(tex: Path, defined: Set[str], suggest: bool = False) -> Tuple[List[str], List[str]]:
    errs: List[str] = []
    warns: List[str] = []
    text = _strip_comments(tex.read_text(encoding="utf-8"))
    for m in set(USED_RE.findall(text)):
        if m not in defined:
            errs.append(f"{tex.name}: 使用了未在 PhyUnit.sty 定义的宏 \\{m}")
    if suggest:
        for pat, rep in SUGGEST_MAP:
            for mm in pat.finditer(text):
                warns.append(f"{tex.name}: 裸单位“{mm.group(0)}”建议改用 {rep}")
    return errs, warns


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


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="PhyUnit 单位宏检查")
    ap.add_argument("paths", nargs="*", type=Path, help=".tex 文件或目录；缺省 试卷/")
    ap.add_argument("--suggest", action="store_true", help="对常见裸单位给出建议宏")
    args = ap.parse_args(argv)
    defined = defined_macros()
    files = collect_tex(args.paths) if args.paths else collect_tex([ROOT / "试卷"])
    total_err = total_warn = 0
    for f in files:
        errs, warns = check_file(f, defined, suggest=args.suggest)
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

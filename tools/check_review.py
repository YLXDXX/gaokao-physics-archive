#!/usr/bin/env python3
"""tools/check_review.py —— 试卷成品“跨项复查”脚本。

在 `check_paper.py`（结构/元数据/标签）、`check_content.py`（书写）之外，
补一层**逐题跨项一致性**检查（本会话三卷审计沉淀的高频问题）：

1. 解析“引图而图不在”：某题 `\\memoanswer` 里出现“如图所示 / 图~\\ref”等，
   但整题**不含任何图片命令**；
2. 选择题答案“三处一致”：`\\xzanswer{}`、`\\fourchoices[answer=]`、`%% answer:`
   三者必须相同；
3. 与平台 JSON 的答案一致：由 `试卷/<年>/<地区>/<地区>.tex` 推断
   `JSON/<年>/<年_<地区>.json`，逐题比对选择题答案（JSON 不存在时给提示）。
4. 题干/答案引用的 `\\ref` 标签须在本文档定义（图片命令 label 或 `\\label{}`）。

用法::

    python3 tools/check_review.py                 # 默认扫描 试卷/*/*/*.tex
    python3 tools/check_review.py 试卷/2026/湖南
    python3 tools/check_review.py --quiet

退出码：0 通过；1 存在问题。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
PIC_RE = re.compile(r"\\(?:one|two|three|four|five|six|seven|eight|nine)picture|"
                    r"\\(?:includegraphics|includesvg)|figs/[A-Za-z0-9_\-]")
REF_FIG_RE = re.compile(r"图\s*(?:~?\\ref\{|\\ref\{)|如图所示|如图")
CHOICE_TYPES = ("单选", "多选", "选择题")


def collect_tex(paths: List[Path]) -> List[Path]:
    files: List[Path] = []
    for p in paths:
        if p.is_dir():
            for f in sorted(p.rglob("*.tex")):
                if "TikZ" in f.parts:
                    continue
                files.append(f)
        elif p.suffix == ".tex":
            files.append(p)
    return files


def infer_json(tex: Path) -> Optional[Path]:
    """试卷/<年>/<地区>/<地区>.tex → JSON/<年>/<年_<地区>.json。"""
    try:
        rel = tex.resolve().relative_to(ROOT / "试卷")
    except ValueError:
        return None
    if len(rel.parts) < 3:
        return None
    year, region = rel.parts[0], rel.parts[1]
    if not re.fullmatch(r"\d{4}", year):
        return None
    return ROOT / "JSON" / year / f"{year}_{region}.json"


def json_answers(tex: Path) -> Dict[int, str]:
    jp = infer_json(tex)
    if not jp or not jp.is_file():
        return {}
    try:
        data = json.loads(jp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    out: Dict[int, str] = {}
    for it in data.get("items", []):
        n = it.get("number")
        if not isinstance(n, int):
            continue
        t = it.get("type") or ""
        if any(k in t for k in CHOICE_TYPES):
            out[n] = re.sub(r"[^A-I]", "", it.get("answer") or "")
    return out


def check_file(tex: Path) -> Tuple[List[str], List[str]]:
    errs: List[str] = []
    warns: List[str] = []
    text = tex.read_text(encoding="utf-8")
    defined = set(re.findall(r"(?<![A-Za-z])label[A-I]?=([^\s,}\]]+)", text)) | \
        set(re.findall(r"\\label\{([^}]+)\}", text))
    jans = json_answers(tex)
    if infer_json(tex) and not jans:
        warns.append(f"{tex.name}: 未找到对应 JSON 或其中无选择题答案，跳过 JSON 比对")

    for block in re.split(r"(?=^%% number:)", text, flags=re.M):
        m = re.match(r"%% number:\s*(\d+)", block)
        if not m:
            continue
        n = int(m.group(1))
        tmatch = re.search(r"%%\s*type:\s*(.*)", block)
        is_choice = bool(tmatch and any(k in tmatch.group(1) for k in CHOICE_TYPES))

        # 1) 解析引图而图不在
        if "\\memoanswer" in block and REF_FIG_RE.search(block) and not PIC_RE.search(block):
            errs.append(f"{tex.name}: 第 {n} 题解析提到图，但该题未见任何图片命令")

        # 2) 选择题三处答案一致 + 3) 与 JSON 一致
        if is_choice:
            xz = re.search(r"\\xzanswer\{([^}]*)\}", block)
            fc = re.search(r"\\[a-z]+choices?\s*\[[^\]]*answer=([A-I]+)", block)
            af = re.search(r"%%\s*answer:\s*([A-I]+)", block)
            vals = {
                "\\xzanswer": re.sub(r"[^A-I]", "", xz.group(1)) if xz else None,
                "fourchoices[answer]": fc.group(1) if fc else None,
                "%% answer": af.group(1) if af else None,
            }
            present = {k: v for k, v in vals.items() if v}
            if len(set(present.values())) > 1:
                errs.append(f"{tex.name}: 第 {n} 题选择题答案三处不一致：{present}")
            if n in jans and present and jans[n] not in present.values():
                errs.append(f"{tex.name}: 第 {n} 题答案与 JSON 不符："
                            f"JSON={jans[n]}，tex={present}")

        # 4) \ref 目标须定义
        for ref in set(re.findall(r"\\ref\{([^}]+)\}", block)):
            if ref not in defined:
                errs.append(f"{tex.name}: 第 {n} 题 \\ref{{{ref}}} 未定义")

    return errs, warns


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="试卷成品跨项复查")
    ap.add_argument("paths", nargs="*", type=Path, help=".tex 文件或目录；缺省 试卷/")
    ap.add_argument("--quiet", action="store_true", help="仅输出问题与汇总")
    args = ap.parse_args(argv)

    files = collect_tex(args.paths) if args.paths else collect_tex([ROOT / "试卷"])
    if not files:
        print("未找到 .tex 文件。")
        return 1

    total_err = total_warn = 0
    for f in files:
        errs, warns = check_file(f)
        total_err += len(errs)
        total_warn += len(warns)
        for w in warns:
            print(f"[提示] {w}")
        for e in errs:
            print(f"[错误] {e}")

    if not args.quiet:
        print(f"\n复查完成：{len(files)} 个文件，错误 {total_err}，提示 {total_warn}。")
    return 1 if total_err else 0


if __name__ == "__main__":
    sys.exit(main())

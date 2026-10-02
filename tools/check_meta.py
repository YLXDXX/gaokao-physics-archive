#!/usr/bin/env python3
"""tools/check_meta.py —— 逐题元数据与平台 JSON 一致性校验

`check_paper.py` 只校验元数据块的**字段是否齐全有序**，不校验取值。本脚本把每道题的
元数据（`%% number/paperName/typeId/type/chapter/point/method/score/degree/duplicateId`，
以及选择题 `%% answer`）与 `JSON/<年>/<年_<地区>.json` 中同号题逐字段比对，防止转换中漂移。

用法::

    python3 tools/check_meta.py 试卷/2000/上海/上海.tex
    python3 tools/check_meta.py 试卷/            # 默认扫描 试卷/*/*/*.tex

无对应 JSON 时跳过并给出提示。退出码：0 通过；1 存在问题。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
# 参与比对的元数据字段（顺序无关；body/answer/memo 为段首标记，单独处理）
META_FIELDS = ["number", "paperName", "typeId", "type", "chapter", "point",
               "method", "score", "degree", "duplicateId"]
CHOICE_TYPES = ("单选", "多选", "选择题")


def infer_json(tex: Path) -> Optional[Path]:
    """试卷/<年>/<地区>/<地区>.tex → JSON/<年>/<年_<地区>.json。"""
    try:
        rel = tex.resolve().relative_to(ROOT / "试卷")
    except ValueError:
        return None
    if len(rel.parts) < 3 or not re.fullmatch(r"\d{4}", rel.parts[0]):
        return None
    year, region = rel.parts[0], rel.parts[1]
    return ROOT / "JSON" / year / f"{year}_{region}.json"


def _norm(v) -> str:
    if v is None:
        return ""
    return re.sub(r"\s+", " ", str(v)).strip()


def _letters(raw) -> str:
    """从（可能含 HTML 的）答案中提取 A–I 字母（先去标签，避免 Book Antiqua 之类误判）。"""
    txt = re.sub(r"<[^>]+>", "", raw or "")
    return re.sub(r"[^A-I]", "", txt)


def parse_meta(text: str) -> Dict[int, Dict[str, str]]:
    """解析 .tex 中各题的 13 项元数据注释，返回 {题号: {字段: 值}}。"""
    out: Dict[int, Dict[str, str]] = {}
    for block in re.split(r"(?=^%%\s*number\s*[:：])", text, flags=re.M):
        m = re.match(r"%%\s*number\s*[:：]\s*(\d+)", block)
        if not m:
            continue
        n = int(m.group(1))
        d: Dict[str, str] = {}
        for line in block.splitlines():
            fm = re.match(r"^%%\s*([A-Za-z]+)\s*[:：]\s*(.*)$", line)
            if fm:
                d[fm.group(1)] = fm.group(2).strip()
        out[n] = d
    return out


def check_file(tex: Path) -> Tuple[List[str], List[str]]:
    errs: List[str] = []
    warns: List[str] = []
    jp = infer_json(tex)
    if not jp or not jp.is_file():
        return errs, [f"{tex.name}: 未找到对应 JSON（{jp}），跳过元数据比对"]
    try:
        data = json.loads(jp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return errs, [f"{tex.name}: 读取 JSON 失败：{e}"]
    items = {int(it["number"]): it for it in data.get("items", [])
             if isinstance(it.get("number"), int)}
    metas = parse_meta(tex.read_text(encoding="utf-8"))
    for n, meta in metas.items():
        it = items.get(n)
        if it is None:
            errs.append(f"{tex.name}: 第 {n} 题在 JSON 中无对应项")
            continue
        for f in META_FIELDS:
            a, b = _norm(meta.get(f)), _norm(it.get(f))
            if a != b:
                errs.append(f"{tex.name}: 第 {n} 题元数据 {f} 不符：tex={a!r} JSON={b!r}")
        # 选择题：%% answer 与 JSON 答案字母一致
        if any(k in (it.get("type") or "") for k in CHOICE_TYPES):
            letters = _letters(it.get("answer"))
            if _norm(meta.get("answer")) != letters:
                errs.append(f"{tex.name}: 第 {n} 题 %% answer 不符："
                            f"tex={meta.get('answer')!r} JSON={letters!r}")
    for n in items:
        if n not in metas:
            errs.append(f"{tex.name}: JSON 第 {n} 题在 tex 中缺失")
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
    ap = argparse.ArgumentParser(description="逐题元数据与平台 JSON 一致性校验")
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

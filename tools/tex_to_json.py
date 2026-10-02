#!/usr/bin/env python3
"""tools/tex_to_json.py —— 从成品 .tex 反向抽取“档案 JSON”

规范要求“排版完成后应能反向生成高质量 JSON”。本脚本把一份 `试卷/<年>/<地区>/<地区>.tex`
逐题还原为 JSON（元数据 + 题干 + 答案 + 详解，均为 LaTeX 源），用于长期归档与一致性校验。

> 说明：平台 JSON 的题干是 HTML，本脚本输出的是**LaTeX 档案 JSON**（内容等价、格式不同），
> 不做 HTML 还原。用 `--compare <平台JSON>` 可逐字段核对元数据（与 `check_meta.py` 同源逻辑）。

用法::

    python3 tools/tex_to_json.py 试卷/2000/上海/上海.tex -o /tmp/上海.json
    python3 tools/tex_to_json.py 试卷/2000/上海/上海.tex \
        --compare JSON/2000/2000_上海.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
META_FIELDS = ["number", "paperName", "typeId", "type", "chapter", "point",
               "method", "score", "degree", "duplicateId"]
CHOICE_TYPES = ("单选", "多选", "选择题")


def _norm(v) -> str:
    if v is None:
        return ""
    return re.sub(r"\s+", " ", str(v)).strip()


def parse_paper(tex: Path) -> dict:
    text = tex.read_text(encoding="utf-8")
    ch = re.search(r"\\chapter\{([^}]*)\}", text)
    items: List[Dict[str, str]] = []
    for block in re.split(r"(?=^%%\s*number\s*[:：])", text, flags=re.M):
        m = re.match(r"%%\s*number\s*[:：]\s*(\d+)", block)
        if not m:
            continue
        d: Dict[str, str] = {}
        for line in block.splitlines():
            fm = re.match(r"^%%\s*([A-Za-z]+)\s*[:：]\s*(.*)$", line)
            if fm:
                d[fm.group(1)] = fm.group(2).strip()
        # 题干 / 答案 / 详解
        body = _slice(block, "%% body:", "%% answer:")
        answer = _slice(block, "%% answer:", "%% memo:")
        memo = _slice(block, "%% memo:", None)
        item = {k: d.get(k, "") for k in META_FIELDS}
        item["body"] = body.strip()
        item["answer"] = (d.get("answer", "") + "\n" + answer).strip()
        item["memo"] = memo.strip()
        items.append(item)
    return {"chapter": ch.group(1) if ch else "", "source": str(tex),
            "items": items}


def _slice(block: str, start: str, end: Optional[str]) -> str:
    i = block.find(start)
    if i < 0:
        return ""
    i = block.find("\n", i)
    if i < 0:
        return ""
    j = block.find(end, i) if end else -1
    return block[i:j] if j >= 0 else block[i:]


def compare(parsed: dict, ref: Path) -> List[str]:
    errs: List[str] = []
    data = json.loads(ref.read_text(encoding="utf-8"))
    ref_items = {int(it["number"]): it for it in data.get("items", [])
                 if isinstance(it.get("number"), int)}
    for it in parsed["items"]:
        n = int(it["number"])
        r = ref_items.get(n)
        if r is None:
            errs.append(f"第 {n} 题：平台 JSON 无对应项")
            continue
        for f in META_FIELDS:
            if _norm(it.get(f)) != _norm(r.get(f)):
                errs.append(f"第 {n} 题 {f}：tex={it.get(f)!r} JSON={r.get(f)!r}")
        if any(k in (r.get("type") or "") for k in CHOICE_TYPES):
            txt = re.sub(r"<[^>]+>", "", r.get("answer") or "")
            letters = re.sub(r"[^A-I]", "", txt)
            got = re.sub(r"[^A-I]", "", it.get("answer", "").splitlines()[0])
            if got != letters:
                errs.append(f"第 {n} 题 answer：tex={got!r} JSON={letters!r}")
    return errs


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="从成品 .tex 反向抽取档案 JSON")
    ap.add_argument("tex", type=Path)
    ap.add_argument("-o", "--out", type=Path, default=None)
    ap.add_argument("--compare", type=Path, default=None,
                    help="与平台 JSON 逐字段核对元数据")
    args = ap.parse_args(argv)
    if not args.tex.is_file():
        print(f"[错误] 找不到 {args.tex}", file=sys.stderr)
        return 1
    parsed = parse_paper(args.tex)
    out = args.out or args.tex.with_suffix(".archive.json")
    out.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[完成] {len(parsed['items'])} 题 → {out}")
    if args.compare:
        errs = compare(parsed, args.compare)
        if errs:
            for e in errs:
                print(f"[不一致] {e}")
            return 1
        print(f"[通过] 元数据与 {args.compare} 一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""tools/review_to_ledger.py —— 由“复核结果”生成/更新异常台账。

复核（人工或子代理）产出的结构化结果，可统一写成 JSON 后由本脚本合并进
`异常记录/<年>.md` 的六列表格，免去手工誊抄与状态漂移。

输入格式（每个文件一个对象，或 `entries` 数组；也可给目录，递归读取 `*.json`）::

    {
      "year": "2008",
      "region": "全国理综Ⅰ",
      "entries": [
        {"number": "25", "category": "缺图", "problem": "解析引轨迹图 JSON 未提供",
         "action": "从 pdfimages 补入 25_an1/2/3", "status": "已解决"},
        {"number": "17", "category": "公式", "problem": "...", "action": "...",
         "status": "待人工核验"}
      ]
    }

也接受紧凑形式：对象里直接含 `number/category/...` 与顶层 `year`/`region`。

合并规则：以 `(地区, 题号, 类别, 问题)` 为键去重；命中则更新“处理建议/状态”。
统一格式（含 `## 状态` 分区小节）下按条目「状态」并入对应分区，状态变化时移动到目标
分区，并重排为 待补充 → 待处理/处理中 → 待人工核验 → 已解决（已解决置末）；
旧版单表格格式则追加/更新到首个表格。类别/状态取值须合法（见 `异常记录/_模板.md`）。

用法::

    python3 tools/review_to_ledger.py 复核结果.json           # 预览（不改文件）
    python3 tools/review_to_ledger.py 复核结果/ --write       # 写入异常记录/<年>.md

退出码：0 成功；1 格式/取值非法。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
ANOM_DIR = ROOT / "异常记录"

try:  # 复用 gen_index 的枚举（作为模块导入时）
    from tools.gen_index import ANOM_CATEGORIES, ANOM_OK
except Exception:  # 直接运行时的回退
    ANOM_CATEGORIES = ["缺题", "缺图", "缺详解", "详解", "来源", "公式", "单位", "文字",
                       "答案", "元数据", "图片编号", "复合图", "理综", "回忆版",
                       "平台数据", "其它"]
    ANOM_OK = {"待处理", "处理中", "已解决", "待人工核验", "待补充"}

HEADER_COLS = ["地区", "题号", "类别", "问题", "处理建议", "状态"]

# 统一格式的状态分区小节顺序（「已解决」置末）
STATUS_ORDER = ["待补充", "待处理 / 处理中", "待人工核验", "已解决"]
STATUS_TO_GROUP = {
    "待补充": "待补充",
    "待处理": "待处理 / 处理中",
    "处理中": "待处理 / 处理中",
    "待人工核验": "待人工核验",
    "已解决": "已解决",
}


def load_entries(paths: List[Path]) -> List[dict]:
    """读取复核结果文件/目录 → 规范化条目列表。"""
    files: List[Path] = []
    for p in paths:
        if p.is_dir():
            files += sorted(p.rglob("*.json"))
        elif p.suffix == ".json":
            files.append(p)
    out: List[dict] = []
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        bundles = data if isinstance(data, list) else [data]
        for b in bundles:
            year, region = b.get("year"), b.get("region")
            ents = b.get("entries") or [b]  # 紧凑形式：对象本身即一条
            for e in ents:
                out.append({
                    "year": str(e.get("year", year) or ""),
                    "region": e.get("region", region) or "",
                    "number": str(e.get("number", "")),
                    "category": e.get("category", ""),
                    "problem": e.get("problem", ""),
                    "action": e.get("action", ""),
                    "status": e.get("status", ""),
                })
    return out


def _row_cells(line: str) -> List[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _row_line(e: dict) -> str:
    return (f"| {e['region']} | {e['number']} | {e['category']} | "
            f"{e['problem']} | {e['action']} | {e['status']} |")


def find_table(lines: List[str]) -> Tuple[int, int]:
    """返回**首个**六列表格数据行的 (start, end)（不含表头与分隔行）；找不到返回 (-1, -1)。"""
    hdr = -1
    for i, l in enumerate(lines):
        if l.lstrip().startswith("|") and all(c in _row_cells(l) for c in HEADER_COLS):
            hdr = i
            break
    if hdr < 0:
        return -1, -1
    start = hdr + 2  # 跳过表头 + 分隔行
    end = start
    while end < len(lines) and lines[end].lstrip().startswith("|"):
        end += 1
    return start, end


def _find_table_in(lines: List[str], lo: int, hi: int) -> Tuple[int, int]:
    """在 [lo, hi) 内查找六列表格数据行范围；找不到返回 (-1, -1)。"""
    hi = min(hi, len(lines))
    hdr = -1
    for i in range(lo, hi):
        if lines[i].lstrip().startswith("|") and all(c in _row_cells(lines[i]) for c in HEADER_COLS):
            hdr = i
            break
    if hdr < 0:
        return -1, -1
    start = hdr + 2
    end = start
    while end < hi and lines[end].lstrip().startswith("|"):
        end += 1
    return start, end


def _status_headings(lines: List[str]) -> List[Tuple[int, str]]:
    """返回 [(行号, 状态分区标题)]，仅识别合法状态小节。"""
    return [(i, ln[3:].strip()) for i, ln in enumerate(lines)
            if ln.startswith("## ") and ln[3:].strip() in STATUS_ORDER]


def _find_existing(records: Dict[str, List[List[str]]], key: Tuple[str, ...]):
    for g in STATUS_ORDER:
        for i, c in enumerate(records[g]):
            if (c[0], c[1], c[2], c[3]) == key:
                return g, i
    return None, None


def merge_year(text: str, entries: List[dict]) -> Tuple[str, List[str]]:
    """把某年的条目合并进文本；返回 (新文本, 变更说明)。

    - 统一格式（含 `## 状态` 分区小节）：按条目「状态」并入对应分区；重复键就地更新，
      状态变化时移动到目标分区；最终按 待补充 → 待处理/处理中 → 待人工核验 → 已解决
      重排（空分区省略、已解决置末）。
    - 旧版单表格格式：保持“首个表格追加/更新”的兼容行为。
    """
    lines = text.splitlines()
    changes: List[str] = []
    sh = _status_headings(lines)

    if sh:
        first = sh[0][0]
        preamble = lines[:first]
        while preamble and preamble[-1].strip() in ("", "---"):
            preamble.pop()
        records: Dict[str, List[List[str]]] = {g: [] for g in STATUS_ORDER}
        for k, (hi, title) in enumerate(sh):
            hi_next = sh[k + 1][0] if k + 1 < len(sh) else len(lines)
            s, e = _find_table_in(lines, hi, hi_next)
            if s >= 0:
                for i in range(s, e):
                    c = _row_cells(lines[i])
                    if len(c) >= 6:
                        records[title].append(c[:6])
        for e in entries:
            target = STATUS_TO_GROUP[e["status"]]
            key = (e["region"], e["number"], e["category"], e["problem"])
            call = [e["region"], e["number"], e["category"],
                    e["problem"], e["action"], e["status"]]
            g, i = _find_existing(records, key)
            if g is not None:
                old = records[g][i]
                if old[4] != e["action"] or old[5] != e["status"]:
                    changes.append(f"[更新] {e['region']} {e['number']} {e['category']}"
                                   f"：{old[5]} → {e['status']}")
                if g == target:
                    records[g][i] = call
                else:
                    records[g].pop(i)
                    records[target].append(call)
            else:
                records[target].append(call)
                changes.append(f"[新增] {e['region']} {e['number']} {e['category']}")
        out = list(preamble)
        for g in STATUS_ORDER:
            if not records[g]:
                continue
            out += ["", "---", "", f"## {g}", "",
                    "| 地区 | 题号 | 类别 | 问题 | 处理建议 | 状态 |",
                    "| :--- | :--- | :--- | :--- | :--- | :--- |"]
            out += ["| " + " | ".join(c) + " |" for c in records[g]]
        return "\n".join(out).rstrip() + "\n", changes

    # 旧版单表格兼容
    start, end = find_table(lines)
    if start < 0:
        return text, ["[跳过] 未找到六列表格"]
    existing: Dict[Tuple[str, str, str, str], int] = {}
    for i in range(start, end):
        c = _row_cells(lines[i])
        if len(c) >= 6:
            existing[(c[0], c[1], c[2], c[3])] = i
    appended: List[str] = []
    for e in entries:
        key = (e["region"], e["number"], e["category"], e["problem"])
        if key in existing:
            old = _row_cells(lines[existing[key]])
            if old[4] != e["action"] or old[5] != e["status"]:
                lines[existing[key]] = _row_line(e)
                changes.append(f"[更新] {e['region']} {e['number']} {e['category']}"
                               f"：{old[5]} → {e['status']}")
        else:
            appended.append(_row_line(e))
            changes.append(f"[新增] {e['region']} {e['number']} {e['category']}")
    if appended:
        lines = lines[:end] + appended + lines[end:]
    return "\n".join(lines) + ("\n" if text.endswith("\n") else ""), changes


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="由复核结果 JSON 生成/更新异常台账")
    ap.add_argument("paths", nargs="+", type=Path, help="复核结果 .json 或目录")
    ap.add_argument("--write", action="store_true", help="写回 异常记录/<年>.md")
    args = ap.parse_args(argv)

    entries = load_entries(args.paths)
    if not entries:
        print("未读到任何条目。")
        return 0
    # 取值校验
    bad = [e for e in entries if e["category"] not in ANOM_CATEGORIES
           or e["status"] not in ANOM_OK or not e["year"]]
    if bad:
        for e in bad:
            print(f"[错误] 非法条目（year/category/status）：{e}", file=sys.stderr)
        return 1

    by_year: Dict[str, List[dict]] = {}
    for e in entries:
        by_year.setdefault(e["year"], []).append(e)

    for year, ents in by_year.items():
        path = ANOM_DIR / f"{year}.md"
        if not path.exists():
            print(f"[跳过] 无 异常记录/{year}.md")
            continue
        text = path.read_text(encoding="utf-8")
        new_text, changes = merge_year(text, ents)
        for c in changes:
            print(f"{year}: {c}")
        if args.write and new_text != text:
            path.write_text(new_text, encoding="utf-8")
            print(f"[写入] 异常记录/{year}.md（{len(changes)} 处）")
    if not args.write:
        print("（预览模式；加 --write 写回）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

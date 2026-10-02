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


def parse_source_numbers(text: str) -> Optional[List[int]]:
    """解析卷级 `%% sourceNumbers: 17, 19, ...`；无则返回 None。

    由 `json_to_tex.py --renumber` 写入：tex 的 `%% number` 被重编为 1..N，
    本列表记录第 i 题对应的**平台原题号**，供本脚本映射回 JSON 比对。
    """
    m = re.search(r"^%%\s*sourceNumbers\s*[:：]\s*(.+)$", text, re.M)
    if not m:
        return None
    return [int(x) for x in re.findall(r"\d+", m.group(1))]


def _last_by_number(items_list: List[dict]) -> Tuple[Dict[int, dict], Dict[int, int]]:
    """返回 {题号: 最后一条} 与 {题号: 出现次数}。

    平台常把一道大题拆成多条同号项（实验Ⅰ/Ⅱ、选修 (1)(2)、A/B 变体），
    合并题以**最后一条**的元数据为准（与制卷约定一致）。
    """
    last: Dict[int, dict] = {}
    count: Dict[int, int] = {}
    for it in items_list:
        n = it.get("number")
        if isinstance(n, int):
            last[n] = it
            count[n] = count.get(n, 0) + 1
    return last, count


def _compare(tex_name: str, label: str, meta: Dict[str, str], it: dict,
             errs: List[str], ignore: Tuple[str, ...] = ()) -> None:
    """逐字段比对一道题的元数据（含选择题 %% answer）；`ignore` 中的字段跳过。"""
    for f in META_FIELDS:
        if f in ignore:
            continue
        a, b = _norm(meta.get(f)), _norm(it.get(f))
        if a != b:
            errs.append(f"{tex_name}: {label}元数据 {f} 不符：tex={a!r} JSON={b!r}")
    if any(k in (it.get("type") or "") for k in CHOICE_TYPES):
        letters = _letters(it.get("answer"))
        if _norm(meta.get("answer")) != letters:
            errs.append(f"{tex_name}: {label}%% answer 不符："
                        f"tex={meta.get('answer')!r} JSON={letters!r}")


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
    items, counts = _last_by_number(data.get("items", []))
    text = tex.read_text(encoding="utf-8")
    metas = parse_meta(text)
    srcs = parse_source_numbers(text)

    if srcs is not None:
        # 经 --renumber：tex 的 %% number = 1..N，映射回平台原题号比对
        for n, meta in metas.items():
            if not (1 <= n <= len(srcs)):
                errs.append(f"{tex.name}: 第 {n} 题超出 %% sourceNumbers 范围"
                            f"（共 {len(srcs)} 个）")
                continue
            src = srcs[n - 1]
            it = items.get(src)
            if it is None:
                errs.append(f"{tex.name}: 第 {n} 题（原题号 {src}）在 JSON 中无对应项")
                continue
            # tex 的 %% number 是重编后的序号，与 JSON 原题号必然不同，跳过该字段
            _compare(tex.name, f"第 {n} 题（原 {src}）", meta, it, errs,
                     ignore=("number",))
        if len(metas) != len(srcs):
            warns.append(f"{tex.name}: tex 有 {len(metas)} 题，"
                         f"%% sourceNumbers 有 {len(srcs)} 个")
    else:
        for n, meta in metas.items():
            it = items.get(n)
            if it is None:
                errs.append(f"{tex.name}: 第 {n} 题在 JSON 中无对应项")
                continue
            _compare(tex.name, f"第 {n} 题", meta, it, errs)
        for n in items:
            if n not in metas:
                errs.append(f"{tex.name}: JSON 第 {n} 题在 tex 中缺失")

    for n, c in counts.items():
        if c > 1:
            warns.append(f"{tex.name}: 第 {n} 题 JSON 有 {c} 条同号项"
                         f"（合并题按最后一条比对元数据）")
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

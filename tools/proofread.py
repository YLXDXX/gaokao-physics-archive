#!/usr/bin/env python3
"""tools/proofread.py —— 交叉校对基础设施（他源成品 PDF ↔ 本仓库试卷）

本脚本只做「基础设施」：扫描、映射、规范化重命名、生成交叉校对表、校验。
不改动任何 `试卷/` 下的 LaTeX 内容。

数据源（均在本地、Git 忽略的 `ProofreadPDF/`，见 `.gitignore`）：
- `tian`：天利 38 套，2025–2026，试卷与答案分离（`<年>_<地区>.pdf` +
  `<年>_<地区>_答案.pdf`），出版物源，部分为矢量配图，准确率最高。
- `zhu`：朱玉亮《1978 年至今 高考物理真题分类全汇编》，1978–2024，
  试卷与答案分离（`<年>_<地区>.pdf` + `<年>_<地区>_答案.pdf`），出版物矢量源。
- `liu`：刘芳项目，1978–2026，教师版合订（`<年>_<地区>.pdf`），含简略答案、无详解。
冲突裁定优先级：天利 > 朱玉亮 > 刘芳 > 本仓库现有材料；详见 `交叉校对/规范.md`。

命令：
    python3 tools/proofread.py plan               # 扫描 → 交叉校对/mapping.json
    python3 tools/proofread.py rename [--apply|--revert]  # 源树内规范化重命名 / 回滚
    python3 tools/proofread.py table [--check]    # 生成 交叉校对/交叉校对表.md
    python3 tools/proofread.py check              # 校验 mapping/源文件/仓库卷/status
    python3 tools/proofread.py show 2024/辽宁      # 查看源文件、状态、源 JSON 与未闭合异常
    python3 tools/proofread.py tokens             # 打印解析出的年份/地区 token（调试）

约束：所有路径相对仓库根；临时产物只写 `/tmp/opencode/`（本脚本不写临时文件）。
"""
from __future__ import annotations

import argparse
import datetime as _dt
import difflib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROOF_DIR = ROOT / "交叉校对"
MAPPING = PROOF_DIR / "mapping.json"
OVERRIDES = PROOF_DIR / "overrides.json"
STATUS = PROOF_DIR / "status.json"
RENAME_MANIFEST = PROOF_DIR / "rename_manifest.json"
TABLE = PROOF_DIR / "交叉校对表.md"
PAPERS = ROOT / "试卷"
SOURCE_ROOT = ROOT / "ProofreadPDF"
ANOMALY_DIR = ROOT / "异常记录"

SOURCES = {
    "tian": {
        "root": "ProofreadPDF/2025-2026",
        "label": "天利38套",
        "range": "2025–2026",
        "layout": "split",  # 试卷、答案分离
    },
    "zhu": {
        "root": "ProofreadPDF/1978-2024",
        "label": "朱玉亮",
        "range": "1978–2024",
        "layout": "split",  # 试卷、答案分离
    },
    "liu": {
        "root": "ProofreadPDF/1978-2026",
        "label": "刘芳",
        "range": "1978–2026",
        "layout": "combined",  # 教师版合订
    },
}

# 常用状态（可在 status.json 中覆盖，取值见规范）
STATUS_VALUES = ["未开始", "素材就绪", "校对中", "已完成", "待人工核验", "无源"]
CONFIDENCE_LABEL = {
    "exact": "精确",
    "alias": "别名",
    "uncertain": "待确认",
    "fuzzy": "模糊",
    "manual": "人工",
    "source-only": "仅源",
    "repo-only": "仅仓库",
}



# ---------------------------------------------------------------------------
# 基础 I/O
# ---------------------------------------------------------------------------
def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        sys.exit(f"[proofread] JSON 解析失败：{path}: {exc}")


def _save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _today() -> str:
    return _dt.date.today().isoformat()


def _join_notes(*parts: str) -> str:
    seen: list[str] = []
    for part in parts:
        for item in (part or "").split("；"):
            item = item.strip()
            if item and item not in seen:
                seen.append(item)
    return "；".join(seen)


# ---------------------------------------------------------------------------
# 试卷（本仓库）扫描
# ---------------------------------------------------------------------------
def scan_repo_sets() -> dict[tuple[int, str], dict]:
    """返回 {(year, region): {"year","region","path","tex"}}。"""
    sets: dict[tuple[int, str], dict] = {}
    if not PAPERS.is_dir():
        return sets
    for ydir in sorted(PAPERS.iterdir()):
        if not ydir.is_dir() or not ydir.name.isdigit():
            continue
        year = int(ydir.name)
        for rdir in sorted(ydir.iterdir()):
            if not rdir.is_dir() or rdir.name == "README.md":
                continue
            tex = rdir / f"{rdir.name}.tex"
            if not tex.exists():
                continue
            sets[(year, rdir.name)] = {
                "year": year,
                "region": rdir.name,
                "path": _rel(rdir),
                "tex": _rel(tex),
            }
    return sets


# ---------------------------------------------------------------------------
# 源 PDF 文件名解析
# ---------------------------------------------------------------------------
_NOISE = ["教师版", "网络回忆版", "二校", "李景雪", "高考", "真题", "docx", "题", "省"]
_BRACKETS = str.maketrans({"（": "", "）": "", "(": "", ")": "", "、": "",
                           "-": "", "—": "", "－": "", "–": "", "+": "", "＋": "",
                           "_": "", " ": "", "\u3000": ""})


def clean_token(stem: str) -> tuple[int | None, str, bool]:
    """由源文件名（去扩展名）解析出 (year, token, is_answer)。

    token 已去掉年份、题号前缀、教师版/二校等噪声，以及「物理」「卷」等通用词；
    ``浙江6月`` 会规范为 ``6月浙江``。
    """
    s = stem.strip().replace("_", "")
    s = re.sub(r"^\s*\d+\s*号\s*", "", s)
    m = re.match(r"^\s*(\d{4})\s*年?", s)
    year = int(m.group(1)) if m else None
    if m:
        s = s[m.end():]
    is_answer = "答案" in s
    s = s.replace("答案", "")
    s = s.replace(".docx", "")
    for w in _NOISE:
        s = s.replace(w, "")
    # 去掉仅作标记的 (1)/(2) 之类
    s = re.sub(r"[（(]\s*\d+\s*[)）]", "", s)
    s = s.translate(_BRACKETS)
    s = s.replace("物理", "").replace("卷", "")
    s = re.sub(r"^浙江(\d+月)$", r"\1浙江", s)
    s = s.strip()
    return year, s, is_answer


def _parse_alias_value(value) -> tuple[str | None, str, str]:
    """别名值可为 str（confidence=alias）或对象。返回 (region, confidence, note)。"""
    if isinstance(value, str):
        return value, "alias", ""
    if isinstance(value, dict):
        region = value.get("region")
        conf = value.get("confidence", "alias")
        note = value.get("note", "")
        return region, conf, note
    return None, "alias", ""


def match_token(token: str, year: int, regions: set[str], overrides: dict) -> tuple[str | None, str, str]:
    """把源 token 匹配到本仓库地区名。返回 (region, confidence, note)。"""
    if token in regions:
        return token, "exact", ""

    aliases = overrides.get("aliases", {})
    for scope in (str(year), "*"):
        table = aliases.get(scope, {})
        if token in table:
            region, conf, note = _parse_alias_value(table[token])
            if region and region in regions:
                return region, conf, note
            # 允许显式映射为 None（仅源）
            if region is None:
                return None, "source-only", note
    # 模糊匹配：仅提示，标为待人工确认
    close = difflib.get_close_matches(token, sorted(regions), n=1, cutoff=0.78)
    if close:
        return close[0], "fuzzy", f"自动模糊匹配 {token!r} → {close[0]!r}"
    return None, "source-only", ""


# ---------------------------------------------------------------------------
# 扫描源 PDF → 分组
# ---------------------------------------------------------------------------
def _is_source_dir_ready(source: str) -> bool:
    return (ROOT / SOURCES[source]["root"]).is_dir()


def _rename_index() -> dict[str, dict[str, str]]:
    """{source: {normalized_rel: original_rel}}，用于重命名后仍按原始文件名解析。"""
    manifest = _load_json(RENAME_MANIFEST, {"renames": []})
    idx: dict[str, dict[str, str]] = {}
    for m in manifest.get("renames", []):
        idx.setdefault(m["source"], {})[m["normalized"]] = m["original"]
    return idx


def scan_source_files(source: str) -> dict[tuple[int, str], dict]:
    """返回 {(year, token): {"year","token","paper","answer","files","original"}}。

    `files` / `paper` / `answer` 是**当前**相对源根路径；`original` 是重命名前的
    首个路径（由 `rename_manifest.json` 还原），token 一律按原始文件名解析，
    以保证重命名后仍保留别名/待确认等映射语义。
    """
    cfg = SOURCES[source]
    root = ROOT / cfg["root"]
    groups: dict[tuple[int, str], dict] = {}
    if not root.is_dir():
        return groups
    ren = _rename_index().get(source, {})
    for ydir in sorted(root.iterdir()):
        if not ydir.is_dir() or not ydir.name.isdigit():
            continue
        for pdf in sorted(ydir.glob("*.pdf")):
            rel = pdf.relative_to(root).as_posix()
            orig_rel = ren.get(rel, rel)
            year, token, is_answer = clean_token(Path(orig_rel).stem)
            if year is None:
                year = int(ydir.name)
            if not token:
                token = f"未解析_{Path(orig_rel).stem}"
            key = (year, token)
            g = groups.setdefault(key, {
                "year": year,
                "token": token,
                "paper": None,
                "answer": None,
                "files": [],
                "original": orig_rel,
            })
            g["files"].append(rel)
            if is_answer:
                g["answer"] = g["answer"] or rel
            else:
                g["paper"] = g["paper"] or rel
    return groups


# ---------------------------------------------------------------------------
# 生成映射
# ---------------------------------------------------------------------------
def _normalized_name(year: int, name: str, is_answer: bool) -> str:
    safe = re.sub(r'[\\/:*?"<>|]', "_", name)
    return f"{year}_{safe}{'_答案' if is_answer else ''}.pdf"


def _kind(source: str, group: dict) -> str:
    if SOURCES[source]["layout"] == "combined":
        return "教师版合订"
    if group["paper"] and group["answer"]:
        return "试卷+答案"
    if group["paper"]:
        return "仅试卷"
    if group["answer"]:
        return "仅答案"
    return "—"


def build_mapping() -> dict:
    repo_sets = scan_repo_sets()
    regions_by_year: dict[int, set[str]] = {}
    for (year, region) in repo_sets:
        regions_by_year.setdefault(year, set()).add(region)
    overrides = _load_json(OVERRIDES, {})

    rows: dict[tuple[int, str], dict] = {}
    for (year, region), info in repo_sets.items():
        rows[(year, region)] = {
            "year": year,
            "region": region,
            "repo": info["path"],
            "by_source": {},
            "confidence": "repo-only",
            "note": "",
        }

    source_only: list[dict] = []
    used: dict[tuple[str, int, str], list[str]] = {}

    for source in SOURCES:
        groups = scan_source_files(source)
        for (year, token), group in sorted(groups.items()):
            regions = regions_by_year.get(year, set())
            region, conf, note = match_token(token, year, regions, overrides)
            entry = {
                "token": token,
                "kind": _kind(source, group),
                "confidence": conf,
                "note": note,
                "original": group.get("original") or (group["files"][0] if group["files"] else None),
                "files": group["files"],
                "normalized": {},
            }
            # 明确忽略的源文件；支持全局 token 与按年 "年/token"
            ignored = set(overrides.get("ignore", []))
            if token in ignored or f"{year}/{token}" in ignored:
                continue

            # 规范化命名：已确认（exact/alias/manual）用我们的地区名；
            # 待确认/模糊/仅源用源 token，避免误导。
            use_repo_name = region is not None and conf in ("exact", "alias", "manual")
            name = region if use_repo_name else token
            entry["target_name"] = name
            if group["paper"]:
                entry["normalized"]["paper"] = f"{year}/{_normalized_name(year, name, False)}"
            if group["answer"]:
                entry["normalized"]["answer"] = f"{year}/{_normalized_name(year, name, True)}"

            fnotes = overrides.get("file_notes", {}).get(source, {})
            for norm in entry["normalized"].values():
                if norm and fnotes.get(norm):
                    entry["note"] = _join_notes(entry["note"], fnotes[norm])

            if region is None:
                source_only.append({
                    "year": year,
                    "source": source,
                    "token": token,
                    "original": entry["original"],
                    "files": entry["files"],
                    "normalized_map": entry["normalized"],
                    "normalized": entry["normalized"].get("paper")
                    or entry["normalized"].get("answer"),
                    "kind": entry["kind"],
                    "note": note or "本仓库无对应 LaTeX 卷",
                })
                continue

            row = rows.get((year, region))
            if row is None:
                # 理论上不应发生；保留为仅源
                source_only.append({
                    "year": year,
                    "source": source,
                    "token": token,
                    "original": entry["original"],
                    "files": entry["files"],
                    "normalized_map": entry["normalized"],
                    "normalized": entry["normalized"].get("paper")
                    or entry["normalized"].get("answer"),
                    "kind": entry["kind"],
                    "note": note or "映射到不存在的仓库卷",
                })
                continue

            used.setdefault((source, year, region), []).append(token)
            row["by_source"][source] = entry
            if conf in ("uncertain", "fuzzy"):
                row["confidence"] = conf
            elif row["confidence"] not in ("uncertain", "fuzzy"):
                row["confidence"] = conf
            label = SOURCES[source]["label"]
            entry_note = entry.get("note", "")
            if entry_note:
                row["note"] = _join_notes(row["note"], f"{label}：{entry_note}")
            elif conf in ("uncertain", "fuzzy"):
                row["note"] = _join_notes(row["note"], f"{label}：源映射待确认")

    # 同一源同一年同一卷被多个 token 命中 → 标待确认
    for (source, year, region), tokens in used.items():
        if len(tokens) > 1:
            row = rows[(year, region)]
            row["confidence"] = "uncertain"
            row["note"] = _join_notes(
                row["note"], f"{SOURCES[source]['label']}源有多个候选：{', '.join(tokens)}"
            )

    mapping = {
        "version": 1,
        "generated": _today(),
        "sources": {
            k: {
                "root": v["root"],
                "label": v["label"],
                "range": v["range"],
                "layout": v["layout"],
            }
            for k, v in SOURCES.items()
        },
        "rows": sorted(rows.values(), key=lambda r: (r["year"], r["region"])),
        "source_only": sorted(source_only, key=lambda r: (r["year"], r["source"], r["token"])),
    }
    return mapping


# ---------------------------------------------------------------------------
# 重命名
# ---------------------------------------------------------------------------
def _rename_plan(mapping: dict) -> list[dict]:
    plan = []
    for row in mapping["rows"]:
        for source, entry in row["by_source"].items():
            root = SOURCES[source]["root"]
            files = entry.get("files", [])
            for kind, rel in entry.get("normalized", {}).items():
                if not rel:
                    continue
                want_answer = kind == "answer"
                chosen = next(
                    (f for f in files if clean_token(Path(f).stem)[2] == want_answer),
                    None,
                )
                if chosen is None and not want_answer:
                    chosen = entry.get("original")
                if chosen:
                    plan.append({
                        "source": source,
                        "root": root,
                        "original": chosen,
                        "normalized": rel,
                    })
    for item in mapping.get("source_only", []):
        # 仅源条目按文件逐一重命名（可能同时有试卷与答案）
        source = item["source"]
        files = item.get("files") or ([item["original"]] if item.get("original") else [])
        norm = item.get("normalized_map") or {}
        for original in files:
            _, _, is_answer = clean_token(Path(original).stem)
            normalized = norm.get("answer" if is_answer else "paper")
            if normalized:
                plan.append({
                    "source": source,
                    "root": SOURCES[source]["root"],
                    "original": original,
                    "normalized": normalized,
                })
    # 去重（同一 original）
    seen = set()
    out = []
    for p in plan:
        key = (p["root"], p["original"])
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def _revert_renames() -> int:
    manifest = _load_json(RENAME_MANIFEST, {"version": 1, "renames": []})
    renames = manifest.get("renames", [])
    if not renames:
        print("[proofread] rename_manifest.json 为空，无需回滚。")
        return 0
    conflicts = []
    for m in renames:
        root = SOURCES[m["source"]]["root"]
        src = ROOT / root / m["normalized"]
        dst = ROOT / root / m["original"]
        if not src.exists():
            conflicts.append(f"当前文件不存在：{root}/{m['normalized']}")
        if dst.exists() and dst != src:
            conflicts.append(f"原文件名已被占用：{root}/{m['original']}")
    if conflicts:
        print("[proofread] 回滚中止，发现冲突：", file=sys.stderr)
        for c in conflicts:
            print("  - " + c, file=sys.stderr)
        return 2
    for m in reversed(renames):
        root = SOURCES[m["source"]]["root"]
        (ROOT / root / m["normalized"]).rename(ROOT / root / m["original"])
    manifest["renames"] = []
    _save_json(RENAME_MANIFEST, manifest)
    _save_json(MAPPING, build_mapping())
    print(f"[proofread] 已回滚 {len(renames)} 个文件；已更新 {MAPPING.relative_to(ROOT)}；"
          f"请运行 make proofread-table 刷新总表")
    return 0


def cmd_rename(args) -> int:
    if not SOURCE_ROOT.is_dir():
        print("[proofread] 未找到 ProofreadPDF/，跳过重命名。")
        return 0
    if getattr(args, "revert", False):
        return _revert_renames()
    mapping = build_mapping()
    plan = _rename_plan(mapping)

    conflicts = []
    for p in plan:
        if p["original"] == p["normalized"]:
            continue
        src = ROOT / p["root"] / p["original"]
        dst = ROOT / p["root"] / p["normalized"]
        if not src.exists():
            conflicts.append(f"源文件不存在：{p['root']}/{p['original']}")
            continue
        if dst.exists() and dst != src:
            conflicts.append(f"目标已存在：{p['root']}/{p['normalized']}")
    # 目标重名检测
    targets = [p["root"] + "/" + p["normalized"] for p in plan if p["original"] != p["normalized"]]
    dup = {x for x in targets if targets.count(x) > 1}
    if dup:
        conflicts.extend(f"目标重名：{x}" for x in sorted(dup))
    if conflicts:
        print("[proofread] 重命名中止，发现冲突：", file=sys.stderr)
        for c in conflicts:
            print("  - " + c, file=sys.stderr)
        return 2

    manifest = _load_json(RENAME_MANIFEST, {"version": 1, "renames": []})
    existing = {(m["source"], m["original"], m["normalized"]) for m in manifest["renames"]}
    applied = 0
    for p in plan:
        if p["original"] == p["normalized"]:
            continue
        src = ROOT / p["root"] / p["original"]
        dst = ROOT / p["root"] / p["normalized"]
        if args.apply:
            src.rename(dst)
            applied += 1
            print(f"  {p['source']}: {p['original']} → {p['normalized']}")
        else:
            print(f"  [预览] {p['source']}: {p['original']} → {p['normalized']}")
        key = (p["source"], p["original"], p["normalized"])
        if key not in existing:
            manifest["renames"].append({
                "source": p["source"],
                "original": p["original"],
                "normalized": p["normalized"],
                "date": _today(),
            })
            existing.add(key)

    if args.apply:
        _save_json(RENAME_MANIFEST, manifest)
        # 重命名后重新扫描，写入最新 mapping
        _save_json(MAPPING, build_mapping())
        print(f"[proofread] 已重命名 {applied} 个文件；已更新 {MAPPING.relative_to(ROOT)}；"
              f"请运行 make proofread-table 刷新总表")
    else:
        print(f"[proofread] 预览 {len([p for p in plan if p['original'] != p['normalized']])} 个待重命名文件；加 --apply 执行。")
    return 0


# ---------------------------------------------------------------------------
# 表格
# ---------------------------------------------------------------------------
def _source_cell(entry: dict | None) -> str:
    if not entry:
        return "—"
    kind = entry.get("kind", "")
    if entry.get("confidence") in ("uncertain", "fuzzy"):
        kind += "（待确认）"
    return kind


def _available(by_source: dict) -> str:
    s = []
    if "tian" in by_source:
        s.append("天")
    if "zhu" in by_source:
        s.append("朱")
    if "liu" in by_source:
        s.append("刘")
    return "+".join(s) if s else "无"


def _collapse_label_notes(note: str) -> str:
    """把“天利38套：X；朱玉亮：X；刘芳：X”合并为“天利38套/朱玉亮/刘芳：X”。"""
    parts = note.split("；") if note else []
    labels = {v["label"] for v in SOURCES.values()}
    grouped: dict[str, list[str]] = {}
    out: list[str] = []
    for part in parts:
        head, sep, tail = part.partition("：")
        if sep and head in labels:
            grouped.setdefault(tail, [])
            if head not in grouped[tail]:
                grouped[tail].append(head)
        else:
            out.append(part)
    for text, labs in grouped.items():
        out.append(f"{'/'.join(labs)}：{text}")
    return "；".join(out)


def _row_cells(r: dict, sets_status: dict) -> str:
    by = r["by_source"]
    key = f"{r['year']}/{r['region']}"
    st = sets_status.get(key, {})
    status_txt = st.get("status", "无源" if not by else "未开始")
    date_txt = st.get("date", "")
    note_parts = []
    if r.get("note"):
        note_parts.append(r["note"])
    if st.get("note"):
        note_parts.append(st["note"])
    note = _collapse_label_notes(_join_notes(*note_parts))
    if not by and st.get("status") not in STATUS_VALUES:
        status_txt = "无源"
    return (
        "| {year} | {region} | {tian} | {zhu} | {liu} | {avail} | {status} | {date} | {note} |".format(
            year=r["year"],
            region=r["region"],
            tian=_source_cell(by.get("tian")),
            zhu=_source_cell(by.get("zhu")),
            liu=_source_cell(by.get("liu")),
            avail=_available(by),
            status=status_txt,
            date=date_txt,
            note=note.replace("|", "\\|"),
        )
    )


def render_table(mapping: dict) -> str:
    status = _load_json(STATUS, {"sets": {}})
    sets_status = status.get("sets", {})
    rows = mapping["rows"]

    total = len(rows)
    with_source = sum(1 for r in rows if r["by_source"])
    without_source = total - with_source
    done = sum(
        1 for r in rows
        if sets_status.get(f"{r['year']}/{r['region']}", {}).get("status") == "已完成"
    )
    source_only = mapping.get("source_only", [])
    years = sorted({r["year"] for r in rows})

    lines: list[str] = []
    lines.append("# 交叉校对表")
    lines.append("")
    lines.append("> 本表由 `python3 tools/proofread.py table` 依据 `交叉校对/mapping.json`、")
    lines.append("> `交叉校对/status.json` 自动生成，**请勿手工编辑**；")
    lines.append("> 进度请改 `status.json` 后重新生成。规范见 `交叉校对/规范.md`，")
    lines.append("> 源文件对应关系见 `交叉校对/mapping.json`（或 `make proofread-show UNIT=2024/辽宁`）。")
    lines.append("")
    lines.append(f"- 生成日期：{mapping.get('generated', _today())}")
    lines.append(f"- 本仓库卷数：{total}；有他源可校：{with_source}；无他源可校：{without_source}")
    lines.append(f"- 已完成交叉校对：{done} 套（逐卷状态见下表与 `status.json`）")
    uniq_source_only = len({(s["year"], s["token"]) for s in source_only})
    lines.append(f"- 他源有、本仓库无：{uniq_source_only} 套源卷（{len(source_only)} 条来源记录；见第三节）")
    lines.append("- 源冲突裁定：天利38套（2025–2026，出版物，最优）＞ 朱玉亮（1978–2024，出版物矢量）＞ 刘芳（1978–2026，教师版）＞ 本仓库材料")
    lines.append("")
    lines.append("## 一、逐卷交叉校对表")
    lines.append("")
    for year in years:
        yrows = [r for r in rows if r["year"] == year]
        ysrc = sum(1 for r in yrows if r["by_source"])
        ydone = sum(
            1 for r in yrows
            if sets_status.get(f"{r['year']}/{r['region']}", {}).get("status") == "已完成"
        )
        lines.append(f"### {year} 年（{len(yrows)} 套，有源 {ysrc}，已完成 {ydone}）")
        lines.append("")
        lines.append("| 年份 | 地区 | 天利源 | 朱玉亮源 | 刘芳源 | 可用源 | 校对状态 | 最后更新 | 备注 |")
        lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
        for r in yrows:
            lines.append(_row_cells(r, sets_status))
        lines.append("")

    lines.append("## 二、本仓库有卷、他源均无（无法交叉校对）")
    lines.append("")
    no_src = [r for r in rows if not r["by_source"]]
    if not no_src:
        lines.append("（无）")
    else:
        lines.append("| 年份 | 地区 | 说明 |")
        lines.append("| :--- | :--- | :--- |")
        for r in no_src:
            lines.append(f"| {r['year']} | {r['region']} | 天利、朱、刘三源均无对应试卷 |")
    lines.append("")

    lines.append("## 三、他源有、本仓库无对应卷")
    lines.append("")
    if not source_only:
        lines.append("（无）")
    else:
        groups: dict[tuple[int, str], list[dict]] = {}
        for item in source_only:
            groups.setdefault((item["year"], item["token"]), []).append(item)
        lines.append("| 年份 | 源地区 token | 来源 | 源文件（原始名） | 类型 | 备注 |")
        lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
        for (year, token), items in sorted(groups.items()):
            labels = "、".join(sorted({SOURCES[i["source"]]["label"] for i in items}))
            files = "；".join(
                f"{SOURCES[i['source']]['label']}：{i.get('original') or ''}" for i in items
            )
            kinds = "、".join(sorted({i.get("kind", "") for i in items}))
            note = _join_notes(*[i.get("note", "") for i in items])
            lines.append(
                "| {year} | {token} | {src} | {orig} | {kind} | {note} |".format(
                    year=year,
                    token=token,
                    src=labels,
                    orig=files.replace("|", "\\|"),
                    kind=kinds,
                    note=note.replace("|", "\\|"),
                )
            )
    lines.append("")

    lines.append("## 四、状态说明")
    lines.append("")
    lines.append("- `未开始`：尚未开始交叉校对。")
    lines.append("- `素材就绪`：已找到对应他源 PDF（及必要 OCR/材料）。")
    lines.append("- `校对中`：正在逐题核对题目/答案/解析/公式/配图。")
    lines.append("- `已完成`：该卷已完成交叉校对并记录结论（异常见 `异常记录/<年>.md`）。")
    lines.append("- `待人工核验`：存在疑点或源映射不确定，需人工复核。")
    lines.append("- `无源`：三份他源均无对应试卷，无法交叉校对。")
    lines.append("")
    lines.append("> 更新方式：编辑 `交叉校对/status.json` 的 `sets.\"<年>/<地区>\"`，")
    lines.append("> 至少填写 `status`、`date`、`note`（结论/用了哪份源/发现的问题），再执行 `make proofread-table`。")
    lines.append("")
    return "\n".join(lines)


def cmd_table(args) -> int:
    mapping = _load_json(MAPPING, None)
    if mapping is None:
        print("[proofread] 缺少 交叉校对/mapping.json；请先运行 make proofread-plan。", file=sys.stderr)
        return 2
    text = render_table(mapping)
    if args.check:
        old = TABLE.read_text(encoding="utf-8") if TABLE.exists() else ""
        if old != text:
            print("[proofread] 交叉校对表与 mapping/status 不一致；请运行 make proofread-table。", file=sys.stderr)
            return 1
        print("[proofread] 交叉校对表一致。")
        return 0
    TABLE.parent.mkdir(parents=True, exist_ok=True)
    TABLE.write_text(text, encoding="utf-8")
    print(f"[proofread] 已生成 {TABLE.relative_to(ROOT)}（{len(mapping['rows'])} 卷）")
    return 0


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------
def cmd_check(args) -> int:
    errs: list[str] = []
    warns: list[str] = []
    mapping = _load_json(MAPPING, None)
    if mapping is None:
        print("[proofread] 缺少 mapping.json；请先运行 make proofread-plan。", file=sys.stderr)
        return 2

    repo_sets = scan_repo_sets()
    keys = set()
    for r in mapping.get("rows", []):
        key = (r["year"], r["region"])
        if key in keys:
            errs.append(f"mapping 重复卷：{r['year']}/{r['region']}")
        keys.add(key)
        if key not in repo_sets:
            errs.append(f"mapping 指向不存在的试卷：{r['year']}/{r['region']}")
        for src, e in r.get("by_source", {}).items():
            if src not in SOURCES:
                errs.append(f"{r['year']}/{r['region']} 未知源：{src}")
                continue
            root = ROOT / SOURCES[src]["root"]
            for kind, rel in e.get("normalized", {}).items():
                if not rel:
                    continue
                if root.is_dir() and not (root / rel).exists():
                    # 重命名前可能还是原名，检查原始文件
                    if not any((root / f).exists() for f in e.get("files", [])):
                        errs.append(f"{r['year']}/{r['region']} {src}/{kind} 文件不存在：{rel}")
    for s, info in repo_sets.items():
        if s not in keys:
            errs.append(f"试卷未纳入 mapping：{info['year']}/{info['region']}")

    if not SOURCE_ROOT.is_dir():
        warns.append("未找到 ProofreadPDF/（本地忽略），跳过源文件存在性校验。")

    for item in mapping.get("source_only", []):
        if SOURCE_ROOT.is_dir():
            root = ROOT / SOURCES[item["source"]]["root"]
            if item.get("normalized") and not (root / item["normalized"]).exists():
                if item.get("original") and not (root / item["original"]).exists():
                    errs.append(f"仅源文件不存在：{item['source']} {item['original']}")

    # overrides.json 别名校验
    overrides = _load_json(OVERRIDES, {})
    all_regions = {region for (_, region) in repo_sets}
    regions_by_year = {}
    for (year, region) in repo_sets:
        regions_by_year.setdefault(str(year), set()).add(region)
    for scope, table in overrides.get("aliases", {}).items():
        if scope != "*" and not scope.isdigit():
            warns.append(f"overrides.json 别名作用域非法：{scope}")
            continue
        for token, value in table.items():
            region, conf, _ = _parse_alias_value(value)
            if region is None:
                continue
            target = regions_by_year.get(scope) if scope != "*" else all_regions
            if target is not None and region not in target:
                warns.append(f"overrides.json 别名指向不存在的地区：{scope}/{token} → {region}")

    # status.json 校验
    st = _load_json(STATUS, {"sets": {}})
    st_sets = st.get("sets", {})
    row_keys = {f"{r['year']}/{r['region']}" for r in mapping.get("rows", [])}
    for key, val in st_sets.items():
        if not isinstance(val, dict):
            errs.append(f"status.json 条目应为对象：{key}")
            continue
        if val.get("status") not in STATUS_VALUES:
            errs.append(f"status.json 状态非法：{key} → {val.get('status')!r}"
                        f"（允许：{'/'.join(STATUS_VALUES)}）")
        if key not in row_keys:
            warns.append(f"status.json 含未知卷：{key}")
    for key in row_keys:
        if key not in st_sets:
            warns.append(f"status.json 缺少卷：{key}（运行 make proofread-plan 补齐）")

    # 表格一致性
    table_text = render_table(mapping)
    old = TABLE.read_text(encoding="utf-8") if TABLE.exists() else ""
    if old != table_text:
        warns.append("交叉校对表未刷新（运行 make proofread-table）。")

    for w in warns:
        print("[proofread] 警告：" + w)
    if errs:
        print("[proofread] 校验失败：", file=sys.stderr)
        for e in errs:
            print("  - " + e, file=sys.stderr)
        return 1
    print(f"[proofread] 校验通过：{len(mapping['rows'])} 卷、{len(mapping.get('source_only', []))} 条仅源记录。")
    return 0


# ---------------------------------------------------------------------------
# 异常记录（交叉校对前先看该卷未闭合条目）
# ---------------------------------------------------------------------------
ANOMALY_STATUS = ("待补充", "待处理", "处理中", "待人工核验")


def _split_md_row(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", s)]


def parse_anomaly_text(text: str, region: str) -> tuple[list[dict], int]:
    """从某年异常记录 Markdown 中提取该地区未闭合条目与已解决计数。

    返回 ``(未闭合条目列表, 已解决条数)``；条目字段含
    ``status/number/category/problem/suggestion``。
    """
    items: list[dict] = []
    resolved = 0
    section = ""
    for lineno, line in enumerate(text.splitlines(), 1):
        if line.startswith("## "):
            section = line[3:].strip()
            continue
        if not line.lstrip().startswith("|"):
            continue
        cells = _split_md_row(line)
        if len(cells) < 6 or cells[0] in ("地区", "---"):
            continue
        if re.fullmatch(r":?-{2,}:?", cells[0]):
            continue
        r, number, category, problem, suggestion, status = cells[:6]
        if r != region:
            continue
        status = status or section
        if status == "已解决":
            resolved += 1
            continue
        if status not in ANOMALY_STATUS and section == "已解决":
            status = "已解决"
            resolved += 1
            continue
        items.append({
            "line": lineno,
            "number": number,
            "category": category,
            "problem": problem,
            "suggestion": suggestion,
            "status": status,
        })
    return items, resolved


def parse_anomalies(year: int, region: str) -> tuple[list[dict], int]:
    path = ANOMALY_DIR / f"{year}.md"
    if not path.is_file():
        return [], 0
    return parse_anomaly_text(path.read_text(encoding="utf-8"), region)


# ---------------------------------------------------------------------------
# 调试：打印 token
# ---------------------------------------------------------------------------
def cmd_show(args) -> int:
    mapping = _load_json(MAPPING, None)
    if mapping is None:
        print("[proofread] 缺少 mapping.json；请先运行 make proofread-plan。", file=sys.stderr)
        return 2
    key = args.unit.replace("\\", "/").strip("/")
    if "/" not in key:
        print("用法：python3 tools/proofread.py show <年>/<地区>，例如 2024/辽宁", file=sys.stderr)
        return 2
    year_s, region = key.split("/", 1)
    try:
        year = int(year_s)
    except ValueError:
        print(f"[proofread] 年份非法：{year_s}", file=sys.stderr)
        return 2
    row = next((r for r in mapping["rows"] if r["year"] == year and r["region"] == region), None)
    if row is None:
        print(f"[proofread] 未找到：{key}", file=sys.stderr)
        return 1
    st = _load_json(STATUS, {"sets": {}}).get("sets", {}).get(key, {})
    print(f"# {year}/{region}")
    print(f"本仓库：{row['repo']}")
    print(f"校对状态：{st.get('status', '未开始' if row['by_source'] else '无源')}"
          f"（{st.get('date', '')}）")
    if st.get("note"):
        print(f"进度备注：{st['note']}")
    json_path = ROOT / "JSON" / str(year) / f"{year}_{region}.json"
    print(f"源 JSON：{_rel(json_path) if json_path.is_file() else '缺失（' + _rel(json_path) + '）'}")
    if not row["by_source"]:
        print("他源：无（无法交叉校对）")
    for source, e in row["by_source"].items():
        print(f"\n## {SOURCES[source]['label']}（{SOURCES[source]['range']}）")
        print(f"类型：{e.get('kind')}；置信度：{CONFIDENCE_LABEL.get(e.get('confidence'), e.get('confidence'))}")
        if e.get("note"):
            print(f"备注：{e['note']}")
        root = SOURCES[source]["root"]
        ren = _rename_index().get(source, {})
        for kind, norm in e.get("normalized", {}).items():
            path = f"{root}/{norm}"
            exists = "存在" if (ROOT / path).exists() else "缺失"
            orig = ren.get(norm)
            orig_txt = f"；原始名 {root}/{orig}" if orig and orig != norm else ""
            print(f"- {kind}: {path}（{exists}{orig_txt}）")

    items, resolved = parse_anomalies(year, region)
    print(f"\n## 异常记录（异常记录/{year}.md）")
    if not items and not resolved:
        print("无该卷记录。")
    else:
        if resolved:
            print(f"已解决：{resolved} 条")
        if items:
            print(f"未闭合：{len(items)} 条（交叉校对前逐条处理，能解决则改“已解决”）")
            for a in items:
                print(f"- [{a['status']}] 第 {a['number']} 题 / {a['category']}："
                      f"{a['problem']}")
        else:
            print("未闭合：0 条。")
    return 0


def cmd_tokens(args) -> int:
    for source in SOURCES:
        if not _is_source_dir_ready(source):
            continue
        print(f"## {source} ({SOURCES[source]['label']})")
        groups = scan_source_files(source)
        for (year, token), g in sorted(groups.items()):
            print(f"{year}\t{token}\t{_kind(source, g)}")
    return 0


def seed_status(mapping: dict) -> None:
    """为每个仓库卷补一条默认状态（不覆盖已有手工记录）。"""
    status = _load_json(STATUS, {"sets": {}})
    sets = status.setdefault("sets", {})
    for r in mapping["rows"]:
        key = f"{r['year']}/{r['region']}"
        default = "未开始" if r["by_source"] else "无源"
        if key not in sets:
            sets[key] = {"status": default, "date": "", "note": ""}
            continue
        cur = sets[key]
        # 仅修正“自动默认值”（无日期、无人工备注）的过时状态
        if (not cur.get("date") and not cur.get("note")
                and cur.get("status") in ("未开始", "无源")
                and cur.get("status") != default):
            cur["status"] = default
    _save_json(STATUS, status)


def cmd_plan(args) -> int:
    if not SOURCE_ROOT.is_dir():
        print("[proofread] 未找到 ProofreadPDF/；无法扫描源 PDF。", file=sys.stderr)
        return 2
    mapping = build_mapping()
    _save_json(MAPPING, mapping)
    seed_status(mapping)
    n_src = sum(len(r["by_source"]) for r in mapping["rows"])
    print(f"[proofread] 已生成 {MAPPING.relative_to(ROOT)}："
          f"{len(mapping['rows'])} 卷（有源 {n_src} 卷次）、"
          f"{len(mapping['source_only'])} 条仅源记录。")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="交叉校对基础设施（他源 PDF ↔ 本仓库试卷）")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_plan = sub.add_parser("plan", help="扫描源 PDF 与本仓库试卷，生成 mapping.json")
    p_plan.set_defaults(func=cmd_plan)
    p_ren = sub.add_parser("rename", help="源树内就地规范化重命名（默认预览）")
    p_ren.add_argument("--apply", action="store_true", help="真正执行重命名")
    p_ren.add_argument("--revert", action="store_true",
                       help="按 rename_manifest.json 回滚到原始文件名")
    p_ren.set_defaults(func=cmd_rename)
    p_tab = sub.add_parser("table", help="生成 交叉校对表.md")
    p_tab.add_argument("--check", action="store_true", help="只校验表格是否最新")
    p_tab.set_defaults(func=cmd_table)
    p_chk = sub.add_parser("check", help="校验 mapping / 源文件 / 仓库卷 / status")
    p_chk.set_defaults(func=cmd_check)
    p_show = sub.add_parser("show", help="查看某卷的源文件对应关系与校对状态")
    p_show.add_argument("unit", help="<年>/<地区>，例如 2024/辽宁")
    p_show.set_defaults(func=cmd_show)
    p_tok = sub.add_parser("tokens", help="打印解析出的年份/地区 token（调试）")
    p_tok.set_defaults(func=cmd_tokens)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

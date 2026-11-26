#!/usr/bin/env python3
"""tools/hqpics.py —— 高质量矢量配图（ProofreadPDF/HighQualityPic）辅助工具

`ProofreadPDF/HighQualityPic/<年>/<源卷文件夹>/<源卷>_p<页>_Fm<图号>.pdf`
是逐图导出的**矢量 PDF**（试题图与答案图分文件夹），来源包括：

- 朱玉亮 1978–2024：`Fm<图号>` 为全卷唯一，规范名 `<年>_<地区>_FmN.pdf`；
- 天利 2025–2026：`_p<页>_f<图号>` 按页编号，规范名保留页号
  `<年>_<地区>_p<页>_Fm<图号>.pdf`（避免跨页重名）。

本脚本：

- `plan`：扫描 → 按本仓库地区名匹配 → `交叉校对/hq_mapping.json` + `HighQualityPic表.md`
- `rename [--apply|--revert]`：文件夹/文件就地规范化（`<年>_<地区>` / `_答案`；
  文件按上述来源规则），原名称写入 `hq_rename_manifest.json`
- `match UNIT`：渲染 HQ 图与现有 `figs/`，一对一匹配，生成可编辑的
  `交叉校对/hq_figmap/<年>_<地区>.json` 与对照图（默认 `交叉校对/hq_compare/`，本地忽略）
- `apply UNIT [--write]`：按 figmap 中 `status: "apply"` 的条目替换配图：
  备份旧图到 `figs/.ocr_before/`、复制 HQ PDF、回填 `.tex` 尺寸、
  更新 `figures.manifest.json` / `figures.map.json`（本地忽略），并记 `hq_apply_log.json`
- `check`：校验 mapping/figmap/apply log 与文件存在性

约束：路径相对仓库根；临时/渲染文件只写 `/tmp/opencode/` 或本地忽略目录。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import figsize_automap as fa  # noqa: E402
from tools import proofread as pr  # noqa: E402

HQ_ROOT = ROOT / "ProofreadPDF" / "HighQualityPic"
HQ_MAPPING = ROOT / "交叉校对" / "hq_mapping.json"
HQ_RENAME = ROOT / "交叉校对" / "hq_rename_manifest.json"
HQ_TABLE = ROOT / "交叉校对" / "HighQualityPic表.md"
HQ_FIGMAP_DIR = ROOT / "交叉校对" / "hq_figmap"
HQ_COMPARE = ROOT / "交叉校对" / "hq_compare"
HQ_APPLY_LOG = ROOT / "交叉校对" / "hq_apply_log.json"
PAPERS = ROOT / "试卷"


def _load(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        sys.exit(f"[hqpics] JSON 解析失败：{path}: {exc}")


def _save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _today() -> str:
    return dt.date.today().isoformat()


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


# --------------------------------------------------------------------------- #
# 尺寸
# --------------------------------------------------------------------------- #
def pdf_size_cm(path: Path) -> tuple[float, float]:
    import pymupdf
    doc = pymupdf.open(str(path))
    try:
        r = doc[0].rect
        return round(r.width * 2.54 / 72, 2), round(r.height * 2.54 / 72, 2)
    finally:
        doc.close()


def _hq_source(year: int) -> tuple[str, str]:
    """HQ 矢量图来源：(source_key, label)。2025–2026 为天利，其余为朱玉亮。"""
    if year >= 2025:
        return "tian", pr.SOURCES["tian"]["label"]
    return "zhu", pr.SOURCES["zhu"]["label"]


def _norm_folder(year: int, region: str | None, token: str, answer: bool,
                 conf: str) -> str:
    name = region if (region and conf in ("exact", "alias", "manual")) else token
    safe = re.sub(r'[\\/:*?"<>|]', "_", name)
    return f"{year}_{safe}{'_答案' if answer else ''}"


def _norm_file(folder: str, original: str) -> str:
    stem = Path(original).stem
    # 天利 2025–2026：按页编号 _p<页>_f<图号>，规范名保留页号以避免跨页重名
    m_page = re.search(r"_p(\d+)_[fF](\d+)$", stem)
    if m_page:
        suffix = f"p{int(m_page.group(1)):02d}_Fm{int(m_page.group(2)):02d}"
        return f"{folder}_{suffix}.pdf"
    # 朱玉亮 1978–2024：Fm<图号> 全卷唯一
    m = re.search(r"Fm\d+(?:_\d+)*", stem, re.I)
    suffix = m.group(0) if m else re.sub(r"[^\w\u4e00-\u9fa5-]+", "_", stem)
    return f"{folder}_{suffix}.pdf"


# --------------------------------------------------------------------------- #
# 扫描与映射
# --------------------------------------------------------------------------- #
def _rename_index() -> dict[str, str]:
    """当前相对路径 → 原始相对路径（文件夹与文件通用）。"""
    m = _load(HQ_RENAME, {"version": 1, "renames": []})
    return {x["normalized"]: x["original"] for x in m.get("renames", [])}


def scan_hq() -> list[dict]:
    """返回 [{"year","folder","files":[{name,path,page,fm,w_cm,h_cm}],...}]。"""
    idx = _rename_index()
    out: list[dict] = []
    if not HQ_ROOT.is_dir():
        return out
    for ydir in sorted(HQ_ROOT.iterdir()):
        if not ydir.is_dir() or not ydir.name.isdigit():
            continue
        year = int(ydir.name)
        for d in sorted(ydir.iterdir()):
            if not d.is_dir():
                continue
            cur_dir_rel = f"{year}/{d.name}"
            orig_dir_rel = idx.get(cur_dir_rel, cur_dir_rel)
            orig_name = Path(orig_dir_rel).name
            yy, token, is_answer = pr.clean_token(orig_name)
            if yy is not None:
                year = yy
            files = []
            for pdf in sorted(d.glob("*.pdf")):
                cur_rel = f"{year}/{d.name}/{pdf.name}"
                orig_rel = idx.get(cur_rel, cur_rel)
                stem = Path(orig_rel).stem
                m_fm = re.search(r"Fm(\d+)", stem, re.I)
                if not m_fm:
                    # 天利按页编号：..._p<页>_f<图号>
                    m_fm = re.search(r"_f(\d+)$", stem, re.I)
                m_p = re.search(r"_p(\d+)_", stem)
                w, h = pdf_size_cm(pdf)
                files.append({
                    "name": pdf.name,
                    "path": _rel(pdf),
                    "current": cur_rel,
                    "original": orig_rel,
                    "page": int(m_p.group(1)) if m_p else None,
                    "fm": int(m_fm.group(1)) if m_fm else None,
                    "w_cm": w,
                    "h_cm": h,
                })
            out.append({
                "year": year,
                "folder": d.name,
                "folder_rel": _rel(d),
                "folder_hq": cur_dir_rel,
                "original_folder": orig_dir_rel,
                "token": token,
                "answer": is_answer,
                "files": files,
            })
    return out


def build_mapping() -> dict:
    repo = pr.scan_repo_sets()
    regions: dict[int, set[str]] = {}
    for (year, region) in repo:
        regions.setdefault(year, set()).add(region)
    overrides = _load(pr.OVERRIDES, {})

    rows: dict[tuple[int, str], dict] = {}
    for (year, region), info in repo.items():
        rows[(year, region)] = {
            "year": year,
            "region": region,
            "repo": info["path"],
            "by_kind": {},
            "confidence": "repo-only",
            "note": "",
        }
    source_only = []
    for item in scan_hq():
        year, token = item["year"], item["token"]
        region, conf, note = pr.match_token(token, year, regions.get(year, set()), overrides)
        norm = _norm_folder(year, region, token, item["answer"], conf)
        src_key, src_label = _hq_source(year)
        entry = {
            "source": src_key,
            "folder": item["folder"],
            "current_folder": item["folder_hq"],
            "original_folder": item["original_folder"],
            "normalized_folder": f"{year}/{norm}",
            "answer": item["answer"],
            "files": [
                {
                    **f,
                    "current": f["current"],
                    "normalized": f"{year}/{norm}/{_norm_file(norm, f['original'])}",
                }
                for f in item["files"]
            ],
            "confidence": conf,
            "note": note,
        }
        if region is None:
            source_only.append({
                "year": year,
                "source": src_key,
                "token": token,
                "answer": item["answer"],
                "folder": item["folder"],
                "current_folder": item["folder_hq"],
                "original_folder": item["original_folder"],
                "normalized_folder": entry["normalized_folder"],
                "files": entry["files"],
                "count": len(item["files"]),
                "note": note or "本仓库无对应 LaTeX 卷",
            })
            continue
        row = rows.get((year, region))
        if row is None:
            source_only.append({
                "year": year,
                "source": src_key,
                "token": token,
                "answer": item["answer"],
                "folder": item["folder"],
                "current_folder": item["folder_hq"],
                "original_folder": item["original_folder"],
                "normalized_folder": entry["normalized_folder"],
                "files": entry["files"],
                "count": len(item["files"]),
                "note": note or "映射到不存在的仓库卷",
            })
            continue
        kind = "answer" if item["answer"] else "question"
        row["by_kind"][kind] = entry
        if conf in ("uncertain", "fuzzy"):
            row["confidence"] = conf
            row["note"] = pr._join_notes(row["note"], f"{src_label}：{note or 'HQ 映射待确认'}")
        elif row["confidence"] == "repo-only":
            row["confidence"] = conf
        if entry.get("note"):
            row["note"] = pr._join_notes(row["note"], f"{src_label}：{entry['note']}")

    return {
        "version": 1,
        "generated": _today(),
        "source_root": "ProofreadPDF/HighQualityPic",
        "rows": sorted(rows.values(), key=lambda r: (r["year"], r["region"])),
        "source_only": sorted(source_only, key=lambda r: (r["year"], r["token"], r["answer"])),
    }


def _hq_counts(row: dict) -> tuple[int, int]:
    q = len(row.get("by_kind", {}).get("question", {}).get("files", []))
    a = len(row.get("by_kind", {}).get("answer", {}).get("files", []))
    return q, a


def render_table(mapping: dict) -> str:
    rows = mapping["rows"]
    total = len(rows)
    with_hq = [r for r in rows if r["by_kind"]]
    without_hq = [r for r in rows if not r["by_kind"]]
    q_total = sum(_hq_counts(r)[0] for r in rows)
    a_total = sum(_hq_counts(r)[1] for r in rows)
    source_only = mapping.get("source_only", [])
    applied = _load(HQ_APPLY_LOG, {"applied": []}).get("applied", [])
    applied_count: dict[tuple[int, str], int] = {}
    for e in applied:
        applied_count[(int(e["year"]), e["region"])] = applied_count.get((int(e["year"]), e["region"]), 0) + 1

    lines = ["# HighQualityPic 高质量配图表", ""]
    lines.append("> 由 `python3 tools/hqpics.py plan` 自动生成，**勿手改**；")
    lines.append("> 素材 `ProofreadPDF/HighQualityPic/` 为本地 Git 忽略目录。")
    lines.append("> HQ 来源：朱玉亮 1978–2024、天利 2025–2026；天利按页编号，"
                 "规范名保留页号 `_p<页>_Fm<图号>`。")
    lines.append("")
    lines.append(f"- 生成日期：{mapping.get('generated', _today())}")
    lines.append(f"- 本仓库卷数：{total}；有 HQ 配图：{len(with_hq)}；无 HQ：{len(without_hq)}")
    lines.append(f"- HQ 图文件：试题图 {q_total} 个、答案图 {a_total} 个")
    uniq = len({(x["year"], x["token"]) for x in source_only})
    lines.append(f"- 他源有、本仓库无：{len(source_only)} 个文件夹（{uniq} 套卷，按试题/答案计）")
    lines.append(f"- 已用 HQ 替换的图：{len(applied)} 张（逐卷见下表“已替换”）")
    lines.append("")
    lines.append("## 一、逐卷 HQ 配图")
    lines.append("")
    for year in sorted({r["year"] for r in rows}):
        yrows = [r for r in rows if r["year"] == year]
        lines.append(f"### {year} 年（{len(yrows)} 套）")
        lines.append("")
        lines.append("| 年份 | 地区 | 试题图 | 答案图 | 状态 | 已替换 | 备注 |")
        lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
        for r in yrows:
            q, a = _hq_counts(r)
            if q and a:
                st = "齐全"
            elif q or a:
                st = "部分"
            else:
                st = "无"
            done = applied_count.get((r["year"], r["region"]), 0)
            note = r.get("note", "")
            lines.append(f"| {r['year']} | {r['region']} | {q} | {a} | {st} | {done or '—'} | {note.replace('|', '\\|')} |")
        lines.append("")
    lines.append("## 二、HQ 有、本仓库无对应卷")
    lines.append("")
    if not source_only:
        lines.append("（无）")
    else:
        lines.append("| 年份 | 地区 token | 类型 | 文件夹 | 图数 | 备注 |")
        lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
        for s in source_only:
            lines.append(f"| {s['year']} | {s['token']} | {'答案' if s['answer'] else '试题'} | "
                         f"{s['folder']} | {s['count']} | {s.get('note', '').replace('|', '\\|')} |")
    lines.append("")
    lines.append("## 三、说明")
    lines.append("")
    lines.append("- `试题图` / `答案图` 为 HQ 文件夹中的 PDF 数量；0 表示该卷该类无 HQ。")
    lines.append("- 逐图对应题号需 `make hq-match UNIT=<年>/<地区>` 生成匹配草表并人工核对；")
    lines.append("  只有 `交叉校对/hq_figmap/<年>_<地区>.json` 中 `status: \"apply\"` 的条目会被 `hq-apply` 替换；"
                 "成功后自动改为 `applied`。")
    lines.append("- 替换时以 HQ PDF 的物理尺寸为准，并会同步 `.tex`、`figures.manifest.json`、`figures.map.json`。")
    lines.append("")
    return "\n".join(lines)


def cmd_plan(args) -> int:
    if not HQ_ROOT.is_dir():
        print("[hqpics] 未找到 ProofreadPDF/HighQualityPic/。", file=sys.stderr)
        return 2
    mapping = build_mapping()
    _save(HQ_MAPPING, mapping)
    HQ_TABLE.write_text(render_table(mapping), encoding="utf-8")
    print(f"[hqpics] 已生成 {HQ_MAPPING.relative_to(ROOT)} 与 {HQ_TABLE.relative_to(ROOT)}："
          f"{len(mapping['rows'])} 卷，{sum(1 for r in mapping['rows'] if r['by_kind'])} 卷有 HQ。")
    return 0


# --------------------------------------------------------------------------- #
# 重命名
# --------------------------------------------------------------------------- #
def _rewrite_tracked_paths() -> None:
    """重命名后同步 hq_figmap / hq_apply_log 中的 HQ 源路径。"""
    manifest = _load(HQ_RENAME, {"version": 1, "renames": []})
    mp = {x["original"]: x["normalized"]
          for x in manifest.get("renames", []) if x.get("kind") == "file"}
    prefix = "ProofreadPDF/HighQualityPic/"

    def fix(p: str | None) -> str | None:
        if not p or not p.startswith(prefix):
            return p
        rel = p[len(prefix):]
        return prefix + mp.get(rel, rel)

    if HQ_FIGMAP_DIR.is_dir():
        for f in sorted(HQ_FIGMAP_DIR.glob("*.json")):
            d = _load(f, {})
            changed = False
            for e in d.get("entries", []):
                new = fix(e.get("hq"))
                if new != e.get("hq"):
                    e["hq"] = new
                    changed = True
            if changed:
                _save(f, d)
    log = _load(HQ_APPLY_LOG, {"applied": []})
    changed = False
    for e in log.get("applied", []):
        new = fix(e.get("hq"))
        if new != e.get("hq"):
            e["hq"] = new
            changed = True
    if changed:
        _save(HQ_APPLY_LOG, log)


def cmd_rename(args) -> int:
    if not HQ_ROOT.is_dir():
        print("[hqpics] 未找到 HighQualityPic/，跳过。")
        return 0
    mapping = build_mapping()
    idx = _rename_index()
    manifest = _load(HQ_RENAME, {"version": 1, "renames": []})
    existing = {(x["original"], x["normalized"]) for x in manifest["renames"]}
    # (current_rel, normalized_rel, original_rel, kind)，均相对 HQ_ROOT
    renames: list[tuple[str, str, str, str]] = []
    for row in mapping["rows"]:
        for kind, e in row["by_kind"].items():
            renames.append((e["current_folder"], e["normalized_folder"],
                            e["original_folder"], "dir"))
            for f in e["files"]:
                renames.append((f["current"], f["normalized"], f["original"], "file"))
    for s in mapping["source_only"]:
        renames.append((s["current_folder"], s["normalized_folder"],
                        s["original_folder"], "dir"))
        for f in s.get("files", []):
            renames.append((f["current"], f["normalized"], f["original"], "file"))

    if args.revert:
        return _revert()

    # 冲突 / 重名检查（用当前路径作源；允许目录合并与“已移动”状态）
    conflicts = []
    targets = {}
    for cur, norm, orig, kind in renames:
        if cur == norm:
            continue
        src = HQ_ROOT / cur
        dst = HQ_ROOT / norm
        if not src.exists():
            if dst.exists():
                continue  # 部分完成：已在目标位置
            conflicts.append(f"源不存在：{cur}")
            continue
        if dst.exists() and dst != src:
            if kind == "dir" and dst.is_dir():
                overlap = ({p.name for p in src.iterdir()}
                           & {p.name for p in dst.iterdir()})
                if overlap:
                    conflicts.append(f"目录合并冲突：{norm} ← {', '.join(sorted(overlap))}")
            else:
                conflicts.append(f"目标已存在：{norm}")
        targets.setdefault(norm, []).append(cur)
    for norm, curs in targets.items():
        if len(curs) > 1:
            conflicts.append(f"目标重名：{norm} ← {', '.join(curs)}")
    if conflicts:
        print("[hqpics] 重命名中止：", file=sys.stderr)
        for c in conflicts:
            print("  - " + c, file=sys.stderr)
        return 2

    applied = 0
    # 先改文件，再改文件夹（避免路径失效）
    for cur, norm, orig, kind in sorted(renames, key=lambda x: 0 if x[3] == "file" else 1):
        if cur == norm:
            continue
        src = HQ_ROOT / cur
        dst = HQ_ROOT / norm
        if src.exists():
            if args.apply:
                dst.parent.mkdir(parents=True, exist_ok=True)
                if kind == "dir" and dst.exists() and dst.is_dir():
                    for p in list(src.iterdir()):
                        target = dst / p.name
                        if target.exists():
                            conflicts.append(f"合并冲突：{norm}/{p.name}")
                        else:
                            p.rename(target)
                    try:
                        src.rmdir()
                    except OSError:
                        pass
                else:
                    src.rename(dst)
                applied += 1
            else:
                print(f"  [预览] {kind}: {cur} → {norm}")
        elif not dst.exists():
            continue
        if (orig, norm) not in existing:
            manifest["renames"].append({"kind": kind, "original": orig, "normalized": norm, "date": _today()})
            existing.add((orig, norm))
    if args.apply:
        _save(HQ_RENAME, manifest)
        _rewrite_tracked_paths()
        m2 = build_mapping()
        _save(HQ_MAPPING, m2)
        HQ_TABLE.write_text(render_table(m2), encoding="utf-8")
        print(f"[hqpics] 已重命名 {applied} 项；已更新 mapping/表。")
    else:
        print(f"[hqpics] 预览 {len([x for x in renames if x[0] != x[1]])} 项；加 --apply 执行。")
    return 0


def _revert() -> int:
    manifest = _load(HQ_RENAME, {"version": 1, "renames": []})
    renames = manifest.get("renames", [])
    if not renames:
        print("[hqpics] 无可回滚记录。")
        return 0
    conflicts = []
    for x in renames:
        src = HQ_ROOT / x["normalized"]
        dst = HQ_ROOT / x["original"]
        if not src.exists():
            conflicts.append(f"当前不存在：{x['normalized']}")
        if dst.exists() and dst != src:
            conflicts.append(f"原名被占用：{x['original']}")
    if conflicts:
        print("[hqpics] 回滚中止：", file=sys.stderr)
        for c in conflicts:
            print("  - " + c, file=sys.stderr)
        return 2
    for x in reversed(renames):
        src = HQ_ROOT / x["normalized"]
        dst = HQ_ROOT / x["original"]
        if src.exists():
            src.rename(dst)
    manifest["renames"] = []
    _save(HQ_RENAME, manifest)
    _save(HQ_MAPPING, build_mapping())
    print(f"[hqpics] 已回滚 {len(renames)} 项。")
    return 0


# --------------------------------------------------------------------------- #
# 匹配
# --------------------------------------------------------------------------- #
def _fig_kind(stem: str) -> str:
    return "answer" if re.search(r"(?i)(?:^|[_\-]|\d)an\d*$", stem) else "question"


def _find_row(mapping: dict, year: int, region: str) -> dict | None:
    return next((r for r in mapping["rows"] if r["year"] == year and r["region"] == region), None)


def _parse_unit(unit: str) -> tuple[int, str]:
    key = unit.replace("\\", "/").strip("/")
    if "/" not in key:
        raise SystemExit("用法：<年>/<地区>，例如 1978/全国")
    y, r = key.split("/", 1)
    return int(y), r


def _render_compare(hq: Path, target: Path, out: Path, label: str, tmp: Path) -> None:
    from PIL import Image
    left = fa.load_image(hq, tmp)
    right = fa.load_image(target, tmp)
    h = 320
    def fit(im):
        w = max(1, int(im.width * h / im.height))
        return im.resize((w, h), Image.BILINEAR)
    left, right = fit(left), fit(right)
    canvas = Image.new("L", (left.width + right.width + 20, h + 30), 255)
    canvas.paste(left, (0, 30))
    canvas.paste(right, (left.width + 20, 30))
    canvas.save(out)


def cmd_match(args) -> int:
    mapping = _load(HQ_MAPPING, None)
    if mapping is None:
        print("[hqpics] 缺少 hq_mapping.json；请先运行 make hq-plan。", file=sys.stderr)
        return 2
    year, region = _parse_unit(args.unit)
    row = _find_row(mapping, year, region)
    if row is None or not row["by_kind"]:
        print(f"[hqpics] {year}/{region} 无 HQ 配图。", file=sys.stderr)
        return 1
    unit_dir = PAPERS / str(year) / region
    figs_dir = unit_dir / "figs"
    if not figs_dir.is_dir():
        print(f"[hqpics] 本仓库卷无 figs/：{unit_dir}", file=sys.stderr)
        return 1
    figs = [p for p in sorted(figs_dir.iterdir())
            if p.is_file() and p.suffix.lower() in (".png", ".jpg", ".jpeg", ".svg", ".pdf")]
    by_kind = {"question": [], "answer": []}
    for p in figs:
        by_kind[_fig_kind(p.stem)].append(p)

    out = {"version": 1, "year": year, "region": region, "generated": _today(), "entries": []}
    compare_dir = HQ_COMPARE / f"{year}_{region}"
    if args.compare_dir:
        compare_dir = Path(args.compare_dir)
    compare_dir.mkdir(parents=True, exist_ok=True)
    tmp = Path("/tmp/opencode/hqpics_match")
    tmp.mkdir(parents=True, exist_ok=True)

    for kind in ("question", "answer"):
        hqfiles = row.get("by_kind", {}).get(kind, {}).get("files", [])
        targets = by_kind[kind]
        if not hqfiles and not targets:
            continue
        # 特征
        hfeat = []
        for f in hqfiles:
            vec, aspect = fa.feature(ROOT / f["path"], tmp)
            hfeat.append((vec, aspect))
        tfeat = []
        for t in targets:
            vec, aspect = fa.feature(t, tmp)
            tfeat.append((vec, aspect))
        n, m = len(hqfiles), len(targets)
        if n and m:
            size = n + m
            cost = [[0.0] * size for _ in range(size)]
            scores = {}
            for i in range(n):
                for j in range(m):
                    sim = float((hfeat[i][0] * tfeat[j][0]).sum())
                    scores[(i, j)] = sim
                    cost[i][j] = -sim
            assign = fa.hungarian_min(cost)
        else:
            assign, scores = {}, {}
        used = set()
        for i in range(n):
            j = assign.get(i)
            f = hqfiles[i]
            entry = {
                "kind": kind,
                "hq": f["path"],
                "hq_stem": Path(f["path"]).stem,
                "page": f.get("page"),
                "fm": f.get("fm"),
                "hq_w_cm": f["w_cm"],
                "hq_h_cm": f["h_cm"],
                "target": None,
                "target_stem": None,
                "score": None,
                "status": "unmatched",
                "crop": None,
                "note": "",
            }
            if j is not None and j < m:
                t = targets[j]
                used.add(j)
                sim = scores.get((i, j), 0.0)
                entry.update({
                    "target": _rel(t),
                    "target_stem": t.stem,
                    "score": round(sim, 3),
                    "status": "auto" if sim >= args.auto_threshold else "review",
                })
                if args.mark_apply:
                    entry["status"] = "apply"
                cmp_path = compare_dir / f"{kind}__{Path(f['path']).stem}__{t.stem}.png"
                _render_compare(ROOT / f["path"], t, cmp_path, f"{f['path']} -> {t.name}", tmp)
            out["entries"].append(entry)
        # 未匹配的现有图
        for j, t in enumerate(targets):
            if j not in used:
                out.setdefault("unmatched_figs", []).append({"kind": kind, "target": _rel(t)})
    # 未匹配 HQ 已作为 status=unmatched 的 entry 保留
    hqmap = HQ_FIGMAP_DIR / f"{year}_{region}.json"
    if hqmap.exists() and not args.force:
        old = _load(hqmap, {})
        if any(e.get("status") == "applied" for e in old.get("entries", [])):
            print(f"[hqpics] {hqmap.relative_to(ROOT)} 已有 applied 条目；"
                  f"如确需重新匹配，加 --force。", file=sys.stderr)
            return 2
    _save(hqmap, out)
    print(f"[hqpics] 已生成 {hqmap.relative_to(ROOT)}；对照图 {compare_dir}")
    print(f"  entries={len(out['entries'])} auto={sum(1 for e in out['entries'] if e['status']=='auto')} "
          f"review={sum(1 for e in out['entries'] if e['status']=='review')} "
          f"unmatched={sum(1 for e in out['entries'] if e['status']=='unmatched')}")
    print("  请查看对照图，确认后把对应条目的 status 改为 \"apply\"，再运行 make hq-apply UNIT=…")
    return 0


# --------------------------------------------------------------------------- #
# 替换（应用 figmap）
# --------------------------------------------------------------------------- #
def _crop_pdf(src: Path, dst: Path, rect: list[float]) -> None:
    """rect = [x0,y0,x1,y1] 归一化（0–1，左上为原点）。"""
    import pymupdf
    doc = pymupdf.open(str(src))
    try:
        r = doc[0].rect
        clip = pymupdf.Rect(
            r.x0 + rect[0] * r.width, r.y0 + rect[1] * r.height,
            r.x0 + rect[2] * r.width, r.y0 + rect[3] * r.height,
        )
        out = pymupdf.open()
        page = out.new_page(width=clip.width, height=clip.height)
        page.show_pdf_page(page.rect, doc, 0, clip=clip)
        out.save(str(dst))
        out.close()
    finally:
        doc.close()


def _split_opts(opts: str) -> list[str]:
    """按顶层逗号切分命令选项，保留 {…}/[…] 内的逗号。"""
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    for ch in opts:
        if ch in "{[":
            depth += 1
        elif ch in "}]":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf).strip())
    return [p for p in parts if p]


def _strip_size_opts(opts: str) -> str:
    parts = _split_opts(opts)
    keep = [x for x in parts if not re.match(r"^(w|h|width|height)\s*=", x)]
    return ", ".join(keep)


def _take_braced(s: str, i: int) -> tuple[str | None, int]:
    if i >= len(s) or s[i] != "{":
        return None, i
    depth = 0
    for j in range(i, len(s)):
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0:
                return s[i + 1:j], j + 1
    return None, i


def _replace_inner(inner: str, old_stem: str, new_stem: str) -> str:
    if "\\includesvg" in inner:
        return f"figs/{new_stem}.pdf"
    return re.sub(rf"figs/{re.escape(old_stem)}(?:\.[A-Za-z0-9]+)?",
                  f"figs/{new_stem}.pdf", inner)


MULTI_N = {
    "twopicture": 2, "threepicture": 3, "fourpicture": 4, "fivepicture": 5,
    "sixpicture": 6, "sevenpicture": 7, "eightpicture": 8, "ninepicture": 9,
    "fourchoices": 4,
}


def _set_per_image_size(opts: str, letter: str, w: float, h: float) -> str:
    parts = _split_opts(opts)
    keep = [x for x in parts
            if not re.match(rf"^(w|h|width|height){letter}\s*=", x, re.I)]
    keep.extend([f"w{letter}={w:.2f}cm", f"h{letter}={h:.2f}cm"])
    return ", ".join(keep)


def _rewrite_multi(text: str, cmd: str, nargs: int, old_stem: str,
                   new_stem: str, w: float, h: float) -> tuple[str, int]:
    count = 0
    pat = re.compile(rf"\\{cmd}(?![A-Za-z])(?:\[([^\]]*)\])?")
    pos = 0
    out: list[str] = []
    while True:
        m = pat.search(text, pos)
        if not m:
            out.append(text[pos:])
            break
        out.append(text[pos:m.start()])
        j = m.end()
        args: list[str] = []
        ok = True
        for _ in range(nargs):
            while j < len(text) and text[j] in " \t\n":
                j += 1
            arg, j2 = _take_braced(text, j)
            if arg is None:
                ok = False
                break
            args.append(arg)
            j = j2
        if not ok:
            out.append(text[m.start():m.end()])
            pos = m.end()
            continue
        opts = m.group(1) or ""
        if cmd == "fourchoices" and "ispicture" not in opts:
            out.append(text[m.start():j])
            pos = j
            continue
        changed = False
        for idx, arg in enumerate(args):
            if re.search(rf"figs/{re.escape(old_stem)}(?![0-9A-Za-z])", arg):
                args[idx] = _replace_inner(arg, old_stem, new_stem)
                opts = _set_per_image_size(opts, chr(ord('A') + idx), w, h)
                changed = True
        if changed:
            count += 1
            new_opts = f"[{opts}]" if opts else ""
            out.append(f"\\{cmd}{new_opts}" + "".join("{" + a + "}" for a in args))
        else:
            out.append(text[m.start():j])
        pos = j
    return "".join(out), count


def _rewrite_figure_refs(text: str, old_stem: str, new_stem: str,
                         w: float, h: float) -> tuple[str, int]:
    text, n = _rewrite_onepicture(text, old_stem, new_stem, w, h)
    if n:
        return text, n
    for cmd, nargs in MULTI_N.items():
        text, n = _rewrite_multi(text, cmd, nargs, old_stem, new_stem, w, h)
        if n:
            return text, n
    return text, 0


def _rewrite_onepicture(text: str, old_stem: str, new_stem: str, w: float, h: float) -> tuple[str, int]:
    count = 0
    pat = re.compile(r"\\onepicture(?:\[([^\]]*)\])?\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}")

    def repl(m):
        nonlocal count
        opts = m.group(1) or ""
        inner = m.group(2)
        if not re.search(rf"figs/{re.escape(old_stem)}(?![0-9A-Za-z])", inner):
            return m.group(0)
        new_inner = _replace_inner(inner, old_stem, new_stem)
        kept = _strip_size_opts(opts)
        new_opts = ", ".join(x for x in (kept, f"w={w:.2f}cm", f"h={h:.2f}cm") if x)
        count += 1
        return f"\\onepicture[{new_opts}]{{{new_inner}}}"

    return pat.sub(repl, text), count


def _update_manifest(unit_dir: Path, old_stem: str, new_stem: str, hq_path: Path,
                     w: float, h: float) -> None:
    new_target = f"{_rel(unit_dir)}/figs/{new_stem}.pdf"
    # figures.map.json
    mp = unit_dir / "figures.map.json"
    if mp.exists():
        data = _load(mp, {"entries": []})
        found = False
        for e in data.get("entries", []):
            t = e.get("target", "")
            if Path(t).stem == old_stem and Path(t).parent.name == "figs":
                e["target"] = new_target
                e.pop("candidate", None)
                e["final_width_cm"] = w
                e["final_height_cm"] = h
                e["notes"] = "HighQualityPic 矢量 PDF（按 HQ 物理尺寸）"
                found = True
        if not found:
            data.setdefault("entries", []).append({
                "target": new_target,
                "final_width_cm": w,
                "final_height_cm": h,
                "notes": "HighQualityPic 矢量 PDF（按 HQ 物理尺寸）",
            })
        _save(mp, data)
    # figures.manifest.json
    mf = unit_dir / "figures.manifest.json"
    if mf.exists():
        data = _load(mf, {"version": 1, "entries": []})
        found = False
        for e in data.get("entries", []):
            t = e.get("target", "")
            if Path(t).stem == old_stem and Path(t).parent.name == "figs":
                e["target"] = new_target
                e["strategy"] = "hq"
                e["asset"] = {"kind": "pdf", "aspect": round(w / h, 6) if h else None}
                e["source"] = {
                    "pdf": _rel(hq_path),
                    "page": 0,
                    "kind": "hq-pdf",
                    "width_cm": w,
                    "height_cm": h,
                    "aspect": round(w / h, 6) if h else None,
                }
                e["final"] = {"width_cm": w, "height_cm": h, "basis": "hq-pdf",
                              "reference": "width", "capped": False}
                e["width_cm"] = w
                e["height_cm"] = h
                e["status"] = "hq"
                e["notes"] = "HighQualityPic 矢量 PDF（按 HQ 物理尺寸）"
                found = True
        if not found:
            data.setdefault("entries", []).append({
                "target": new_target, "strategy": "hq",
                "asset": {"kind": "pdf", "aspect": round(w / h, 6) if h else None},
                "source": {"pdf": _rel(hq_path), "page": 0, "kind": "hq-pdf",
                           "width_cm": w, "height_cm": h,
                           "aspect": round(w / h, 6) if h else None},
                "final": {"width_cm": w, "height_cm": h, "basis": "hq-pdf",
                          "reference": "width", "capped": False},
                "width_cm": w, "height_cm": h, "status": "hq",
                "notes": "HighQualityPic 矢量 PDF（按 HQ 物理尺寸）",
            })
        _save(mf, data)


def cmd_apply(args) -> int:
    year, region = _parse_unit(args.unit)
    unit_dir = PAPERS / str(year) / region
    figmap = HQ_FIGMAP_DIR / f"{year}_{region}.json"
    if not figmap.exists():
        print(f"[hqpics] 缺少匹配草表：{figmap}；请先 make hq-match UNIT={year}/{region}", file=sys.stderr)
        return 2
    data = _load(figmap, {"entries": []})
    tex_path = unit_dir / f"{region}.tex"
    if not tex_path.exists():
        print(f"[hqpics] 缺少 {tex_path}", file=sys.stderr)
        return 2
    text = tex_path.read_text(encoding="utf-8")
    log = _load(HQ_APPLY_LOG, {"version": 1, "applied": []})
    applied, skipped = 0, []
    figs_dir = unit_dir / "figs"
    backup = figs_dir / ".ocr_before"
    figmap_changed = False
    for e in data.get("entries", []):
        if e.get("status") != "apply":
            continue
        if not e.get("target") or not e.get("target_stem"):
            skipped.append((e.get("hq"), "未指定 target_stem"))
            continue
        hq_path = ROOT / e["hq"]
        old_stem = Path(e["target"]).stem
        new_stem = e["target_stem"]
        if not hq_path.exists():
            skipped.append((e["hq"], "HQ 文件不存在"))
            continue
        # 改名时避免覆盖另一张已有图
        if new_stem != old_stem:
            clash = [p.name for p in figs_dir.glob(f"{new_stem}.*") if p.is_file()]
            if clash:
                skipped.append((e["hq"], f"目标题号 {new_stem} 已有图片：{', '.join(clash)}"))
                continue
        w, h = e["hq_w_cm"], e["hq_h_cm"]
        if e.get("crop") and not args.write:
            x0, y0, x1, y1 = e["crop"]
            w = round(w * (x1 - x0), 2)
            h = round(h * (y1 - y0), 2)
        new_pdf = figs_dir / f"{new_stem}.pdf"
        # 先确认是本项目支持自动更新的图片命令；不支持则不动任何文件
        new_text, n = _rewrite_figure_refs(text, old_stem, new_stem, w, h)
        if n == 0:
            skipped.append((e["hq"], "未找到可自动更新的图片引用（需人工处理）"))
            continue
        # 同一张图若还有其它未支持的引用（多图/图片选项等），整条跳过，避免留下失效路径
        if re.search(rf"figs/{re.escape(old_stem)}(?![0-9A-Za-z])", new_text):
            skipped.append((e["hq"], "仍有未支持的图片引用（多图/图片选项等），需人工处理"))
            continue
        if args.write:
            backup.mkdir(parents=True, exist_ok=True)
            for p in figs_dir.glob(f"{old_stem}.*"):
                if p.is_file():
                    shutil.move(str(p), str(backup / p.name))
            if e.get("crop"):
                _crop_pdf(hq_path, new_pdf, e["crop"])
                w, h = pdf_size_cm(new_pdf)
                new_text, _ = _rewrite_figure_refs(text, old_stem, new_stem, w, h)
            else:
                shutil.copy2(hq_path, new_pdf)
            _update_manifest(unit_dir, old_stem, new_stem, hq_path, w, h)
            new_rel = f"{_rel(unit_dir)}/figs/{new_stem}.pdf"
            # 同一目标只保留最新一条日志，避免重复 apply 产生重复记录
            log["applied"] = [x for x in log.get("applied", [])
                              if not (x.get("year") == year and x.get("region") == region
                                      and x.get("new") == new_rel)]
            log["applied"].append({
                "date": _today(), "year": year, "region": region,
                "kind": e.get("kind"), "hq": e["hq"],
                "old": e.get("target"), "new": new_rel,
                "width_cm": w, "height_cm": h, "crop": e.get("crop"),
            })
            e["status"] = "applied"
            figmap_changed = True
        text = new_text
        applied += 1
        print(f"  {'[写入]' if args.write else '[预览]'} {e.get('target')} → figs/{new_stem}.pdf "
              f"({w:.2f}×{h:.2f}cm)")
    if skipped:
        print("[hqpics] 跳过（需人工处理）：", file=sys.stderr)
        for hq, why in skipped:
            print(f"  - {hq}: {why}", file=sys.stderr)
    if args.write:
        tex_path.write_text(text, encoding="utf-8")
        if figmap_changed:
            _save(figmap, data)
        _save(HQ_APPLY_LOG, log)
        print(f"[hqpics] 已替换 {applied} 张；日志 {HQ_APPLY_LOG.relative_to(ROOT)}")
    else:
        print(f"[hqpics] 预览 {applied} 张；加 --write 执行。")
    return 0


# --------------------------------------------------------------------------- #
# 校验
# --------------------------------------------------------------------------- #
def cmd_check(args) -> int:
    errs, warns = [], []
    mapping = _load(HQ_MAPPING, None)
    if mapping is None:
        print("[hqpics] 缺少 hq_mapping.json；请先 make hq-plan。", file=sys.stderr)
        return 2
    for row in mapping["rows"]:
        unit = PAPERS / str(row["year"]) / row["region"]
        if not unit.is_dir():
            errs.append(f"试卷不存在：{row['year']}/{row['region']}")
        for kind, e in row.get("by_kind", {}).items():
            for f in e.get("files", []):
                if HQ_ROOT.is_dir() and not (ROOT / f["path"]).exists() \
                        and not (ROOT / f.get("original", "")).exists():
                    errs.append(f"HQ 文件不存在：{f['path']}")

    # 总表必须与 mapping + apply log 同步（不依赖本地 HQ 是否还在）
    table_text = HQ_TABLE.read_text(encoding="utf-8") if HQ_TABLE.exists() else ""
    if table_text != render_table(mapping):
        warns.append("HighQualityPic表.md 未刷新（make hq-plan）")

    # 匹配草表
    status_ok = {"auto", "review", "unmatched", "apply", "applied"}
    if HQ_FIGMAP_DIR.is_dir():
        for f in sorted(HQ_FIGMAP_DIR.glob("*.json")):
            d = _load(f, {})
            key = f.stem
            for e in d.get("entries", []):
                if e.get("status") not in status_ok:
                    warns.append(f"{key} 的 figmap 状态非法：{e.get('status')!r}")
                if HQ_ROOT.is_dir() and e.get("hq") and not (ROOT / e["hq"]).exists():
                    warns.append(f"{key} 的 HQ 源文件不存在：{e['hq']}")
                if e.get("status") == "applied" and e.get("target_stem"):
                    new = PAPERS / str(d.get("year")) / str(d.get("region")) / "figs" / f"{e['target_stem']}.pdf"
                    if not new.exists():
                        warns.append(f"{key} 已标记 applied 但新图不存在：{new}")

    # HQ 重命名清单
    if HQ_ROOT.is_dir():
        manifest = _load(HQ_RENAME, {"renames": []})
        for x in manifest.get("renames", []):
            if not (HQ_ROOT / x["normalized"]).exists():
                warns.append(f"重命名清单中的规范化路径不存在：{x['normalized']}")

    # 替换日志
    for e in _load(HQ_APPLY_LOG, {"applied": []}).get("applied", []):
        if not (ROOT / e["new"]).exists():
            warns.append(f"apply 日志中的新图不存在：{e['new']}")
        if HQ_ROOT.is_dir() and e.get("hq") and not (ROOT / e["hq"]).exists():
            warns.append(f"apply 日志中的 HQ 源文件不存在：{e['hq']}")

    for w in warns:
        print("[hqpics] 警告：" + w)
    if errs:
        print("[hqpics] 校验失败：", file=sys.stderr)
        for e in errs:
            print("  - " + e, file=sys.stderr)
        return 1
    print(f"[hqpics] 校验通过：{len(mapping['rows'])} 卷。")
    return 0

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="HighQualityPic 高质量配图辅助工具")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan", help="扫描 HQ → hq_mapping.json + 表")
    p.set_defaults(func=cmd_plan)
    p = sub.add_parser("rename", help="HQ 文件夹/文件规范化重命名（默认预览）")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--revert", action="store_true")
    p.set_defaults(func=cmd_rename)
    p = sub.add_parser("match", help="为某卷生成 HQ↔figs 匹配草表与对照图")
    p.add_argument("unit")
    p.add_argument("--auto-threshold", type=float, default=0.8)
    p.add_argument("--mark-apply", action="store_true", help="把所有匹配条目标为 apply（慎用）")
    p.add_argument("--force", action="store_true", help="已有 applied 条目时仍重新生成 figmap")
    p.add_argument("--compare-dir", help="对照图输出目录（默认 交叉校对/hq_compare/）")
    p.set_defaults(func=cmd_match)
    p = sub.add_parser("apply", help="按 figmap 的 apply 条目替换配图")
    p.add_argument("unit")
    p.add_argument("--write", action="store_true")
    p.set_defaults(func=cmd_apply)
    p = sub.add_parser("check", help="校验 mapping/表/日志")
    p.set_defaults(func=cmd_check)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

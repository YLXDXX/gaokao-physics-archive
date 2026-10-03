#!/usr/bin/env python3
"""tools/gen_index.py —— 试卷索引 / 进度文档的生成与共享库

随着年份与地区增多，`README.md`、`进度记录.md`、`试卷/<年>/README.md` 与
`异常记录/<年>.md` 容易相互脱节。本脚本以**文件系统为事实来源**，提供：

- `scan_papers()`：扫描 `试卷/<年>/<地区>/`，统计题数、图片数、是否有 TikZ / 裁剪
  recipe、两版 PDF 是否生成、是否仍有“缺详解”占位等；
- `parse_progress()`：解析 `进度记录.md`（人工维护的**逐年明细表**）；
- `check()`：校验进度表与 `试卷/` 目录**双向一致**、状态取值合法、题数与实际相符、
  异常记录链接可达，并检查 `异常记录/<年>.md` 的表头与状态；
- `write()`：生成/刷新 `试卷/<年>/README.md`（年份索引）与 `README.md` 的进度概要块，
  并回填 `进度记录.md` 的题数列。

用法::

    python3 tools/gen_index.py            # 打印各年份概要（status）
    python3 tools/gen_index.py --check    # 校验（make check-docs）
    python3 tools/gen_index.py --write    # 生成年份索引 / 刷新概要（make index）

供 `tools/check_docs.py`、`tools/status.py` 复用其函数。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAPERS_DIR = ROOT / "试卷"
ANOM_DIR = ROOT / "异常记录"
PROGRESS = ROOT / "进度记录.md"
README = ROOT / "README.md"

# 进度状态枚举（`进度记录.md` 的表头说明须与之一致）
STATUS_ENUM = ["未开始", "材料就绪", "制作中", "已编译", "已自查", "待复核", "已完成", "回忆版"]
STATUS_OK = set(STATUS_ENUM)
# 异常记录状态枚举（`异常记录/<年>.md` 的“状态”列）
ANOM_STATUS = ["待处理", "处理中", "已解决", "待人工核验", "待补充"]
ANOM_OK = set(ANOM_STATUS)
# 异常记录表头列（允许两种：含“类别”的完整表 / 简化表）
ANOM_COLS = ["地区", "题号", "类别", "问题", "处理建议", "状态"]

README_START = "<!-- PROGRESS:START -->"
README_END = "<!-- PROGRESS:END -->"


# ---------------------------------------------------------------------------
# 扫描
# ---------------------------------------------------------------------------
def _is_paper_dir(d: Path) -> bool:
    return d.is_dir() and any(p.name != "TikZ" and p.suffix == ".tex"
                              for p in d.glob("*.tex"))


def _main_tex(rdir: Path) -> Path | None:
    cands = [p for p in rdir.glob("*.tex") if p.parent.name != "TikZ"]
    if not cands:
        return None
    # 优先与目录同名的 .tex
    for p in cands:
        if p.stem == rdir.name:
            return p
    return sorted(cands)[0]


def scan_papers(root: Path = ROOT) -> dict[str, dict[str, dict]]:
    """返回 {年: {地区: facts}}。facts 见模块说明。"""
    out: dict[str, dict[str, dict]] = {}
    base = root / "试卷"
    if not base.is_dir():
        return out
    for ydir in sorted(base.iterdir()):
        if not ydir.is_dir():
            continue
        for rdir in sorted(ydir.iterdir()):
            if not _is_paper_dir(rdir):
                continue
            tex = _main_tex(rdir)
            txt = tex.read_text(encoding="utf-8") if tex else ""
            figs_dir = rdir / "figs"
            tikz_dir = rdir / "TikZ"
            facts = {
                "year": ydir.name,
                "region": rdir.name,
                "dir": str(rdir.relative_to(root)),
                "tex": str(tex.relative_to(root)) if tex else None,
                "questions": len(re.findall(r"^%%\s*number\s*[:：]", txt, re.M)),
                "figs": len(list(figs_dir.glob("*"))) if figs_dir.is_dir() else 0,
                "tikz": bool(list(tikz_dir.glob("*.tex"))) if tikz_dir.is_dir() else False,
                "recrop": (rdir / ".recrop.json").exists(),
                "student": (rdir / f"{rdir.name}_学生版.pdf").exists(),
                "teacher": (rdir / f"{rdir.name}_教师版.pdf").exists(),
                "placeholder": len(re.findall(r"本题原卷及材料中未提供详解", txt)),
                "recalled": bool(re.search(r"^%%\s*recalled\s*[:：]\s*(?:true|是|1)\b",
                                           txt, re.M | re.I)),
                "papertype": (re.search(r"^%%\s*paperType\s*[:：]\s*(.+)$", txt, re.M).group(1).strip()
                              if re.search(r"^%%\s*paperType\s*[:：]\s*(.+)$", txt, re.M) else ""),
            }
            facts["derived"] = _derive_status(facts)
            out.setdefault(ydir.name, {})[rdir.name] = facts
    return out


def _derive_status(f: dict) -> str:
    if f["student"] and f["teacher"]:
        return "已编译"
    if f["questions"]:
        return "制作中"
    return "材料就绪"


# ---------------------------------------------------------------------------
# 解析 进度记录.md
# ---------------------------------------------------------------------------
def parse_progress(path: Path = PROGRESS) -> dict[str, dict]:
    """解析 进度记录.md，返回 {年: {"rows": {地区: {题数,状态,说明,异常}}, "heading": ...}}"""
    years: dict[str, dict] = {}
    if not path.exists():
        return years
    cur: str | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        # 年份小节标题：普通年份 `### 2020 年（…）`；特殊桶 `### 2000年以前（…）`
        m = re.match(r"^###\s*(\d{4}年以前|\d{4})", line)
        if m:
            cur = m.group(1)
            years[cur] = {"heading": line.strip(), "rows": {}}
            continue
        if cur is None or not line.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3 or set(cells[0]) <= set(":-") or cells[0] in ("地区", "年份"):
            continue
        row = {
            "region": cells[0],
            "题数": cells[1] if len(cells) > 1 else "",
            "status": cells[2] if len(cells) > 2 else "",
            "note": cells[3] if len(cells) > 3 else "",
            "anomaly_raw": cells[4] if len(cells) > 4 else "",
        }
        link = re.search(r"\]\(([^)]+)\)", row["anomaly_raw"])
        row["anomaly"] = link.group(1) if link else ""
        years[cur]["rows"][row["region"]] = row
    return years


# ---------------------------------------------------------------------------
# 解析 异常记录/<年>.md
# ---------------------------------------------------------------------------
def parse_anomaly(path: Path) -> dict:
    """返回 {status_values, headers, has_category, title_ok, rows}"""
    res = {"status_values": [], "headers": [], "has_category": False,
           "title_ok": False, "rows": []}
    if not path.exists():
        return res
    lines = path.read_text(encoding="utf-8").splitlines()
    if lines and re.match(r"^#\s*异常记录", lines[0]):
        res["title_ok"] = True
    for line in lines:
        if not line.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if any(c in ANOM_COLS for c in cells) and "状态" in cells:
            res["headers"].append(cells)
            if "类别" in cells:
                res["has_category"] = True
        elif cells and cells[-1] in ANOM_OK:
            res["status_values"].append(cells[-1])
            res["rows"].append({
                "region": cells[0] if len(cells) > 0 else "",
                "question": cells[1] if len(cells) > 1 else "",
                "category": cells[2] if len(cells) > 2 and cells[2] in ANOM_CATEGORIES else "",
                "status": cells[-1],
                "problem": cells[3] if len(cells) > 3 else "",
            })
    return res


# 异常类别枚举（与 异常记录/_模板.md 一致）
ANOM_CATEGORIES = ["缺题", "缺图", "缺详解", "详解", "来源", "公式", "单位", "文字", "答案",
                   "元数据", "图片编号", "复合图", "理综", "回忆版", "平台数据", "其它"]


def anomaly_tally(root: Path = ROOT) -> dict[str, dict]:
    """汇总各年异常记录：闭合/未闭合计数与未闭合明细。"""
    out: dict[str, dict] = {}
    for year in sorted(scan_papers(root)):
        info = parse_anomaly(root / "异常记录" / f"{year}.md")
        counts: dict[str, int] = {}
        opened = []
        for r in info["rows"]:
            counts[r["status"]] = counts.get(r["status"], 0) + 1
            if r["status"] != "已解决":
                opened.append(r)
        out[year] = {"counts": counts, "open": opened, "total": len(info["rows"])}
    return out


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------
def check(root: Path = ROOT, verbose: bool = True) -> list[str]:
    errs: list[str] = []
    papers = scan_papers(root)
    progress = parse_progress(root / "进度记录.md")

    def log(*a):
        if verbose:
            print(*a)

    # 1. 年份双向一致
    for year in sorted(papers):
        if year not in progress:
            errs.append(f"进度记录.md 缺少年份小节：### {year} 年")
    for year in sorted(progress):
        if year not in papers:
            errs.append(f"进度记录.md 中的年份 {year} 在 试卷/ 下不存在")
            continue
        rows = progress[year]["rows"]
        for region, f in papers[year].items():
            if region not in rows:
                errs.append(f"进度记录.md 缺 {year}/{region} 一行")
                continue
            r = rows[region]
            if r["题数"] and int(re.sub(r"\D", "", r["题数"]) or 0) != f["questions"]:
                errs.append(
                    f"{year}/{region} 题数不符：进度表 {r['题数']} vs 实际 {f['questions']}")
            if r["status"] and r["status"] not in STATUS_OK:
                errs.append(f"{year}/{region} 状态非法：{r['status']}（应为 {STATUS_ENUM}）")
            if r["anomaly"] and not (root / r["anomaly"]).exists():
                errs.append(f"{year}/{region} 异常记录链接不可达：{r['anomaly']}")
        for region in rows:
            if region not in papers[year]:
                errs.append(f"进度记录.md 多出 {year}/{region}（试卷/ 下无此目录）")

    # 2. 异常记录文件
    for year in sorted(papers):
        p = root / "异常记录" / f"{year}.md"
        if not p.exists():
            errs.append(f"缺少异常记录文件：异常记录/{year}.md")
            continue
        info = parse_anomaly(p)
        if not info["title_ok"]:
            errs.append(f"异常记录/{year}.md 首行应为 `# 异常记录 · {year} 年`")
        if not info["headers"]:
            errs.append(f"异常记录/{year}.md 未找到 `地区|题号|类别|问题|处理建议|状态` 表头")
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.lstrip().startswith("|"):
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                if len(cells) >= 5 and cells[-1] not in ANOM_OK and cells[-1] not in (
                        "状态",) and set(cells[-1]) != set("-:"):
                    errs.append(f"异常记录/{year}.md 状态非法：{cells[-1]}")
        if not info["has_category"]:
            errs.append(f"异常记录/{year}.md 的表头缺少“类别”列")

    # 2b. 年份索引 试卷/<年>/README.md
    for year in sorted(papers):
        p = root / "试卷" / year / "README.md"
        if not p.exists():
            errs.append(f"缺少年份索引：试卷/{year}/README.md")
            continue
        t = p.read_text(encoding="utf-8")
        for region in papers[year]:
            if f"]({region}/)" not in t:
                errs.append(f"试卷/{year}/README.md 未列出 {region}")

    # 3. README 概要块存在
    readme = root / "README.md"
    if readme.exists():
        t = readme.read_text(encoding="utf-8")
        if README_START not in t or README_END not in t:
            errs.append("README.md 缺少进度概要标记 PROGRESS:START/END")

    log(f"校验完成：年份 {len(papers)} 个、试卷 {sum(len(v) for v in papers.values())} 套，"
        f"错误 {len(errs)} 处。")
    return errs


# ---------------------------------------------------------------------------
# 生成
# ---------------------------------------------------------------------------
def render_year_readme(year: str, facts: dict[str, dict], rows: dict[str, dict]) -> str:
    n = sum(f["questions"] for f in facts.values())
    heading = f"{year}试卷索引" if year.endswith("以前") else f"{year} 年试卷索引"
    out = [f"# {heading}", "",
           "> 本文件由 `tools/gen_index.py --write` 生成，请勿手改；"
           f"进度见 [`进度记录.md`](../../进度记录.md)，异常见 "
           f"[`异常记录/{year}.md`](../../异常记录/{year}.md)。", "",
           f"共 **{len(facts)} 套**、**{n} 题**。", "",
           "| 地区 | 题数 | 状态 | 图片 | TikZ | 标记 | 说明 |",
           "| :--- | :-- | :--- | :-- | :-- | :--- | :--- |"]
    for region in sorted(facts, key=lambda r: (-facts[r]["questions"], r)):
        f = facts[region]
        row = rows.get(region, {})
        note = row.get("note", "") or ""
        mark = "回忆版" if f["recalled"] else (f["papertype"] or "—")
        out.append(f"| [{region}]({region}/) | {f['questions']} | {row.get('status','') or f['derived']} "
                   f"| {f['figs']} | {'是' if f['tikz'] else '—'} | {mark} | {note} |")
    out.append("")
    return "\n".join(out)


def write(root: Path = ROOT, verbose: bool = True) -> None:
    papers = scan_papers(root)
    progress = parse_progress(root / "进度记录.md")
    # 年份索引
    for year in sorted(papers):
        content = render_year_readme(year, papers[year], progress.get(year, {}).get("rows", {}))
        (root / "试卷" / year / "README.md").write_text(content, encoding="utf-8")
        if verbose:
            print(f"[写入] 试卷/{year}/README.md")
    # README 概要块
    if README.exists():
        t = README.read_text(encoding="utf-8")
        if README_START in t and README_END in t:
            total_p = sum(len(v) for v in papers.values())
            total_q = sum(f["questions"] for v in papers.values() for f in v.values())
            total_y = len(papers)
            block = (f"{README_START}\n"
                     f"- **已完成**：{total_y} 个年份、共 **{total_p} 套**卷、**{total_q} 题**"
                     f"（{ '、'.join((y if y.endswith('以前') else f'{y} 年') + f' {len(v)} 套' for y, v in sorted(papers.items())) }）。\n"
                     f"- **材料就位**：`材料处理/` 已完成 402 份 PDF 的三路转换与提图（本地，不入库）。\n"
                     f"- **待制作**：其余年份/地区，按批次推进。\n"
                     f"{README_END}")
            t = re.sub(re.escape(README_START) + r".*?" + re.escape(README_END),
                       block, t, flags=re.S)
            README.write_text(t, encoding="utf-8")
            if verbose:
                print("[刷新] README.md 进度概要块")
    # 回填题数列
    if PROGRESS.exists():
        t = PROGRESS.read_text(encoding="utf-8")
        lines = t.splitlines()
        cur = None
        changed = 0
        for i, line in enumerate(lines):
            m = re.match(r"^###\s*(\d{4})\s*年", line)
            if m:
                cur = m.group(1)
                continue
            if cur is None or not line.lstrip().startswith("|"):
                continue
            cells = [c for c in line.strip().strip("|").split("|")]
            region = cells[0].strip() if cells else ""
            if region in papers.get(cur, {}):
                actual = str(papers[cur][region]["questions"])
                if len(cells) > 1 and cells[1].strip() != actual:
                    cells[1] = f" {actual} "
                    lines[i] = "|" + "|".join(cells) + "|"
                    changed += 1
        if changed:
            PROGRESS.write_text("\n".join(lines) + "\n", encoding="utf-8")
            if verbose:
                print(f"[回填] 进度记录.md 题数列 {changed} 处")


def status_report(root: Path = ROOT) -> str:
    papers = scan_papers(root)
    progress = parse_progress(root / "进度记录.md")
    tally = anomaly_tally(root)
    lines = ["各年份进度概要："]
    for year in sorted(papers):
        q = sum(f["questions"] for f in papers[year].values())
        ph = sum(f["placeholder"] for f in papers[year].values())
        rows = progress.get(year, {}).get("rows", {})
        done = sum(1 for r in rows.values() if r.get("status") == "已完成")
        t = tally.get(year, {"counts": {}, "open": []})
        c = t["counts"]
        lines.append(
            f"  {year}: {len(papers[year])} 套 / {q} 题；已完成 {done} 套；缺详解题 {ph}；"
            f"未闭合异常 {len(t['open'])}"
            f"（待人工核验 {c.get('待人工核验', 0)}、待补充 {c.get('待补充', 0)}、"
            f"待处理 {c.get('待处理', 0)}、处理中 {c.get('处理中', 0)}）")
    total_p = sum(len(v) for v in papers.values())
    total_q = sum(f["questions"] for v in papers.values() for f in v.values())
    total_ph = sum(f["placeholder"] for v in papers.values() for f in v.values())
    opens = [(y, r) for y, t in tally.items() for r in t["open"]]
    lines.append(f"合计：{len(papers)} 个年份、{total_p} 套、{total_q} 题；"
                 f"未闭合异常 {len(opens)}；缺详解题 {total_ph}")
    if opens:
        lines.append("未闭合异常明细：")
        for y, r in opens:
            cat = f"[{r['category']}] " if r["category"] else ""
            q = r["question"] or ""
            loc = f"第 {q} 题" if re.match(r"^\d", q) else q
            lines.append(f"  - {y} {r['region']} {loc} {cat}{r['status']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="试卷索引 / 进度文档生成与校验")
    ap.add_argument("--check", action="store_true", help="校验进度表与目录一致性")
    ap.add_argument("--write", action="store_true", help="生成年份索引并刷新 README 概要")
    ap.add_argument("--status", action="store_true", help="打印各年份概要")
    args = ap.parse_args(argv)

    if args.write:
        write()
    if args.check:
        errs = check()
        if errs:
            for e in errs:
                print(f"[错误] {e}")
            return 1
        return 0
    if args.status or not (args.write or args.check):
        print(status_report())
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""tools/ocr_batch.py —— 批量材料处理驱动（Docx/**/*.pdf → 材料处理/<年>/<地区>/）

把 `材料处理与OCR规范.md` 的三路管线拆成**可分阶段、可断点续跑**的批量入口，
避免逐份调用 `ocr_pipeline.sh` 时**每个 PDF 都重新加载一次模型**的开销：

    源 PDF:  Docx/<年>/<年_地区>.pdf
    产物:    材料处理/<年>/<地区>/
             ├── pdftotext.txt        （旁证，CPU）
             ├── paddle/output.md     （引擎乙·验证，需 PaddleOCR-VL 服务）
             ├── ovis/output.md       （引擎甲·底本，vLLM 单进程复用模型）
             ├── merged.md            （三路交叉验证主数据源）
             └── pdfimages/           （原 PDF 内嵌图无损提取）

子命令::

    list        列出 PDF → 目标目录映射
    status      统计各阶段完成情况
    pdftotext   生成 pdftotext.txt（多线程，CPU）
    paddle      调用 PaddleOCR-VL 服务生成 paddle/output.md（需先起服务）
    ovis        OvisOCR2 批量（同一进程内**只加载一次模型**）
    merge       生成/校验 merged.md（--force 重建）
    extract     无损提取内嵌图到 pdfimages/

典型流程::

    ./tools/paddlex_serve_start.sh                       # 先起 Paddle 服务
    python3 tools/ocr_batch.py pdftotext                  # 旁证（可先跑）
    python3 tools/ocr_batch.py paddle                     # 验证引擎
    ./tools/paddlex_serve_stop.sh                         # 释放显存
    ~/.conda/envs/ovis_ocr/bin/python tools/ocr_batch.py ovis   # 底本（复用模型）
    python3 tools/ocr_batch.py merge
    python3 tools/ocr_batch.py extract

选项::

    --year 2001 --year 2026   仅处理指定年份目录（可重复）
    --region 湖北             仅处理指定地区（与 --year 配合）
    --only <关键词>           仅处理路径含该关键词者
    --limit N                 最多处理 N 份（调试用）
    --force                   已有产物也重跑
    --jobs N                  pdftotext 并发线程数（默认 8）
    --dry-run                 只列出将处理的项
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
DOCX = ROOT / "Docx"
MATERIAL = ROOT / "材料处理"
HERE = Path(__file__).resolve().parent

# PaddleOCR-VL 客户端所用解释器（可用环境变量覆盖）
PADDLE_PYTHON = os.environ.get(
    "PADDLE_PYTHON", os.path.expanduser("~/.conda/envs/BaiduPaddle/bin/python")
)
OVIS_MODEL = os.environ.get("OVIS_MODEL", os.path.expanduser("~/AI/ATH-MaaS/OvisOCR2"))


def _split(pdf: Path) -> Optional[Tuple[str, str]]:
    """返回 (年份桶目录, 完整卷名 stem)；不合规者返回 None。"""
    rel = pdf.relative_to(DOCX)
    if len(rel.parts) < 2 or "_" not in pdf.stem:
        return None
    return rel.parts[0], pdf.stem


def region_counts() -> Dict[Tuple[str, str], int]:
    """统计每个 (年份桶, 基础地区) 下的卷数，用于检测同地区多卷冲突。"""
    counts: Dict[Tuple[str, str], int] = defaultdict(int)
    for pdf in DOCX.rglob("*.pdf"):
        sp = _split(pdf)
        if not sp:
            continue
        year, stem = sp
        counts[(year, stem.split("_", 1)[1])] += 1
    return counts


def iter_pdfs(years: Optional[List[str]] = None,
              region: Optional[str] = None,
              only: Optional[str] = None) -> List[Tuple[Path, Path]]:
    """遍历 Docx 下的 PDF，返回 (源 PDF, 处理目录) 列表。

    处理目录一般为 ``材料处理/<年份>/<地区>``；但以下两种情况改用**完整卷名**作子目录：

    * 同一 (年份, 地区) 下有多份卷（如 ``2000年以前`` 的 ``1978_全国``、``1979_全国``…）；
    * 年份桶**不是 4 位数字**（如 ``2000年以前``），此桶内卷名本身即含学年，须保留
      （如 ``1999_广东``、``1991_湖南云南海南``）。
    """
    counts = region_counts()
    items: List[Tuple[Path, Path]] = []
    for pdf in sorted(DOCX.rglob("*.pdf")):
        sp = _split(pdf)
        if not sp:
            continue
        year, stem = sp
        reg = stem.split("_", 1)[1]
        if years and year not in years:
            continue
        if region and region not in reg:
            continue
        use_full = counts[(year, reg)] > 1 or not re.fullmatch(r"\d{4}", year)
        name = stem if use_full else reg
        out = MATERIAL / year / name
        if only and only not in str(pdf) and only not in str(out):
            continue
        items.append((pdf, out))
    return items


def nonempty(p: Path) -> bool:
    return p.is_file() and p.stat().st_size > 0


def pdfimages_ok(d: Path) -> bool:
    """pdfimages 阶段是否完成：有 manifest 时校验所列图片文件齐全；无 manifest 的
    纯矢量/无内嵌图目录，只要 pdfimages/ 目录存在即视为完成。"""
    p = d / "pdfimages"
    if not p.is_dir():
        return False
    man = p / "manifest.json"
    if not man.is_file():
        return True
    try:
        data = json.loads(man.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return all((p / e.get("file", "")).is_file() for e in data.get("images", []))


def run_retry(cmd, tries: int = 2):
    """执行命令，非零退出码时重试（瞬态故障，如服务抖动）。返回最后一次 CompletedProcess。"""
    last = None
    for _ in range(max(1, tries)):
        last = subprocess.run(cmd, capture_output=True, text=True)
        if last.returncode == 0:
            return last
    return last


# --------------------------------------------------------------------------
# 各阶段
# --------------------------------------------------------------------------
def cmd_list(items, args) -> int:
    for pdf, out in items:
        print(f"{pdf.relative_to(ROOT)}  ->  {out.relative_to(ROOT)}")
    print(f"\n共 {len(items)} 份。")
    return 0


def cmd_status(items, args) -> int:
    stages = {
        "pdftotext": lambda d: nonempty(d / "pdftotext.txt"),
        "paddle": lambda d: nonempty(d / "paddle" / "output.md"),
        "ovis": lambda d: nonempty(d / "ovis" / "output.md"),
        "merged": lambda d: nonempty(d / "merged.md"),
        "pdfimages": pdfimages_ok,
    }
    counts = {k: 0 for k in stages}
    done_all = 0
    for _, out in items:
        ok = True
        for k, fn in stages.items():
            if fn(out):
                counts[k] += 1
            else:
                ok = False
        if ok:
            done_all += 1
    total = len(items)
    print(f"共 {total} 份：")
    for k in stages:
        print(f"  {k:10s} {counts[k]:4d}/{total}")
    print(f"  五要素齐全 {done_all:4d}/{total}")
    return 0


def cmd_pdftotext(items, args) -> int:
    todo = [(p, o) for p, o in items
            if args.force or not nonempty(o / "pdftotext.txt")]

    def run(pair: Tuple[Path, Path]) -> bool:
        pdf, out = pair
        out.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(["pdftotext", "-layout", str(pdf), str(out / "pdftotext.txt")],
                           capture_output=True, text=True)
        if r.returncode != 0:
            print(f"[失败] {pdf.relative_to(ROOT)}: {r.stderr.strip()}")
            return False
        return True

    n_ok = n_fail = 0
    with ThreadPoolExecutor(max_workers=args.jobs) as ex:
        for ok in ex.map(run, todo):
            n_ok += ok
            n_fail += (not ok)
    print(f"pdftotext 完成：成功 {n_ok}，失败 {n_fail}，跳过 {len(items) - len(todo)}。")
    return 1 if n_fail else 0


def cmd_paddle(items, args) -> int:
    todo = [(p, o) for p, o in items
            if args.force or not nonempty(o / "paddle" / "output.md")]
    script = HERE / "PaddleOCR_PDF_to_md.py"
    n_ok = n_fail = 0
    for i, (pdf, out) in enumerate(todo, 1):
        if args.dry_run:
            print(f"[dry-run] paddle {pdf.relative_to(ROOT)}")
            continue
        (out / "paddle").mkdir(parents=True, exist_ok=True)
        print(f"[{i}/{len(todo)}] Paddle ← {pdf.relative_to(ROOT)}", flush=True)
        r = run_retry(
            [PADDLE_PYTHON, str(script), "-i", str(pdf), "-o", str(out / "paddle"), "-q"],
            tries=2,
        )
        if r.returncode != 0 or not nonempty(out / "paddle" / "output.md"):
            print(f"   [失败] rc={r.returncode} {(r.stderr or '')[-400:]}")
            n_fail += 1
        else:
            n_ok += 1
    print(f"Paddle 完成：成功 {n_ok}，失败 {n_fail}，跳过 {len(items) - len(todo)}。")
    return 1 if n_fail else 0


def cmd_ovis(items, args) -> int:
    todo = [(p, o) for p, o in items
            if args.force or not nonempty(o / "ovis" / "output.md")]
    if args.dry_run:
        for pdf, _ in todo:
            print(f"[dry-run] ovis {pdf.relative_to(ROOT)}")
        return 0
    if not todo:
        print("Ovis：无需处理（均已存在）。")
        return 0

    # 延迟导入，避免非 ovis 子命令也拉入 vllm
    sys.path.insert(0, str(HERE))
    try:
        import pdf_to_md  # type: ignore
    except Exception as e:  # pragma: no cover
        print(f"[错误] 无法导入 pdf_to_md（需用 ovis_ocr 环境解释器运行 ovis 子命令）：{e}",
              file=sys.stderr)
        return 2

    ns = argparse.Namespace(
        model_path=args.model_path or OVIS_MODEL,
        enforce_eager=True,
        skip_compile=False,
        input="",
        output=None,
        resume=False,
        batch_size=None,
        dpi=None,
        max_image_size=None,
        image_quality=None,
        debug=False,
        preview=False,
    )
    config = pdf_to_md.load_config(None)
    proc = pdf_to_md.MainProcessor(config, ns)
    if not proc.load_model():
        print("[错误] OvisOCR2 模型加载失败。", file=sys.stderr)
        return 2

    n_ok = n_fail = 0
    for i, (pdf, out) in enumerate(todo, 1):
        print(f"[{i}/{len(todo)}] Ovis ← {pdf.relative_to(ROOT)}", flush=True)
        ns.input = str(pdf)
        ns.output = str(out / "ovis")
        ok = False
        for attempt in (1, 2):
            try:
                ok = proc.process_pdf(pdf)
            except Exception as e:  # pragma: no cover
                print(f"   [异常 {attempt}] {e}")
                ok = False
            if ok and nonempty(out / "ovis" / "output.md"):
                break
            if attempt == 1:
                print(f"   [重试] {pdf.relative_to(ROOT)}")
        if ok and nonempty(out / "ovis" / "output.md"):
            n_ok += 1
        else:
            n_fail += 1
    print(f"Ovis 完成：成功 {n_ok}，失败 {n_fail}，跳过 {len(items) - len(todo)}。")
    return 1 if n_fail else 0


def cmd_merge(items, args) -> int:
    sys.path.insert(0, str(HERE))
    import material_merge  # type: ignore
    argv = ["--root", "材料处理"]
    if args.force:
        argv.append("--force")
    return material_merge.main(argv)


def cmd_extract(items, args) -> int:
    sys.path.insert(0, str(HERE))
    import pdf_extract_images  # type: ignore
    argv = ["--root", "材料处理"]
    if args.force:
        argv.append("--force")
    return pdf_extract_images.main(argv)


COMMANDS = {
    "list": cmd_list,
    "status": cmd_status,
    "pdftotext": cmd_pdftotext,
    "paddle": cmd_paddle,
    "ovis": cmd_ovis,
    "merge": cmd_merge,
    "extract": cmd_extract,
}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="批量材料处理驱动（PDF→Markdown/text）")
    parser.add_argument("command", choices=sorted(COMMANDS))
    parser.add_argument("--year", action="append", default=[], help="仅指定年份（可重复）")
    parser.add_argument("--region", default=None, help="仅指定地区（子串匹配）")
    parser.add_argument("--only", default=None, help="仅路径含该关键词者")
    parser.add_argument("--limit", type=int, default=0, help="最多处理 N 份")
    parser.add_argument("--jobs", type=int, default=8, help="pdftotext 并发数")
    parser.add_argument("--force", action="store_true", help="已有产物也重跑")
    parser.add_argument("--model-path", default=None, help="OvisOCR2 模型路径")
    parser.add_argument("--dry-run", action="store_true", help="只列出将处理的项")
    args = parser.parse_args(argv)

    items = iter_pdfs(args.year or None, args.region, args.only)
    if args.limit:
        items = items[: args.limit]
    if not items:
        print("未找到匹配的 PDF。")
        return 1
    return COMMANDS[args.command](items, args)


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""tools/material_merge.py

生成材料处理目录的 ``merged.md``（三路交叉验证后的主数据源）。

规则（与 `材料处理与OCR规范.md` 一致）：
    * 正文以 **OvisOCR2**（`ovis/output.md`）为底本；
    * 用 **PaddleOCR-VL**（`paddle/output.md`）与 **pdftotext**（`pdftotext.txt`）逐项印证；
    * 文末附**自动提取的差异记录**（数字 / 公式），供回原 PDF 核对。

守卫（防止「merged.md 在、底稿没了」的静默缺失）：
    * 即使 `merged.md` 已存在，也检查 `ovis/output.md`、`paddle/output.md`
      是否缺失/为空；缺失即报 ``[错误]`` 并计入退出码（不覆盖既有 merged.md）；
    * `merged.md` 头部记录底稿哈希 ``source_sha256``；重建时如底稿已变，
      下次运行报 ``[漂移]``，提示用 ``--force`` 重建。

用法::

    python3 tools/material_merge.py <处理目录> [<处理目录> ...]
    python3 tools/material_merge.py --root 材料处理 [--force]

默认仅处理**尚无 merged.md** 的目录；``--force`` 覆盖重建。
退出码：0 无问题；1 存在底稿缺失或漂移。
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parent.parent
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
FORMULA_RE = re.compile(r"\$[^$\n]+\$")


def strip_front_matter(md: str) -> str:
    if md.startswith("---"):
        parts = md.split("---", 2)
        if len(parts) >= 3:
            return parts[2].lstrip("\n")
    return md


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def source_hash(ovis_path: Path, paddle_path: Path) -> str:
    """底稿（ovis/output.md + paddle/output.md）的 sha256，用于检测漂移。"""
    h = hashlib.sha256()
    for p in (ovis_path, paddle_path):
        h.update(p.read_bytes() if p.exists() else b"")
        h.update(b"\x00")
    return h.hexdigest()


def read_source_hash(merged_path: Path) -> Optional[str]:
    """读取已生成 merged.md 头部记录的底稿哈希（无则 None）。"""
    m = re.search(r"^source_sha256:\s*([0-9a-fA-F]{64})\s*$", read_text(merged_path), re.M)
    return m.group(1).lower() if m else None


def clean_body(body: str) -> str:
    """清理 OvisOCR2 常见噪声：独立的纯大写拼音行、过多空行。"""
    out = []
    for line in body.splitlines():
        if re.fullmatch(r"[A-Z]{3,}", line.strip()):
            continue  # 如 DIYIZHANG
        out.append(line)
    text = "\n".join(out)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip("\n")


def title_of(ovis_text: str, directory: Path) -> str:
    m = re.search(r'^title:\s*"?([^"\n]+)"?\s*$', ovis_text, re.M)
    return m.group(1).strip() if m else directory.name


def _fmt_set(items: List[str]) -> str:
    return "；".join(f"`{x}`" for x in items) if items else "`（无）`"


def build_appendix(ovis: str, paddle: str, pdftxt: str) -> str:
    o_n, p_n, t_n = map(lambda s: set(NUMBER_RE.findall(s)), (ovis, paddle, pdftxt))
    o_f, p_f = set(FORMULA_RE.findall(ovis)), set(FORMULA_RE.findall(paddle))

    lines = [
        "## 附：交叉验证差异记录（自动提取，供回原图核对）",
        "",
        f"- OvisOCR2 数字集合 {len(o_n)} 个；PaddleOCR-VL 数字集合 {len(p_n)} 个；"
        f"pdftotext 数字集合 {len(t_n)} 个。",
        "",
        "### 1. 数字 / 单位差异",
        "",
        "仅 Ovis 出现（Paddle 与 pdftotext 均无）：",
        _fmt_set(sorted(o_n - p_n - t_n)),
        "",
        "仅 Paddle 出现（Ovis 与 pdftotext 均无）：",
        _fmt_set(sorted(p_n - o_n - t_n)),
        "",
        "仅 pdftotext 出现（两引擎均无）：",
        _fmt_set(sorted(t_n - o_n - p_n)),
        "",
        "### 2. 公式差异",
        "",
        "仅 Ovis 出现的公式：",
        _fmt_set(sorted(o_f - p_f)),
        "",
        "仅 Paddle 出现的公式：",
        _fmt_set(sorted(p_f - o_f)),
        "",
    ]
    return "\n".join(lines)


def build_merged(directory: Path) -> Optional[str]:
    ovis_path = directory / "ovis" / "output.md"
    paddle_path = directory / "paddle" / "output.md"
    pdftxt_path = directory / "pdftotext.txt"
    if not ovis_path.exists():
        return None

    ovis_raw = read_text(ovis_path)
    ovis_body = clean_body(strip_front_matter(ovis_raw))
    paddle_body = strip_front_matter(read_text(paddle_path))
    pdftxt = read_text(pdftxt_path)
    title = title_of(ovis_raw, directory)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    header = (
        "---\n"
        f'title: {title}\n'
        "engines: OvisOCR2 (ovis/output.md) + PaddleOCR-VL-1.6 (paddle/output.md)\n"
        "side_reference: pdftotext -layout (pdftotext.txt)\n"
        f"source_sha256: {source_hash(ovis_path, paddle_path)}\n"
        f"validated_at: {now}\n"
        "status: 以 OvisOCR2 为底本，已对照 PaddleOCR-VL 与 pdftotext 交叉验证\n"
        "---\n\n"
        "# 主数据源（merged.md）\n\n"
        "> 本文件为该材料的主数据源：正文以 OvisOCR2 输出为底本，\n"
        "> 已与 PaddleOCR-VL 输出、pdftotext 文本逐项交叉验证；\n"
        "> 文末“交叉验证差异记录”列出三路来源不一致的数字/公式，供回原 PDF 核对。\n\n"
        "> **配图取用**：以 `<处理目录>/pdfimages/`（原 PDF 内嵌图**无损提取**，见 `make extract-images`）为准——\n"
        "> **单图直接取用、多子图用 `tools/recrop_figures.py` 裁剪回填**；本文件的 `<img src=\"images/...\">`\n"
        "> 仅为 OCR 交叉校勘旁证，**不再直接用于制作配图**（见 `材料处理与OCR规范.md` 第五节）。\n\n"
    )
    appendix = build_appendix(ovis_body, paddle_body, pdftxt)
    return header + ovis_body.rstrip() + "\n\n---\n\n" + appendix


def iter_dirs(args) -> List[Path]:
    if args.root:
        base = Path(args.root)
        dirs = set()
        for p in base.rglob("ovis/output.md"):
            dirs.add(p.parent.parent)
        # 同时纳入「有 merged.md / pdftotext.txt 但可能缺 ovis」的目录，供守卫检查
        for name in ("merged.md", "pdftotext.txt"):
            for p in base.rglob(name):
                dirs.add(p.parent)
        return sorted(dirs)
    return [Path(p) for p in args.paths]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="生成 merged.md（三路交叉验证主数据源）")
    parser.add_argument("paths", nargs="*", help="材料处理目录（含 ovis/、paddle/、pdftotext.txt）")
    parser.add_argument("--root", default="", help="在此目录下递归查找并处理")
    parser.add_argument("--force", action="store_true", help="覆盖已有 merged.md")
    args = parser.parse_args(argv)

    dirs = iter_dirs(args)
    if not dirs:
        print("未找到待处理目录。")
        return 1

    built = skipped = missing = 0
    problems = 0
    for d in dirs:
        out = d / "merged.md"
        ovis_p = d / "ovis" / "output.md"
        paddle_p = d / "paddle" / "output.md"
        ovis_ok = ovis_p.is_file() and ovis_p.stat().st_size > 0
        paddle_ok = paddle_p.is_file() and paddle_p.stat().st_size > 0

        # 守卫：即使 merged.md 已存在，也检查底稿是否缺失（防止静默缺失）
        if not ovis_ok or not paddle_ok:
            lack = [n for n, ok in (("ovis/output.md", ovis_ok),
                                    ("paddle/output.md", paddle_ok)) if not ok]
            print(f"[错误] 缺少底稿（{'、'.join(lack)}）：{d}")
            problems += 1
            if out.exists() and not args.force:
                # 不用残缺底稿覆盖既有 merged.md，但计入问题
                skipped += 1
                continue

        if out.exists() and not args.force:
            if ovis_ok and paddle_ok:
                stored = read_source_hash(out)
                if stored is not None and stored != source_hash(ovis_p, paddle_p):
                    print(f"[漂移] 底稿已变更，merged.md 需重建（--force）：{out}")
                    problems += 1
            skipped += 1
            continue

        merged = build_merged(d)
        if merged is None:
            missing += 1
            print(f"[跳过] 缺少 ovis/output.md：{d}")
            continue
        out.write_text(merged, encoding="utf-8")
        built += 1
        print(f"[生成] {out}")
    print(f"\n完成：生成 {built}，跳过（已存在）{skipped}，缺料 {missing}，问题 {problems}。")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

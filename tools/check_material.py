#!/usr/bin/env python3
"""材料处理产物完整性检查（四要素 + 图片引用 + 底稿漂移）。

针对 ``材料处理/<年>/<地区>/`` 下的每个
**处理目录**，检查其四要素是否齐全、非空：

    1. ovis/output.md    —— OvisOCR2 底本
    2. paddle/output.md  —— PaddleOCR-VL 验证
    3. pdftotext.txt     —— 文字版旁证
    4. merged.md         —— 三路交叉验证主数据源

并进一步校验：

    * ovis/output.md、paddle/output.md 中引用的 ``images/`` 图片确实存在；
    * merged.md 头部若记录了底稿哈希 ``source_sha256``，则与当前
      ovis/paddle 底稿比对，不一致即为**漂移**（底稿已变、merged.md 未重建）。

> 背景：曾出现「merged.md 在、ovis/paddle 被清空」的静默缺失（旧版
> material_merge 只认 merged.md 是否已存在，不回头校验底稿）。本脚本用于
> 在批量转换后立即发现此类问题，避免不完整数据被后续使用。

用法::

    python3 tools/check_material.py                 # 默认检查两个根目录
    python3 tools/check_material.py 材料处理
    python3 tools/check_material.py --root 材料处理
    python3 tools/check_material.py --quiet         # 仅打印问题与汇总

退出码：0 全部完整；1 存在问题。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Iterable, List, Set

sys.path.insert(0, str(Path(__file__).resolve().parent))
from material_merge import source_hash  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ROOTS = ["材料处理"]

# merged.md 头部记录的底稿哈希
HASH_RE = re.compile(r"^source_sha256:\s*([0-9a-fA-F]{64})\s*$", re.M)
# output.md 中的图片引用：<img src="images/x.jpg"> 或 ![alt](images/x.jpg)
IMG_RE = re.compile(r"""(?:src\s*=\s*["']|!\[[^\]]*\]\()\s*(images/[^"')]+)""")

ELEMENTS = [
    ("ovis/output.md", "OvisOCR2 底本"),
    ("paddle/output.md", "PaddleOCR-VL 验证"),
    ("pdftotext.txt", "文字旁证"),
    ("merged.md", "主数据源"),
]


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def find_dirs(roots: Iterable[Path]) -> List[Path]:
    """定位所有处理目录（含 ovis/paddle 子目录或 pdftotext.txt / merged.md 者）。"""
    dirs: Set[Path] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for name in ("ovis", "paddle"):
            for p in root.rglob(name):
                if p.is_dir():
                    dirs.add(p.parent)
        for name in ("pdftotext.txt", "merged.md"):
            for p in root.rglob(name):
                dirs.add(p.parent)
    return sorted(dirs)


def check_images(doc: str, base: Path, problems: List[str], warnings: List[str]):
    """校验 doc 中引用的 images/ 图片是否真实存在。"""
    text = read_text(base)
    refs = IMG_RE.findall(text)
    missing = sorted({r for r in refs if not (base.parent / r).exists()})
    for r in missing:
        problems.append(f"{doc} 引用图片缺失：{r}")


def check_dir(d: Path, problems: List[str], warnings: List[str]):
    # 1) 四要素存在且非空
    for rel, label in ELEMENTS:
        p = d / rel
        if not p.is_file():
            problems.append(f"缺少 {label}（{rel}）：{d}")
        elif p.stat().st_size == 0:
            problems.append(f"空文件 {label}（{rel}）：{d}")

    # 2) 图片引用完整性
    if (d / "ovis" / "output.md").is_file():
        check_images("ovis/output.md", d / "ovis" / "output.md", problems, warnings)
    if (d / "paddle" / "output.md").is_file():
        check_images("paddle/output.md", d / "paddle" / "output.md", problems, warnings)

    # 3) 底稿漂移（merged.md 记录 source_sha256 时）
    merged = d / "merged.md"
    ovis_p, paddle_p = d / "ovis" / "output.md", d / "paddle" / "output.md"
    if merged.is_file() and ovis_p.is_file() and paddle_p.is_file():
        m = HASH_RE.search(read_text(merged))
        if m:
            cur = source_hash(ovis_p, paddle_p)
            if cur.lower() != m.group(1).lower():
                problems.append(f"底稿漂移（底稿已变、merged.md 未重建）：{d}")

    # 4) 原 PDF 内嵌图是否已提取（供配图/裁剪；纯矢量页目录会存在但清单为空）
    if ovis_p.is_file() and not (d / "pdfimages").is_dir():
        warnings.append(f"尚未提取原 PDF 内嵌图（可运行 make extract-images）：{d}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="材料处理产物完整性检查")
    parser.add_argument("paths", nargs="*", help="处理目录或根目录（默认检查两个根目录）")
    parser.add_argument("--root", action="append", default=[],
                        help="要递归检查的根目录（可重复）")
    parser.add_argument("--quiet", action="store_true", help="仅打印问题与汇总")
    args = parser.parse_args(argv)

    if args.paths:
        roots = [Path(p) for p in args.paths]
    elif args.root:
        roots = [Path(r) for r in args.root]
    else:
        roots = [ROOT / r for r in DEFAULT_ROOTS]

    dirs = find_dirs(roots)
    if not dirs:
        print("未找到任何处理目录。")
        return 1

    problems: List[str] = []
    warnings: List[str] = []
    for d in dirs:
        check_dir(d, problems, warnings)

    if not args.quiet:
        print(f"共检查处理目录 {len(dirs)} 个。")
    for w in warnings:
        print(f"[提示] {w}")
    for p in problems:
        print(f"[错误] {p}")

    if problems:
        print(f"\n结果：{len(problems)} 处问题 ❌")
        return 1
    print(f"\n结果：{len(dirs)} 个处理目录四要素完整、图片引用有效 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())

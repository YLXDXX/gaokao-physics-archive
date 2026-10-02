#!/usr/bin/env python3
"""tools/check_glyphs.py —— 编译日志“缺字（Missing character）”检查。

XeLaTeX 遇到 font 中没有的字形（最典型：把汉字放进 ``\\mathrm{}`` 等拉丁字体命令）时，
不会报错，只在 ``.log`` 里写 ``Missing character: There is no 太 in font ...``，产物**静默丢字**。
本脚本扫描试卷目录下的 ``*.log``，把这些缺字集中报出，供 ``make check`` 兜底。

用法::

    python3 tools/check_glyphs.py                 # 默认扫描 试卷/
    python3 tools/check_glyphs.py 试卷/2026/四川   # 指定文件或目录
    python3 tools/check_glyphs.py --quiet         # 仅输出问题与汇总

退出码：0 无缺字（或未找到日志）；1 发现缺字。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ROOTS = ["试卷"]

# XeTeX：Missing character: There is no 太 in font ...
MISSING_RE = re.compile(
    r"Missing character:\s*There is no\s+(.*?)\s+in font\s+(.*?)[!.]?\s*$"
)
# 兜底：某些引擎/字体的另一种措辞
NO_GLYPH_RE = re.compile(r"Missing character:.*?\(U\+([0-9A-Fa-f]+)\)")


def collect_logs(paths: List[Path]) -> List[Path]:
    logs: List[Path] = []
    for p in paths:
        if p.is_dir():
            logs += sorted(p.rglob("*.log"))
        elif p.suffix == ".log" and p.is_file():
            logs.append(p)
        elif p.is_file():  # 传入 .tex，找同名 .log
            logs += sorted(p.parent.glob(p.stem + "*.log"))
    # 去重、保持顺序
    seen = set()
    out: List[Path] = []
    for f in logs:
        key = f.resolve()
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out


def scan_log(path: Path) -> List[str]:
    """返回该日志中的缺字描述列表（已去重）。"""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    hits: List[str] = []
    for line in text.splitlines():
        m = MISSING_RE.search(line)
        if m:
            hits.append(f"缺字 {m.group(1)!r}（font: {m.group(2).strip()}）")
        else:
            m = NO_GLYPH_RE.search(line)
            if m:
                hits.append(f"缺字 U+{m.group(1)}")
    return sorted(set(hits))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="编译日志缺字检查（Missing character）")
    ap.add_argument("paths", nargs="*", type=Path, help=".log 文件或目录；缺省扫描 试卷/")
    ap.add_argument("--quiet", action="store_true", help="仅输出问题与汇总")
    args = ap.parse_args(argv)

    paths = args.paths or [ROOT / r for r in DEFAULT_ROOTS]
    logs = collect_logs(paths)
    if not logs:
        if not args.quiet:
            print("未找到编译日志（请先 make 编译）。")
        return 0

    bad = 0
    for log in logs:
        hits = scan_log(log)
        if hits:
            bad += 1
            rel = log.relative_to(ROOT) if str(log).startswith(str(ROOT)) else log
            print(f"[缺字] {rel}")
            for h in hits:
                print(f"    - {h}")

    if bad:
        print(f"\n结果：{bad}/{len(logs)} 个日志存在缺字 ❌"
              "（常见原因：汉字写在 \\mathrm{} 内，应改用 \\text{...}）")
        return 1
    if not args.quiet:
        print(f"结果：{len(logs)} 个日志无缺字 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())

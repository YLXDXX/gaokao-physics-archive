#!/usr/bin/env python3
"""tools/status.py —— 各年份制作进度概要

扫描 `试卷/` 与 `进度记录.md`，按年份打印套数、题数与“已完成”计数；
状态列另可由文件系统推断（两版 PDF 是否生成等）。

用法::

    python3 tools/status.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gen_index  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    print(gen_index.status_report())
    return 0


if __name__ == "__main__":
    sys.exit(main())

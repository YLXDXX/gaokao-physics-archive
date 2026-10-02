#!/usr/bin/env python3
"""tools/check_docs.py —— 文档一致性校验（进度 / 年份索引 / 异常记录）

校验 `进度记录.md` ↔ `试卷/<年>/<地区>/`、`试卷/<年>/README.md`、`异常记录/<年>.md`
是否相互一致（状态取值合法、题数相符、链接可达、异常表头规范）。
已接入根目录 `make check`（`make check-docs`）。

用法::

    python3 tools/check_docs.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gen_index  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    errs = gen_index.check()
    if errs:
        for e in errs:
            print(f"[错误] {e}")
        print(f"\n文档校验未通过：{len(errs)} 处问题。")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

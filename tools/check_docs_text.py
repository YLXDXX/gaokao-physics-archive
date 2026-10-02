#!/usr/bin/env python3
"""tools/check_docs_text.py —— 文档体检（交叉引用 / 过时命令）。

对项目 Markdown 文档做轻量一致性检查，避免各文档相互漂移：

1. **过时的 `cd` 用法**：规则要求统一在仓库根用 `make -C 试卷/…`，文档中不应再
   出现“`cd 试卷/…` / `cd Docx/…`”之类示例；带“不要/禁止/不得/反例”等否定词的
   说明行豁免（那正是在讲这条规则）；
2. **失效相对链接**：形如 `](path/to/x.md)` 的本地链接，目标文件须存在
   （跳过 http(s) 链接与锚点）。

只扫描根目录、`docs/`、`tools/`（含 `tools/textfix/` 等子目录）下的 `*.md`；
不扫描由 `make index` 生成的 `试卷/**/README.md`。

用法::

    python3 tools/check_docs_text.py
    python3 tools/check_docs_text.py --roots docs tools

退出码：0 通过；1 存在问题。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {"__pycache__", "node_modules", ".git", "svg-inkscape"}
DEFAULT_ROOTS = [ROOT, ROOT / "docs", ROOT / "tools"]
CD_RE = re.compile(r"`?\bcd\s+([^\s`'\"]+)")
NEG_WORDS = ("不要", "禁止", "不得", "反例", "错误", "✗", "❌")
LINK_RE = re.compile(r"\]\(([^)\s]+\.md)(?:#[^)]*)?\)")


def iter_md(roots: List[Path]) -> List[Path]:
    out: List[Path] = []
    for root in roots:
        if root.is_file() and root.suffix == ".md":
            out.append(root)
        elif root.is_dir():
            # 仓库根只取顶层 *.md（避免递归进 材料处理/ JSON/ Docx/ 等数据目录）
            pat = "*.md" if root == ROOT else "**/*.md"
            for p in root.glob(pat):
                if any(part in SKIP_DIRS for part in p.parts):
                    continue
                out.append(p)
    # 去重、排除生成的年份索引
    uniq = sorted(set(out))
    return [p for p in uniq if "/试卷/" not in str(p)]


def check_doc(path: Path) -> List[str]:
    errs: List[str] = []
    text = path.read_text(encoding="utf-8", errors="ignore")
    for i, line in enumerate(text.splitlines(), 1):
        m = CD_RE.search(line)
        if m and not any(w in line for w in NEG_WORDS):
            target = m.group(1)
            if target.startswith(("试卷", "Docx", "JSON", "材料处理", "./试卷")):
                errs.append(f"{path.relative_to(ROOT)}:{i} 过时的 cd 用法："
                            f"「{m.group(0).strip()}」（请改用 make -C 试卷/…）")
        for link in LINK_RE.findall(line):
            if link.startswith(("http://", "https://", "mailto:")):
                continue
            target = (path.parent / link).resolve()
            if not target.exists():
                errs.append(f"{path.relative_to(ROOT)}:{i} 失效的相对链接：{link}")
    return errs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Markdown 文档体检（交叉引用/过时命令）")
    ap.add_argument("--roots", nargs="*", default=None,
                    help="要扫描的目录或文件（缺省 根目录 / docs / tools）")
    args = ap.parse_args(argv)
    roots = [Path(r) for r in args.roots] if args.roots else DEFAULT_ROOTS
    files = iter_md(roots)
    total = 0
    for f in files:
        errs = check_doc(f)
        total += len(errs)
        for e in errs:
            print(f"[错误] {e}")
    if total:
        print(f"\n共检查 {len(files)} 个文档，发现 {total} 处问题 ❌")
        return 1
    print(f"\n共检查 {len(files)} 个文档，未发现问题 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())

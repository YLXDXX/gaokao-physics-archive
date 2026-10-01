"""tools/textfix/textfix.py

正则文本处理模块：核心处理与命令行入口。

修正各卷 `.tex`（及 `.sty`/`.cls`/`.md`）中的共性问题，如：数字之间的全角
冒号改半角、相邻行内公式连字符并入公式、`\\dfrac` 改 `\\frac`（见
`LaTeX_format_ReadMe.md` 第 21～23 条）。

用法::

    python3 tools/textfix/textfix.py [选项] <路径>...

    <路径> 可为文件或目录（目录递归）。默认仅检查并列出待修正处；
    加 --write 就地写回。--check 在存在待修正处时返回退出码 1，
    便于接入 CI / make check。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

try:  # 作为包导入（python -m tools.textfix.textfix）
    from .rules import RULES, apply_rules, scan_text
except ImportError:  # 直接运行脚本（python3 tools/textfix/textfix.py）
    from rules import RULES, apply_rules, scan_text

DEFAULT_EXTENSIONS: Tuple[str, ...] = (".tex", ".sty", ".cls", ".md")


def fix_text(text: str) -> Tuple[str, List[Tuple[str, int]]]:
    """对一段文本应用全部规则，返回 ``(新文本, 规则统计)``。"""
    return apply_rules(text)


def iter_target_files(
    paths: Iterable[str],
    extensions: Sequence[str] = DEFAULT_EXTENSIONS,
) -> List[Path]:
    """把文件 / 目录参数展开为待处理文件列表（去重、保持顺序）。"""
    files: List[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            for ext in extensions:
                files.extend(sorted(path.rglob(f"*{ext}")))
        elif path.is_file():
            files.append(path)
        else:
            raise FileNotFoundError(f"路径不存在：{path}")

    seen = set()
    result: List[Path] = []
    for item in files:
        key = item.resolve()
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def fix_file(path: Path, write: bool = False) -> Tuple[bool, List[Tuple[str, int]]]:
    """处理单个文件，返回 ``(是否有改动, 规则统计)``。

    ``write=False`` 时只计算不写回（用于检查 / 预览）。
    """
    original = path.read_text(encoding="utf-8")
    fixed, changes = apply_rules(original)
    if changes and write:
        path.write_text(fixed, encoding="utf-8")
    return bool(changes), changes


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="修正文档中的共性问题（正则文本处理）")
    parser.add_argument("paths", nargs="+", help="待处理的文件或目录")
    parser.add_argument("--write", action="store_true", help="就地写回修改")
    parser.add_argument("--check", action="store_true",
                        help="仅检查：存在待修正处时返回退出码 1")
    parser.add_argument("--ext", action="append", default=None,
                        help="扩展名（可重复，如 --ext .tex），"
                             "默认 .tex/.sty/.cls/.md")
    args = parser.parse_args(argv)

    extensions = tuple(args.ext) if args.ext else DEFAULT_EXTENSIONS
    files = iter_target_files(args.paths, extensions)

    changed_files = 0
    total_hits = 0
    for path in files:
        text = path.read_text(encoding="utf-8")
        hits = scan_text(text)
        if not hits:
            continue
        changed_files += 1
        total_hits += len(hits)
        if args.write:
            fix_file(path, write=True)
            print(f"[已修正] {path}（{len(hits)} 处）")
        else:
            print(f"[需修正] {path}（{len(hits)} 处）")
            for lineno, rule_name, snippet in hits:
                print(f"    L{lineno}  {rule_name}：“{snippet}”")

    if changed_files == 0:
        print(f"检查 {len(files)} 个文件，未发现共性问题。")
        return 0
    if args.write:
        print(f"共修正 {changed_files} 个文件、{total_hits} 处。")
        return 0
    print(f"共 {changed_files} 个文件、{total_hits} 处待修正（加 --write 应用）。")
    return 1 if args.check else 0


if __name__ == "__main__":
    sys.exit(main())

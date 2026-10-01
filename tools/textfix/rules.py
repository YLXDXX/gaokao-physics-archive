"""tools/textfix/rules.py

共性问题正则规则库。

每条规则用 ``Rule`` 描述：名称、说明、正则表达式与替换内容。规则按
``RULES`` 列表顺序依次应用。新增规则只需在 ``RULES`` 中追加一条
``Rule`` 即可，命令行与测试会自动使用新规则。

约定：
    * 正则一律使用 Python ``re`` 语法，``re.compile`` 后复用；
    * 替换内容可为字符串，或可调用对象 ``f(match) -> str``；
    * 规则应尽量“窄”——只命中确定需要修改的情形，避免误伤。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, List, Pattern, Tuple, Union

Replacement = Union[str, Callable[[re.Match], str]]


@dataclass(frozen=True)
class Rule:
    """一条正则替换规则。"""

    name: str
    description: str
    pattern: Pattern[str]
    replacement: Replacement


# ---------------------------------------------------------------------------
# 规则定义
# ---------------------------------------------------------------------------
def _colon_to_halfwidth(match: "re.Match[str]") -> str:
    """把命中片段（如 ``8：00``）中的全角冒号统一替换为半角。"""
    return match.group(0).replace("：", ":")


def _merge_math_hyphen(match: "re.Match[str]") -> str:
    """把 ``$A$-$B$`` 合并为 ``$A-B$``（去掉中间多余的 ``$``）。"""
    text = match.group(0)
    return "$" + text[1:-1].replace("$", "") + "$"


RULES: List[Rule] = [
    Rule(
        name="digit-colon-digit",
        description="数字之间的全角冒号“：”改为半角冒号“:”（时间、比例等）",
        # 匹配“数字：数字”整体（如 8：00、19：26、8：00：00、1：2），
        # 再在命中片段内把“：”改为“:”。中文冒号（前/后非数字）不受影响。
        pattern=re.compile(r"\d+(?:：\d+)+"),
        replacement=_colon_to_halfwidth,
    ),
    Rule(
        name="math-hyphen-merge",
        description="相邻行内公式之间的连字符应并入公式（如 $x$-$t$ → $x-t$）",
        # 匹配 $A$-$B$（可链式，如 $A$-$B$-$C$），把中间的 $ 去掉、保留连字符。
        # 仅匹配“公式-公式”形式：$x$ 与 $t$、$-5$、$a$-b 等不受影响。
        pattern=re.compile(r"\$[^$\n]+\$(?:-\$[^$\n]+\$)+"),
        replacement=_merge_math_hyphen,
    ),
    Rule(
        name="dfrac-to-frac",
        description="分数统一用 \\frac（\\dfrac → \\frac，行间会自动放大）",
        # 只命中命令 \dfrac 本身，\dfrac 后的 {...} 保持不变；
        # (?![A-Za-z]) 避免误伤 \dfracX 之类的其他命令。
        pattern=re.compile(r"\\dfrac(?![A-Za-z])"),
        replacement=r"\\frac",
    ),
]


def apply_rules(text: str) -> Tuple[str, List[Tuple[str, int]]]:
    """对文本依次应用全部规则。

    返回 ``(新文本, [(规则名, 替换次数), ...])``；只包含实际发生替换的规则。
    """
    changes: List[Tuple[str, int]] = []
    for rule in RULES:
        text, count = rule.pattern.subn(rule.replacement, text)
        if count:
            changes.append((rule.name, count))
    return text, changes


def scan_text(text: str) -> List[Tuple[int, str, str]]:
    """扫描文本，返回 ``[(行号, 规则名, 命中片段), ...]``（行号从 1 起）。"""
    hits: List[Tuple[int, str, str]] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for rule in RULES:
            for match in rule.pattern.finditer(line):
                hits.append((lineno, rule.name, match.group(0)))
    return hits

"""tools/textfix/__init__.py

gk-textfix：高考真题 LaTeX 文档共性问题正则处理模块。

对外导出：
    * ``Rule`` / ``RULES``  —— 规则定义
    * ``apply_rules``       —— 对文本应用全部规则
    * ``scan_text``         —— 扫描待修正位置（含行号）
    * ``fix_text`` / ``fix_file`` / ``iter_target_files`` —— 文件级处理
"""
from .rules import RULES, Rule, apply_rules, scan_text
from .textfix import fix_file, fix_text, iter_target_files

__all__ = [
    "Rule",
    "RULES",
    "apply_rules",
    "scan_text",
    "fix_file",
    "fix_text",
    "iter_target_files",
]

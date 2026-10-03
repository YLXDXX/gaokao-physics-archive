"""tools/test_review_to_ledger.py —— 复核结果 → 异常台账 合并测试。"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools import review_to_ledger as r


YEAR_MD = """# 异常记录 · 2000 年

| 地区 | 题号 | 类别 | 问题 | 处理建议 | 状态 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 上海 | 1 | 缺详解 | 无解析 | 占位 | 待补充 |
"""

NEW_MD = """# 异常记录 · 2000 年

> 引言

## 制作说明

说明文字。

---

## 待人工核验

| 地区 | 题号 | 类别 | 问题 | 处理建议 | 状态 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 北京 | 5 | 复合图 | 四图合一 | 原图呈现 | 待人工核验 |

---

## 已解决

| 地区 | 题号 | 类别 | 问题 | 处理建议 | 状态 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 上海 | 1 | 缺详解 | 无解析 | 占位 | 已解决 |
"""


class TestReviewToLedger(unittest.TestCase):
    def test_merge_new_format_sections(self):
        entries = [
            # 已有「已解决」行：更新处理建议
            {"year": "2000", "region": "上海", "number": "1", "category": "缺详解",
             "problem": "无解析", "action": "已补写解析", "status": "已解决"},
            # 已有「待人工核验」行：状态改为已解决 → 应移动到已解决分区
            {"year": "2000", "region": "北京", "number": "5", "category": "复合图",
             "problem": "四图合一", "action": "已拆分", "status": "已解决"},
            # 新条目 → 应新建「待补充」分区（置于最前）
            {"year": "2000", "region": "云南", "number": "3", "category": "缺详解",
             "problem": "缺解析", "action": "占位", "status": "待补充"},
        ]
        new_text, changes = r.merge_year(NEW_MD, entries)
        self.assertIn("| 上海 | 1 | 缺详解 | 无解析 | 已补写解析 | 已解决 |", new_text)
        self.assertIn("| 北京 | 5 | 复合图 | 四图合一 | 已拆分 | 已解决 |", new_text)
        self.assertIn("| 云南 | 3 | 缺详解 | 缺解析 | 占位 | 待补充 |", new_text)
        # 原「待人工核验」分区已空，应省略
        self.assertNotIn("## 待人工核验", new_text)
        # 分区顺序：待补充 → 已解决（已解决置末）
        self.assertLess(new_text.index("## 待补充"), new_text.index("## 已解决"))

    def test_merge_update_and_append(self):
        entries = [
            {"year": "2000", "region": "上海", "number": "1", "category": "缺详解",
             "problem": "无解析", "action": "已补写解析", "status": "已解决"},
            {"year": "2000", "region": "北京", "number": "5", "category": "复合图",
             "problem": "四图合一", "action": "原图呈现", "status": "待人工核验"},
        ]
        new_text, changes = r.merge_year(YEAR_MD, entries)
        self.assertTrue(any("更新" in c for c in changes))
        self.assertTrue(any("新增" in c for c in changes))
        self.assertIn("| 上海 | 1 | 缺详解 | 无解析 | 已补写解析 | 已解决 |", new_text)
        self.assertIn("| 北京 | 5 | 复合图 | 四图合一 | 原图呈现 | 待人工核验 |", new_text)

    def test_load_compact_and_bundle(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "r.json"
            p.write_text(json.dumps({
                "year": "2000", "region": "上海",
                "entries": [{"number": "2", "category": "文字", "problem": "错字",
                             "action": "更正", "status": "已解决"}]},
                ensure_ascii=False), encoding="utf-8")
            ents = r.load_entries([p])
            self.assertEqual(len(ents), 1)
            self.assertEqual(ents[0]["region"], "上海")
            self.assertEqual(ents[0]["number"], "2")

    def test_load_list_of_bundles(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "r.json"
            p.write_text(json.dumps([
                {"year": "2000", "region": "A", "number": "1", "category": "公式",
                 "problem": "x", "action": "y", "status": "已解决"},
                {"year": "2001", "region": "B", "number": "2", "category": "文字",
                 "problem": "z", "action": "w", "status": "待补充"},
            ], ensure_ascii=False), encoding="utf-8")
            ents = r.load_entries([p])
            self.assertEqual({e["year"] for e in ents}, {"2000", "2001"})


if __name__ == "__main__":
    unittest.main()

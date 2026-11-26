"""tools/test_proofread.py —— 交叉校对基础设施的纯函数测试。"""
from __future__ import annotations

import unittest

from tools import proofread as p


class TestCleanToken(unittest.TestCase):
    def test_zhu_paper_and_answer(self):
        self.assertEqual(p.clean_token("1978年全国卷物理"), (1978, "全国", False))
        self.assertEqual(p.clean_token("1978年全国卷物理答案"), (1978, "全国", True))
        self.assertEqual(p.clean_token("2003年全国旧课程卷理综物理"), (2003, "全国旧课程理综", False))
        self.assertEqual(p.clean_token("2005年北京春招卷物理"), (2005, "北京春招", False))
        self.assertEqual(p.clean_token("2015年浙江10月卷物理"), (2015, "10月浙江", False))

    def test_liu_noise(self):
        self.assertEqual(p.clean_token("293号2024年北京卷物理（教师版）"), (2024, "北京", False))
        self.assertEqual(p.clean_token("294号 2024年高考广东卷物理真题（教师版）"), (2024, "广东", False))
        self.assertEqual(p.clean_token("357号2026年河南卷（教师版）.docx"), (2026, "河南", False))
        self.assertEqual(p.clean_token("290号_2023年海南卷物理教师版"), (2023, "海南", False))
        self.assertEqual(p.clean_token("2007年全国1－卷教师版"), (2007, "全国1", False))
        self.assertEqual(p.clean_token("2015年福建卷物理+(教师版)"), (2015, "福建", False))

    def test_reorder_month_zhejiang(self):
        self.assertEqual(p.clean_token("2025浙江6月（教师版)二校"), (2025, "6月浙江", False))
        self.assertEqual(p.clean_token("2026年1月浙江"), (2026, "1月浙江", False))


class TestMatchToken(unittest.TestCase):
    def test_exact(self):
        region, conf, note = p.match_token("辽宁", 2024, {"辽宁", "北京"}, {})
        self.assertEqual((region, conf, note), ("辽宁", "exact", ""))

    def test_alias_and_year_priority(self):
        ov = {"aliases": {"*": {"黑吉辽": "黑吉辽内"},
                          "2024": {"黑吉辽": {"region": "辽宁", "confidence": "alias",
                                             "note": "同卷"}}}}
        region, conf, note = p.match_token("黑吉辽", 2024, {"辽宁", "黑吉辽内"}, ov)
        self.assertEqual(region, "辽宁")
        self.assertEqual(conf, "alias")
        self.assertIn("同卷", note)
        region, conf, _ = p.match_token("黑吉辽", 2025, {"辽宁", "黑吉辽内"}, ov)
        self.assertEqual((region, conf), ("黑吉辽内", "alias"))

    def test_explicit_null_is_source_only(self):
        ov = {"aliases": {"2003": {"全国旧课程": {"region": None,
                                                 "confidence": "uncertain",
                                                 "note": "未收"}}}}
        region, conf, note = p.match_token("全国旧课程", 2003, {"全国理综旧课程"}, ov)
        self.assertIsNone(region)
        self.assertEqual(conf, "source-only")
        self.assertIn("未收", note)

    def test_fuzzy_marks_uncertain(self):
        region, conf, note = p.match_token("全国旧课程", 2003, {"全国理综旧课程"}, {})
        self.assertEqual(conf, "fuzzy")
        self.assertEqual(region, "全国理综旧课程")
        self.assertTrue(note)


class TestAnomalyParsing(unittest.TestCase):
    def test_open_and_resolved_for_region(self):
        text = """## 待人工核验
| 地区 | 题号 | 类别 | 问题 | 处理建议 | 状态 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 辽宁 | 5 | 缺图 | 第 5 题缺图 | 补图 | 待人工核验 |
| 北京 | 1 | 文字 | 其它卷 | 忽略 | 待处理 |

## 已解决
| 地区 | 题号 | 类别 | 问题 | 处理建议 | 状态 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 辽宁 | 3 | 公式 | 分式误写 | 已改 \\frac | 已解决 |
| 辽宁 | 4 | 单位 | 裸单位 | 已用 PhyUnit | 已解决 |
"""
        items, resolved = p.parse_anomaly_text(text, "辽宁")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["number"], "5")
        self.assertEqual(items[0]["status"], "待人工核验")
        self.assertEqual(resolved, 2)


class TestNamingAndTable(unittest.TestCase):
    def test_normalized_name(self):
        self.assertEqual(p._normalized_name(2024, "辽宁", False), "2024_辽宁.pdf")
        self.assertEqual(p._normalized_name(2024, "辽宁", True), "2024_辽宁_答案.pdf")
        self.assertEqual(p._normalized_name(2024, "a/b", False), "2024_a_b.pdf")

    def test_collapse_label_notes(self):
        note = "朱玉亮：同一套；刘芳：同一套；刘芳：其它"
        self.assertEqual(p._collapse_label_notes(note), "朱玉亮/刘芳：同一套；刘芳：其它")

    def test_available(self):
        self.assertEqual(p._available({}), "无")
        self.assertEqual(p._available({"zhu": {}}), "朱")
        self.assertEqual(p._available({"zhu": {}, "liu": {}}), "朱+刘")
        self.assertEqual(p._available({"tian": {}, "zhu": {}, "liu": {}}), "天+朱+刘")


if __name__ == "__main__":
    unittest.main()

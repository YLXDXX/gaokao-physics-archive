"""tools/test_gen_index.py —— gen_index 解析/校验纯函数与端到端测试。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools import gen_index


def _make_repo(root: Path) -> None:
    (root / "试卷" / "2020" / "测试").mkdir(parents=True)
    tex = root / "试卷" / "2020" / "测试" / "测试.tex"
    tex.write_text("%% number: 1\n%% number: 2\n%% number: 3\n", encoding="utf-8")
    (root / "试卷" / "2020" / "测试" / "figs").mkdir()
    (root / "试卷" / "2020" / "测试" / "figs" / "01.svg").write_text("x")
    (root / "进度记录.md").write_text(
        "# 进度记录\n\n### 2020 年（1 套）\n\n"
        "| 地区 | 题数 | 状态 | 说明 | 异常记录 |\n"
        "| :--- | :-- | :--- | :--- | :--- |\n"
        "| 测试 | 3 | 已完成 | 测试卷 | [2020.md](异常记录/2020.md) |\n",
        encoding="utf-8")
    (root / "异常记录").mkdir()
    (root / "异常记录" / "2020.md").write_text(
        "# 异常记录 · 2020 年\n\n"
        "| 地区 | 题号 | 类别 | 问题 | 处理建议 | 状态 |\n"
        "| :--- | :--- | :--- | :--- | :--- | :--- |\n"
        "| 测试 | 1 | 公式 | 示例 | 已改 | 已解决 |\n",
        encoding="utf-8")
    (root / "试卷" / "2020" / "README.md").write_text(
        "# 2020 年试卷索引\n\n| 地区 |\n| :--- |\n| [测试](测试/) |\n", encoding="utf-8")
    (root / "README.md").write_text(
        "<!-- PROGRESS:START -->\n<!-- PROGRESS:END -->\n", encoding="utf-8")


class TestGenIndex(unittest.TestCase):
    def test_scan(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _make_repo(root)
            papers = gen_index.scan_papers(root)
            self.assertIn("2020", papers)
            self.assertEqual(papers["2020"]["测试"]["questions"], 3)

    def test_check_ok(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _make_repo(root)
            self.assertEqual(gen_index.check(root, verbose=False), [])

    def test_check_missing_row(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _make_repo(root)
            (root / "进度记录.md").write_text(
                "# 进度记录\n\n### 2020 年（1 套）\n\n"
                "| 地区 | 题数 | 状态 | 说明 | 异常记录 |\n"
                "| :--- | :-- | :--- | :--- | :--- |\n",
                encoding="utf-8")
            errs = gen_index.check(root, verbose=False)
            self.assertTrue(any("测试" in e for e in errs))

    def test_check_bad_status(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _make_repo(root)
            t = (root / "异常记录" / "2020.md").read_text(encoding="utf-8")
            (root / "异常记录" / "2020.md").write_text(
                t.replace("已解决", "搞定了"), encoding="utf-8")
            errs = gen_index.check(root, verbose=False)
            self.assertTrue(any("状态非法" in e for e in errs))

    def test_check_missing_category(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _make_repo(root)
            (root / "异常记录" / "2020.md").write_text(
                "# 异常记录 · 2020 年\n\n"
                "| 地区 | 题号 | 问题 | 处理建议 | 状态 |\n"
                "| :--- | :--- | :--- | :--- | :--- |\n"
                "| 测试 | 1 | 示例 | 已改 | 已解决 |\n",
                encoding="utf-8")
            errs = gen_index.check(root, verbose=False)
            self.assertTrue(any("类别" in e for e in errs))


if __name__ == "__main__":
    unittest.main()

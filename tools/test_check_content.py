#!/usr/bin/env python3
"""tools/test_check_content.py

``tools/check_content.py`` 的单元测试，重点校验**裸单位规则**（UNIT_RE）：
只识别“复合单位”（m/s、kg/m^3、V/m…）与少量“·”复合单位，不误伤
变量乘积（g·L、n·m）、图片尺寸（6.59cm）、线段名（ab/cd）等。

运行::

    python3 -m unittest tools.test_check_content
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_content  # noqa: E402


class TestUnitRegex(unittest.TestCase):
    # 应当命中（裸写的复合单位）
    POSITIVE = [
        "m/s", "km/h", "20m/s", "m/s^2", "m/s²", "m/s2",
        "kg/m^3", "kg/m³", "g/cm^3", "N/m", "N/cm", "V/m", "V/cm",
        "W/m^2", "Wb/m^2", "A/m", "J/kg", "mol/L", "rad/s", "r/min",
        "m^3/s", "m^3/h", "kW·h", r"kW\cdot h", "mA·h", "N·m", "J·s", "Ω·m",
        "kg·m/s", "m/s²",
    ]
    # 不应命中（变量乘积 / 图片尺寸 / 线段名 / 已用宏等）
    NEGATIVE = [
        r"g \cdot L", "v=s/t", "ab/cd", "6.59cm", "h=3.95cm",
        "mg", "nm", "mL", "E_{kC}", "W=UIt", "P=W/t", "F=ma", "N=mg",
        "2T", "3s", "2g", "x/m", "U/mA", "M/m", "p/V", "n/V",
        r"\Ums", r"3\Ums", r"\Ukgmc",
    ]

    def test_positive(self):
        for s in self.POSITIVE:
            self.assertIsNotNone(check_content.UNIT_RE.search(s),
                                 f"应命中却未命中：{s}")

    def test_negative(self):
        for s in self.NEGATIVE:
            self.assertIsNone(check_content.UNIT_RE.search(s),
                              f"不应命中却命中：{s}")


class TestCheckUnits(unittest.TestCase):
    def test_flags_compound(self):
        errs = []
        check_content.check_units("t.tex", "速度 $v=3m/s$ 与 $a=2m/s^2$", errs)
        self.assertEqual(len(errs), 2)

    def test_macro_not_flagged(self):
        errs = []
        check_content.check_units("t.tex", "速度 $v=3\\Ums$、$a=2\\Umsq$", errs)
        self.assertEqual(errs, [])

    def test_variable_product_not_flagged(self):
        errs = []
        check_content.check_units("t.tex", "$G=mg$、$W=UIt$、图宽 $6.59cm$", errs)
        self.assertEqual(errs, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)

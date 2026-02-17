import unittest
from decimal import Decimal

from budget_audit.services.normalization import (
    build_embedding_text,
    normalize_tax_flag,
    normalize_text,
    normalize_text_no_space,
    parse_decimal,
    parse_price_range,
)


class NormalizationTests(unittest.TestCase):
    def test_normalize_text(self):
        self.assertEqual(normalize_text("  普通  硅酸盐 水泥 "), "普通 硅酸盐 水泥")
        self.assertEqual(normalize_text_no_space(" 32.5 级  散装 "), "32.5级散装")

    def test_normalize_tax_flag(self):
        self.assertTrue(normalize_tax_flag("是"))
        self.assertTrue(normalize_tax_flag("含税"))
        self.assertFalse(normalize_tax_flag("否"))
        self.assertFalse(normalize_tax_flag("不含税"))

    def test_parse_decimal(self):
        self.assertEqual(parse_decimal("1,234.56"), Decimal("1234.56"))
        self.assertEqual(parse_decimal("382.22元"), Decimal("382.22"))
        self.assertIsNone(parse_decimal(""))

    def test_parse_price_range(self):
        low, high = parse_price_range("285.80-515.00")
        self.assertEqual(low, Decimal("285.80"))
        self.assertEqual(high, Decimal("515.00"))

        low, high = parse_price_range("90.00~115.00")
        self.assertEqual(low, Decimal("90.00"))
        self.assertEqual(high, Decimal("115.00"))

        low, high = parse_price_range("120")
        self.assertEqual(low, Decimal("120"))
        self.assertEqual(high, Decimal("120"))

    def test_build_embedding_text(self):
        text = build_embedding_text("矿渣硅酸盐水泥", "32.5级 散装", "t", True)
        self.assertIn("材料名称:矿渣硅酸盐水泥", text)
        self.assertIn("规格型号:32.5级 散装", text)
        self.assertIn("单位:t", text)
        self.assertIn("税标识:含税", text)


if __name__ == "__main__":
    unittest.main()


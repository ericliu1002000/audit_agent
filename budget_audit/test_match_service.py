import unittest
import os
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "audit_agent.settings")

import django

django.setup()

from budget_audit.services.match_service import match_vendor_quote_excel


class MatchServiceTests(unittest.TestCase):
    @patch("budget_audit.services.match_service._judge_candidates_with_deepseek")
    @patch("budget_audit.services.match_service.BudgetPriceItem")
    @patch("budget_audit.services.match_service.get_budget_milvus_manager")
    @patch("budget_audit.services.match_service.call_siliconflow_qwen3_embedding_api")
    @patch("budget_audit.services.match_service.parse_vendor_quote_excel")
    def test_match_vendor_quote_excel_happy_path(
        self,
        mock_parse,
        mock_embed,
        mock_get_manager,
        mock_model,
        mock_judge,
    ):
        mock_parse.return_value = [
            {
                "row_number": 5,
                "material_name": "32.5级矿渣水泥",
                "spec_model": "32.5级 散装",
                "unit": "t",
                "vendor_price": Decimal("390.00"),
                "is_tax_included": True,
                "embedding_text": "材料名称:32.5级矿渣水泥 | 规格型号:32.5级 散装 | 单位:t | 税标识:含税",
            }
        ]
        mock_embed.return_value = [0.1, 0.2, 0.3, 0.4]

        manager = Mock()
        manager.search_candidates.return_value = [
            {"item_id": 1, "score": 0.86},
            {"item_id": 2, "score": 0.84},
        ]
        mock_get_manager.return_value = manager

        std_1 = SimpleNamespace(
            id=1,
            material_name="矿渣硅酸盐水泥",
            spec_model="32.5级 袋装",
            unit="t",
            base_price=Decimal("390.83"),
            price_low=Decimal("313.30"),
            price_high=Decimal("515.00"),
            is_tax_included=True,
        )
        std_2 = SimpleNamespace(
            id=2,
            material_name="矿渣硅酸盐水泥",
            spec_model="32.5级 散装",
            unit="t",
            base_price=Decimal("382.22"),
            price_low=Decimal("285.80"),
            price_high=Decimal("515.00"),
            is_tax_included=True,
        )
        mock_model.objects.filter.return_value = [std_1, std_2]

        mock_judge.return_value = {
            "judgement": "一致",
            "matched_id": 2,
            "reason": "规格、单位、税标识一致",
            "confidence": 0.93,
        }

        results = match_vendor_quote_excel(uploaded_file=Mock(), top_k=3)

        self.assertEqual(len(results), 1)
        row = results[0]
        self.assertEqual(row["matched_id"], 2)
        self.assertEqual(row["judgement"], "一致")
        self.assertEqual(row["reason"], "规格、单位、税标识一致")
        self.assertEqual(row["confidence"], 0.93)
        self.assertEqual(row["matched_material_name"], "矿渣硅酸盐水泥")
        self.assertAlmostEqual(row["deviation_rate"], 2.04, places=2)
        self.assertTrue(row["in_range"])
        self.assertGreaterEqual(len(row["candidates"]), 1)

    @patch("budget_audit.services.match_service._judge_candidates_with_deepseek")
    @patch("budget_audit.services.match_service.BudgetPriceItem")
    @patch("budget_audit.services.match_service.get_budget_milvus_manager")
    @patch("budget_audit.services.match_service.call_siliconflow_qwen3_embedding_api")
    @patch("budget_audit.services.match_service.parse_vendor_quote_excel")
    def test_match_vendor_quote_excel_no_candidates(
        self,
        mock_parse,
        mock_embed,
        mock_get_manager,
        mock_model,
        mock_judge,
    ):
        mock_parse.return_value = [
            {
                "row_number": 1,
                "material_name": "未知材料",
                "spec_model": "",
                "unit": "t",
                "vendor_price": Decimal("100.00"),
                "is_tax_included": True,
                "embedding_text": "材料名称:未知材料 | 规格型号: | 单位:t | 税标识:含税",
            }
        ]
        mock_embed.return_value = [0.1, 0.2, 0.3, 0.4]
        manager = Mock()
        manager.search_candidates.return_value = []
        mock_get_manager.return_value = manager
        mock_model.objects.filter.return_value = []
        mock_judge.return_value = {
            "judgement": "不确定",
            "matched_id": None,
            "reason": "未召回候选",
            "confidence": 0.0,
        }

        results = match_vendor_quote_excel(uploaded_file=Mock(), top_k=3)

        self.assertEqual(results[0]["matched_id"], None)
        self.assertEqual(results[0]["judgement"], "不确定")
        self.assertIsNone(results[0]["deviation_rate"])
        self.assertEqual(results[0]["candidates"], [])


if __name__ == "__main__":
    unittest.main()

import unittest
import os
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "audit_agent.settings")

import django

django.setup()

from budget_audit.services.standard_sync import import_standard_price_excel


class StandardSyncTests(unittest.TestCase):
    @patch("budget_audit.services.standard_sync.call_siliconflow_qwen3_embedding_api")
    @patch("budget_audit.services.standard_sync.get_budget_milvus_manager")
    @patch("budget_audit.services.standard_sync.parse_standard_price_excel")
    @patch("budget_audit.services.standard_sync.BudgetPriceItem")
    def test_import_standard_price_excel_flow(
        self,
        mock_model,
        mock_parse,
        mock_get_milvus,
        mock_embed,
    ):
        row_1 = {
            "material_name": "矿渣硅酸盐水泥",
            "spec_model": "32.5级 散装",
            "unit": "t",
            "base_price": 382.22,
            "price_low": 285.80,
            "price_high": 515.00,
            "is_tax_included": True,
            "publish_month": "2025-12",
            "region": "天津市",
            "embedding_text": "材料名称:矿渣硅酸盐水泥 | 规格型号:32.5级 散装 | 单位:t | 税标识:含税",
        }
        row_2 = {
            "material_name": "普通硅酸盐水泥",
            "spec_model": "42.5级 袋装",
            "unit": "t",
            "base_price": 458.44,
            "price_low": 379.76,
            "price_high": 590.00,
            "is_tax_included": True,
            "publish_month": "2025-12",
            "region": "天津市",
            "embedding_text": "材料名称:普通硅酸盐水泥 | 规格型号:42.5级 袋装 | 单位:t | 税标识:含税",
        }
        mock_parse.return_value = [row_1, row_2]

        old_qs = Mock()
        old_qs.values_list.return_value = [11, 12]
        mock_model.objects.filter.return_value = old_qs

        create_counter = {"n": 0}

        def _create(**kwargs):
            create_counter["n"] += 1
            return SimpleNamespace(
                id=100 + create_counter["n"],
                unit=kwargs["unit"],
                is_tax_included=kwargs["is_tax_included"],
                embedding_text=kwargs["embedding_text"],
            )

        mock_model.objects.create.side_effect = _create
        mock_embed.return_value = [0.1, 0.2, 0.3, 0.4]

        milvus_manager = Mock()
        mock_get_milvus.return_value = milvus_manager

        result = import_standard_price_excel(
            uploaded_file=Mock(),
            region="天津市",
            publish_month="2025-12",
            replace_existing=True,
            default_tax_included=True,
        )

        self.assertEqual(result["parsed"], 2)
        self.assertEqual(result["created"], 2)
        self.assertEqual(result["deleted"], 2)
        self.assertEqual(result["indexed"], 2)
        self.assertEqual(result["index_failed"], 0)

        milvus_manager.delete_items.assert_called_once_with([11, 12])
        self.assertEqual(milvus_manager.upsert_item.call_count, 2)
        self.assertEqual(mock_embed.call_count, 2)


if __name__ == "__main__":
    unittest.main()

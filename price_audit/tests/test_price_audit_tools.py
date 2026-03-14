"""价格审核工具测试。"""

from __future__ import annotations

from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from price_audit.agent.tools import PriceAuditToolCollector, PriceAuditToolset
from price_audit.constants import EXHIBITION_CENTER_NEC, PROJECT_NATURE_PERMANENT
from price_audit.models import GovernmentPriceBatch, GovernmentPriceItem
from price_audit.tests.helpers import (
    TempMediaRootMixin,
    create_submission_row,
    create_submission_with_workbook,
)


User = get_user_model()


class PriceAuditToolTests(TempMediaRootMixin, TestCase):
    """验证标准价候选工具。"""

    def setUp(self):
        self.user = User.objects.create_user(username="tool", password="Testpass123")
        self.batch = GovernmentPriceBatch.objects.create(
            region_name="天津",
            year=2026,
            is_active=True,
            vector_status=GovernmentPriceBatch.VectorStatus.ACTIVE,
        )
        self.item = GovernmentPriceItem.objects.create(
            batch=self.batch,
            row_no=1,
            material_name_raw="地台制作",
            material_name_normalized="地台制作",
            spec_model_raw="竹胶板",
            spec_model_normalized="竹胶板",
            unit_raw="㎡",
            unit_normalized="㎡",
            benchmark_price="70.00",
            price_min="60.00",
            price_max="80.00",
            description="常规展台地台制作",
            is_tax_included=True,
            embedding_text="材料名称:地台制作 | 规格型号:竹胶板 | 单位:㎡",
            raw_row_data={},
        )
        self.other_item = GovernmentPriceItem.objects.create(
            batch=self.batch,
            row_no=2,
            material_name_raw="地台制作",
            material_name_normalized="地台制作",
            spec_model_raw="木结构",
            spec_model_normalized="木结构",
            unit_raw="m",
            unit_normalized="m",
            benchmark_price="90.00",
            price_min="80.00",
            price_max="100.00",
            description="包边类结果",
            is_tax_included=True,
            embedding_text="材料名称:地台制作 | 规格型号:木结构 | 单位:m",
            raw_row_data={},
        )
        self.submission = create_submission_with_workbook(
            created_by=self.user,
            price_batch=self.batch,
            exhibition_center_id=EXHIBITION_CENTER_NEC,
            project_nature=PROJECT_NATURE_PERMANENT,
        )
        self.parent_row = create_submission_row(
            self.submission,
            excel_row_no=4,
            sequence_no="2",
            row_type="group",
            fee_type="特装展台搭建",
            submitted_unit="-",
            submitted_unit_price=None,
            submitted_quantity=None,
            submitted_days=None,
            submitted_amount="1200.0000",
            budget_note="特装父项",
        )
        self.row = create_submission_row(
            self.submission,
            excel_row_no=5,
            sequence_no="2.1",
            parent_sequence_no="2",
            fee_type="特装展台-地台制作",
            submitted_unit="平米",
            submitted_unit_price="100.00",
            submitted_quantity="10.00",
            submitted_days=None,
            submitted_amount="1000.00",
            budget_note="地台制作说明",
        )

    def test_get_submission_row_context_includes_parent_row(self):
        """上下文工具应返回当前行及父项信息。"""

        toolset = PriceAuditToolset(self.row)
        context = toolset.get_submission_row_context()

        self.assertEqual(context["submission_id"], self.submission.id)
        self.assertEqual(context["exhibition_center"]["id"], EXHIBITION_CENTER_NEC)
        self.assertEqual(context["exhibition_center"]["name"], "天津国家会展中心")
        self.assertEqual(context["project_nature"]["id"], PROJECT_NATURE_PERMANENT)
        self.assertEqual(context["project_nature"]["name"], "常设陈列")
        self.assertEqual(context["row"]["row_id"], self.row.id)
        self.assertEqual(context["parent_row"]["sequence_no"], self.parent_row.sequence_no)
        self.assertEqual(context["parent_row"]["fee_type"], self.parent_row.fee_type)

    def test_get_submission_row_context_returns_empty_parent_when_not_nested(self):
        """没有父项的行应返回空 parent_row。"""

        standalone_row = create_submission_row(
            self.submission,
            excel_row_no=3,
            sequence_no="1",
            parent_sequence_no="",
            fee_type="场地租",
            submitted_unit="平米",
        )

        toolset = PriceAuditToolset(standalone_row)
        context = toolset.get_submission_row_context()

        self.assertIsNone(context["parent_row"]["sequence_no"])
        self.assertIsNone(context["parent_row"]["fee_type"])

    @patch("price_audit.agent.tools.call_embedding_api", return_value=[0.1, 0.2, 0.3, 0.4])
    @patch("price_audit.agent.tools.get_price_audit_milvus_manager")
    def test_search_standard_price_candidates_returns_enriched_results(
        self,
        manager_mock,
        _embedding_mock,
    ):
        """工具应返回回表后的标准价候选。"""

        manager = Mock()
        manager.search_candidates.return_value = [
            {
                "item_id": self.other_item.id,
                "batch_id": self.batch.id,
                "year": self.batch.year,
                "region_name": self.batch.region_name,
                "unit": "m",
                "embedding_text": self.other_item.embedding_text,
                "score": 0.99,
            },
            {
                "item_id": self.item.id,
                "batch_id": self.batch.id,
                "year": self.batch.year,
                "region_name": self.batch.region_name,
                "unit": "㎡",
                "embedding_text": self.item.embedding_text,
                "score": 0.75,
            }
        ]
        manager_mock.return_value = manager

        toolset = PriceAuditToolset(self.row)
        result = toolset.search_standard_price_candidates("地台制作", "平米", 3)

        self.assertEqual(result["query"], "地台制作")
        self.assertEqual(len(result["items"]), 2)
        self.assertEqual(result["items"][0]["item_id"], self.item.id)
        self.assertEqual(result["items"][0]["benchmark_price"], "70.00")
        self.assertNotIn("expr", result["items"][0])

    @patch("price_audit.agent.tools.call_embedding_api", return_value=[0.1, 0.2, 0.3, 0.4])
    @patch("price_audit.agent.tools.get_price_audit_milvus_manager")
    def test_search_standard_price_candidates_falls_back_to_row_context_and_filters_missing_items(
        self,
        manager_mock,
        _embedding_mock,
    ):
        """空 query 时应使用行上下文，且回表缺失项应被过滤。"""

        manager = Mock()
        manager.search_candidates.return_value = [
            {"item_id": 999999, "score": 0.99},
            {"item_id": self.item.id, "score": 0.80},
        ]
        manager_mock.return_value = manager

        toolset = PriceAuditToolset(self.row)
        result = toolset.search_standard_price_candidates("", "", 3)

        self.assertEqual(result["query"], self.row.fee_type)
        self.assertEqual(result["unit"], self.row.submitted_unit)
        self.assertEqual([item["item_id"] for item in result["items"]], [self.item.id])

    def test_tool_collector_deduplicates_candidates_by_item_id(self):
        """同一 item 多次命中时只保留一份证据。"""

        collector = PriceAuditToolCollector()

        collector.add_candidates([{"item_id": 1, "score": 0.9}, {"item_id": 2, "score": 0.8}])
        collector.add_candidates([{"item_id": 1, "score": 0.95}, {"item_id": 3, "score": 0.7}])

        self.assertEqual([item["item_id"] for item in collector.candidates], [1, 2, 3])

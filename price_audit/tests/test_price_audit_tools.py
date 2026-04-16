"""价格审核工具测试。"""

from __future__ import annotations

from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from price_audit.agent.tools import PriceAuditToolCollector, PriceAuditToolset
from price_audit.constants import (
    EXHIBITION_CENTER_MEIJIANG,
    EXHIBITION_CENTER_NEC,
    PROJECT_NATURE_PERMANENT,
    PROJECT_NATURE_TEMPORARY,
)
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
        self.sibling_row = create_submission_row(
            self.submission,
            excel_row_no=6,
            sequence_no="2.2",
            parent_sequence_no="2",
            fee_type="特装展台-地台包边",
            submitted_unit="m",
            submitted_unit_price="20.00",
            submitted_quantity="10.00",
            submitted_days=None,
            submitted_amount="200.00",
            budget_note="地台包边说明",
        )
        self.same_type_row = create_submission_row(
            self.submission,
            excel_row_no=7,
            sequence_no="3.1",
            parent_sequence_no="3",
            fee_type="普通展台-地台制作",
            submitted_unit="㎡",
            submitted_unit_price="80.00",
            submitted_quantity="8.00",
            submitted_days=None,
            submitted_amount="640.00",
            budget_note="普通展台地台制作说明",
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
        self.assertIn("submission_overview", context)
        self.assertIn("current_group_context", context)
        self.assertIn("same_fee_type_context", context)
        self.assertIn("rule_hints", context)
        self.assertEqual(context["submission_overview"]["leaf_row_count"], 3)
        self.assertEqual(context["current_group_context"]["parent_row"]["sequence_no"], "2")
        self.assertEqual(len(context["current_group_context"]["group_rows"]), 2)
        self.assertIn(
            "3.1",
            [item["sequence_no"] for item in context["same_fee_type_context"]],
        )

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
        self.assertIsNone(context["current_group_context"]["parent_row"])
        self.assertEqual(context["current_group_context"]["group_rows"], [])

    def test_get_submission_row_context_marks_line_items_as_meter_based(self):
        """包边/踢脚线类项目应提示按米审核。"""

        line_row = create_submission_row(
            self.submission,
            excel_row_no=8,
            sequence_no="4.1",
            fee_type="特装展台-地台包边",
            submitted_unit="㎡",
            submitted_unit_price="85.00",
            submitted_quantity="216.00",
            submitted_days=None,
            submitted_amount="18360.00",
            budget_note="铝合金收边条",
        )

        context = PriceAuditToolset(line_row).get_submission_row_context()

        self.assertEqual(context["rule_hints"]["fee_category"], "fabrication")
        self.assertEqual(context["rule_hints"]["preferred_units"], ["m"])

    def test_get_submission_row_context_marks_print_items_as_area_based(self):
        """喷绘类项目应提示按平方米审核。"""

        print_row = create_submission_row(
            self.submission,
            excel_row_no=9,
            sequence_no="5.1",
            fee_type="特装展台-喷绘画面",
            submitted_unit="项",
            submitted_unit_price="6000.00",
            submitted_quantity="1.00",
            submitted_days=None,
            submitted_amount="6000.00",
            budget_note="环保写真布",
        )

        context = PriceAuditToolset(print_row).get_submission_row_context()

        self.assertEqual(context["rule_hints"]["fee_category"], "fabrication")
        self.assertEqual(context["rule_hints"]["preferred_units"], ["㎡"])

    def test_get_submission_row_context_marks_simple_reception_desk_as_rental_for_temporary_project(self):
        """临时展会中的简易接待台应优先按租赁审。"""

        temporary_submission = create_submission_with_workbook(
            created_by=self.user,
            price_batch=self.batch,
            exhibition_center_id=EXHIBITION_CENTER_MEIJIANG,
            project_nature=PROJECT_NATURE_TEMPORARY,
            original_filename="temporary.xlsx",
        )
        simple_desk_row = create_submission_row(
            temporary_submission,
            excel_row_no=3,
            sequence_no="1",
            fee_type="普通展台-简易接待台",
            submitted_unit="个",
            submitted_unit_price="500.00",
            submitted_quantity="10.00",
            submitted_days="1.00",
            submitted_amount="5000.00",
            budget_note="标准展位配套接待台",
        )

        context = PriceAuditToolset(simple_desk_row).get_submission_row_context()

        self.assertEqual(context["rule_hints"]["preferred_pricing_mode"], "rental")
        self.assertEqual(context["rule_hints"]["fee_category"], "standardized_item")

    def test_get_submission_row_context_marks_official_fee_items(self):
        """场馆官方收费类项目应有 official 提示。"""

        official_row = create_submission_row(
            self.submission,
            excel_row_no=10,
            sequence_no="6",
            fee_type="施工管理费",
            submitted_unit="㎡",
            submitted_unit_price="20.00",
            submitted_quantity="100.00",
            submitted_days=None,
            submitted_amount="2000.00",
            budget_note="展馆收取",
        )

        context = PriceAuditToolset(official_row).get_submission_row_context()

        self.assertEqual(context["rule_hints"]["fee_category"], "official_fee")
        self.assertEqual(context["rule_hints"]["preferred_pricing_mode"], "official")

    def test_get_submission_row_context_exposes_duplicate_pricing_risk_keywords(self):
        """工厂制作人工应提示与喷绘等重复计价风险。"""

        labor_row = create_submission_row(
            self.submission,
            excel_row_no=11,
            sequence_no="7",
            fee_type="特装展台-工厂制作人工",
            submitted_unit="项",
            submitted_unit_price="2500.00",
            submitted_quantity="1.00",
            submitted_days=None,
            submitted_amount="2500.00",
            budget_note="含喷绘画面制作",
        )

        context = PriceAuditToolset(labor_row).get_submission_row_context()

        self.assertIn("喷绘", context["rule_hints"]["duplicate_risk_keywords"])

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
        self.assertTrue(result["has_valid_price"])
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

    @patch("price_audit.agent.tools.call_embedding_api", return_value=[0.1, 0.2, 0.3, 0.4])
    @patch("price_audit.agent.tools.get_price_audit_milvus_manager")
    def test_build_evidence_json_marks_local_standard_when_candidates_have_valid_price(
        self,
        manager_mock,
        _embedding_mock,
    ):
        """本地标准价足够时，应标记为 local_standard。"""

        manager = Mock()
        manager.search_candidates.return_value = [
            {
                "item_id": self.item.id,
                "batch_id": self.batch.id,
                "year": self.batch.year,
                "region_name": self.batch.region_name,
                "unit": "㎡",
                "embedding_text": self.item.embedding_text,
                "score": 0.95,
            }
        ]
        manager_mock.return_value = manager

        toolset = PriceAuditToolset(self.row)
        toolset.search_standard_price_candidates("地台制作", "㎡", 3)
        evidence_json = toolset.build_evidence_json(
            reviewed_unit_price="70",
            reviewed_amount="700",
            notes=["参考本地标准价"],
        )

        self.assertEqual(evidence_json["pricing_basis"], "local_standard")
        self.assertEqual(evidence_json["price_sources"], [])
        self.assertEqual(len(evidence_json["candidates"]), 1)

    @patch("price_audit.agent.tools.call_embedding_api", return_value=[0.1, 0.2, 0.3, 0.4])
    @patch("price_audit.agent.tools.get_price_audit_milvus_manager")
    def test_build_evidence_json_marks_missing_local_price_as_insufficient_evidence(
        self,
        manager_mock,
        _embedding_mock,
    ):
        """本地标准价不足时，应标记为 insufficient_evidence。"""

        manager = Mock()
        manager.search_candidates.return_value = []
        manager_mock.return_value = manager

        toolset = PriceAuditToolset(self.row)
        toolset.search_standard_price_candidates("地台制作", "㎡", 3)
        evidence_json = toolset.build_evidence_json(
            reviewed_unit_price="100",
            reviewed_amount="1000",
            notes=["本地标准价证据不足"],
        )

        self.assertEqual(evidence_json["pricing_basis"], "insufficient_evidence")
        self.assertEqual(evidence_json["price_sources"], [])
        self.assertEqual(evidence_json["candidates"], [])

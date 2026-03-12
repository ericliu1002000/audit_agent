"""逐行审核服务测试。"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from price_audit.agent.row_agent import RowAuditOutput
from price_audit.models import GovernmentPriceBatch, PriceAuditRowDecision
from price_audit.services.row_review_service import _calculate_amount, review_leaf_row
from price_audit.tests.helpers import (
    TempMediaRootMixin,
    create_submission_row,
    create_submission_with_workbook,
)


User = get_user_model()


class RowReviewServiceTests(TempMediaRootMixin, TestCase):
    """验证逐行审核的回退与分支逻辑。"""

    def setUp(self):
        self.user = User.objects.create_user(username="row-review", password="Testpass123")
        self.batch = GovernmentPriceBatch.objects.create(
            region_name="天津",
            year=2026,
            is_active=True,
            vector_status=GovernmentPriceBatch.VectorStatus.ACTIVE,
        )
        self.submission = create_submission_with_workbook(
            created_by=self.user,
            price_batch=self.batch,
        )

    def test_calculate_amount_multiplies_all_available_factors(self):
        """金额重算应乘上所有非空因子。"""

        self.assertEqual(
            _calculate_amount(Decimal("70"), Decimal("10"), Decimal("3")),
            Decimal("2100"),
        )
        self.assertEqual(
            _calculate_amount(Decimal("70"), Decimal("10"), None),
            Decimal("700"),
        )
        self.assertIsNone(_calculate_amount(None, None, None))

    @patch("price_audit.services.row_review_service.review_row_with_agent")
    def test_review_leaf_row_marks_unchanged_when_agent_returns_same_values(self, review_mock):
        """审核值不变时应标记 unchanged。"""

        row = create_submission_row(self.submission)
        review_mock.return_value = (
            RowAuditOutput(
                reviewed_unit="平米",
                reviewed_unit_price="9",
                reviewed_quantity="100",
                reviewed_days="3",
                reviewed_amount="2700",
                reason=" 价格合理 ",
                notes=["与送审一致"],
            ),
            {"candidates": [], "notes": ["与送审一致"]},
        )

        decision = review_leaf_row(row)

        self.assertEqual(decision.status, PriceAuditRowDecision.Status.COMPLETED)
        self.assertEqual(decision.result_type, PriceAuditRowDecision.ResultType.UNCHANGED)
        self.assertEqual(decision.reviewed_amount, Decimal("2700"))
        self.assertEqual(decision.reason, "价格合理")
        self.assertEqual(decision.evidence_json["notes"], ["与送审一致"])

    @patch("price_audit.services.row_review_service.review_row_with_agent")
    def test_review_leaf_row_uses_agent_amount_and_falls_back_other_fields(self, review_mock):
        """只返回审核金额时，其余字段应回退到送审值。"""

        row = create_submission_row(
            self.submission,
            fee_type="电费",
            submitted_unit="",
            submitted_unit_price=None,
            submitted_quantity=None,
            submitted_days=None,
            submitted_amount="500.0000",
        )
        review_mock.return_value = (
            RowAuditOutput(
                reviewed_amount="400",
                reason="按实际用电需求下调。",
                notes=["调整电费"],
            ),
            {"candidates": [], "notes": ["调整电费"]},
        )

        decision = review_leaf_row(row)

        self.assertEqual(decision.result_type, PriceAuditRowDecision.ResultType.ADJUSTED)
        self.assertEqual(decision.reviewed_unit, "")
        self.assertIsNone(decision.reviewed_unit_price)
        self.assertIsNone(decision.reviewed_quantity)
        self.assertIsNone(decision.reviewed_days)
        self.assertEqual(decision.reviewed_amount, Decimal("400"))
        self.assertEqual(decision.reduction_amount, Decimal("100.0000"))

    @patch("price_audit.services.row_review_service.review_row_with_agent")
    def test_review_leaf_row_recalculates_amount_from_unit_price_quantity_and_days(self, review_mock):
        """审核金额缺失时应按单价、数量、天数重算。"""

        row = create_submission_row(
            self.submission,
            submitted_unit="人/天",
            submitted_unit_price="500.0000",
            submitted_quantity="2.0000",
            submitted_days="3.0000",
            submitted_amount="3000.0000",
        )
        review_mock.return_value = (
            RowAuditOutput(
                reviewed_unit="人/天",
                reviewed_unit_price="450",
                reviewed_quantity="2",
                reviewed_days="3",
                reason="按常规人工单价调整。",
                notes=[],
            ),
            {"candidates": [], "notes": []},
        )

        decision = review_leaf_row(row)

        self.assertEqual(decision.reviewed_amount, Decimal("2700"))
        self.assertEqual(decision.reduction_amount, Decimal("300.0000"))

    @patch("price_audit.services.row_review_service.review_row_with_agent")
    def test_review_leaf_row_recalculates_amount_without_days(self, review_mock):
        """缺少天数时应按单价和数量重算。"""

        row = create_submission_row(
            self.submission,
            sequence_no="2.1",
            fee_type="特装展台-地台制作",
            submitted_unit="㎡",
            submitted_unit_price="100.0000",
            submitted_quantity="10.0000",
            submitted_days=None,
            submitted_amount="1000.0000",
        )
        review_mock.return_value = (
            RowAuditOutput(
                reviewed_unit="㎡",
                reviewed_unit_price="70",
                reviewed_quantity="10",
                reason="参考标准价下调。",
                notes=[],
            ),
            {"candidates": [], "notes": []},
        )

        decision = review_leaf_row(row)

        self.assertEqual(decision.result_type, PriceAuditRowDecision.ResultType.ADJUSTED)
        self.assertEqual(decision.reviewed_amount, Decimal("700"))

    @patch("price_audit.services.row_review_service.review_row_with_agent")
    def test_review_leaf_row_falls_back_to_submitted_amount_when_calculation_is_impossible(
        self,
        review_mock,
    ):
        """既无审核金额又无法重算时应保留送审金额。"""

        row = create_submission_row(
            self.submission,
            fee_type="设计费",
            submitted_unit="",
            submitted_unit_price=None,
            submitted_quantity=None,
            submitted_days=None,
            submitted_amount="800.0000",
        )
        review_mock.return_value = (
            RowAuditOutput(
                reviewed_unit="",
                reason="缺少可靠证据，暂保留送审金额。",
                notes=[],
            ),
            {"candidates": [], "notes": []},
        )

        decision = review_leaf_row(row)

        self.assertEqual(decision.result_type, PriceAuditRowDecision.ResultType.UNCHANGED)
        self.assertEqual(decision.reviewed_amount, Decimal("800.0000"))
        self.assertEqual(decision.reduction_amount, Decimal("0.0000"))

    @patch("price_audit.services.row_review_service.review_row_with_agent")
    def test_review_leaf_row_marks_failed_when_agent_raises(self, review_mock):
        """agent 异常时应写 failed decision。"""

        row = create_submission_row(self.submission)
        review_mock.side_effect = RuntimeError("AI 审核失败")

        decision = review_leaf_row(row)

        self.assertEqual(decision.status, PriceAuditRowDecision.Status.FAILED)
        self.assertEqual(decision.result_type, "")
        self.assertEqual(decision.reason, "")
        self.assertEqual(decision.evidence_json, {})
        self.assertIn("AI 审核失败", decision.error_message)

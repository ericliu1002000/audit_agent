"""价格审核报告服务测试。"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from price_audit.models import GovernmentPriceBatch
from price_audit.services.report_service import build_submission_report
from price_audit.tests.helpers import (
    TempMediaRootMixin,
    create_row_decision,
    create_submission_row,
    create_submission_with_workbook,
)


User = get_user_model()


class ReportServiceTests(TempMediaRootMixin, TestCase):
    """验证 report_json 构造逻辑。"""

    def setUp(self):
        self.user = User.objects.create_user(username="report", password="Testpass123")
        self.batch = GovernmentPriceBatch.objects.create(
            region_name="天津",
            year=2026,
            is_active=True,
            vector_status=GovernmentPriceBatch.VectorStatus.ACTIVE,
        )
        self.submission = create_submission_with_workbook(
            created_by=self.user,
            price_batch=self.batch,
            status="completed",
        )
        self.submission.submitted_total_amount = "4500.0000"
        self.submission.reviewed_total_amount = "4100.0000"
        self.submission.reduction_total_amount = "400.0000"
        self.submission.save(
            update_fields=[
                "submitted_total_amount",
                "reviewed_total_amount",
                "reduction_total_amount",
                "updated_at",
            ]
        )

    def test_build_submission_report_counts_statuses_and_serializes_decimals(self):
        """报告应统计 completed/failed/skipped，并把 Decimal 转成字符串。"""

        row1 = create_submission_row(self.submission, excel_row_no=3, sequence_no="1", fee_type="场地租")
        row2 = create_submission_row(self.submission, excel_row_no=4, sequence_no="2", fee_type="电费")
        row3 = create_submission_row(self.submission, excel_row_no=5, sequence_no="", fee_type="税费")

        create_row_decision(row1, reviewed_amount="2600.0000", reduction_amount="100.0000")
        create_row_decision(
            row2,
            status="failed",
            result_type="",
            reviewed_amount=None,
            reduction_amount=None,
            reason="",
            error_message="AI 审核失败",
        )
        create_row_decision(
            row3,
            result_type="skipped",
            reviewed_amount="100.0000",
            reduction_amount="0.0000",
            reason="税费当前版本不做智能审核，暂按送审金额保留。",
        )

        report = build_submission_report(self.submission)

        self.assertEqual(report["statistics"]["total_rows"], 3)
        self.assertEqual(report["statistics"]["completed_rows"], 2)
        self.assertEqual(report["statistics"]["failed_rows"], 1)
        self.assertEqual(report["statistics"]["skipped_rows"], 1)
        self.assertEqual(report["submitted_total_amount"], "4500.0000")
        self.assertEqual(report["rows"][0]["submitted_amount"], "2700.0000")
        self.assertEqual(report["rows"][1]["decision"]["error_message"], "AI 审核失败")

    def test_build_submission_report_handles_rows_without_decision(self):
        """缺少 decision 的行也应安全进入报告。"""

        row = create_submission_row(self.submission, excel_row_no=3, sequence_no="1", fee_type="场地租")

        report = build_submission_report(self.submission)

        self.assertEqual(report["statistics"]["total_rows"], 1)
        self.assertEqual(report["statistics"]["completed_rows"], 0)
        self.assertEqual(report["rows"][0]["row_id"], row.id)
        self.assertIsNone(report["rows"][0]["decision"]["status"])

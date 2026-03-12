"""价格审核任务测试。"""

from __future__ import annotations

from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from price_audit.agent.row_agent import RowAuditOutput
from price_audit.models import (
    GovernmentPriceBatch,
    PriceAuditRowDecision,
    PriceAuditSubmission,
)
from price_audit.services.submission_parser import populate_submission_rows
from price_audit.tasks import (
    _aggregate_non_leaf_rows,
    _update_submission_totals,
    dispatch_process_price_audit_submission,
    process_price_audit_submission,
)
from price_audit.tests.helpers import (
    TempMediaRootMixin,
    create_row_decision,
    create_submission_with_workbook,
)


User = get_user_model()


class PriceAuditTaskTests(TempMediaRootMixin, TestCase):
    """验证送审单异步审核任务。"""

    def setUp(self):
        self.user = User.objects.create_user(username="task", password="Testpass123")
        self.batch = GovernmentPriceBatch.objects.create(
            region_name="天津",
            year=2026,
            is_active=True,
            vector_status=GovernmentPriceBatch.VectorStatus.ACTIVE,
        )

    def _create_submission(self) -> PriceAuditSubmission:
        return create_submission_with_workbook(
            created_by=self.user,
            price_batch=self.batch,
        )

    def _mock_agent(self, row):
        if row.fee_type == "场地租":
            return RowAuditOutput(
                reviewed_unit="平米",
                reviewed_unit_price="9",
                reviewed_quantity="100",
                reviewed_days="3",
                reviewed_amount="2700",
                reason="场地租价格合理。",
                notes=["与送审一致"],
            ), {"candidates": [], "notes": ["与送审一致"]}
        if row.fee_type == "特装展台-地台制作":
            return RowAuditOutput(
                reviewed_unit="㎡",
                reviewed_unit_price="70",
                reviewed_quantity="10",
                reviewed_amount="700",
                reason="参考标准价后下调单价。",
                notes=["采用标准价 70 元/㎡"],
            ), {"candidates": [{"item_id": 1}], "notes": ["采用标准价 70 元/㎡"]}
        if row.fee_type == "特装展台-地台包边":
            return RowAuditOutput(
                reviewed_unit="m",
                reviewed_unit_price="20",
                reviewed_quantity="10",
                reviewed_amount="200",
                reason="维持原申报。",
                notes=[],
            ), {"candidates": [], "notes": []}
        return RowAuditOutput(
            reviewed_amount="400",
            reason="按实际用电需求下调。",
            notes=["调整电费"],
        ), {"candidates": [], "notes": ["调整电费"]}

    def _create_populated_submission(self) -> PriceAuditSubmission:
        submission = self._create_submission()
        populate_submission_rows(submission)
        return submission

    def _create_completed_leaf_decisions(self, submission: PriceAuditSubmission) -> None:
        create_row_decision(submission.rows.get(sequence_no="1"))
        create_row_decision(
            submission.rows.get(sequence_no="2.1"),
            result_type=PriceAuditRowDecision.ResultType.ADJUSTED,
            reviewed_unit="㎡",
            reviewed_unit_price="70.0000",
            reviewed_quantity="10.0000",
            reviewed_days=None,
            reviewed_amount="700.0000",
            reduction_amount="300.0000",
            reason="参考标准价后下调单价。",
        )
        create_row_decision(
            submission.rows.get(sequence_no="2.2"),
            reviewed_unit="m",
            reviewed_unit_price="20.0000",
            reviewed_quantity="10.0000",
            reviewed_days=None,
            reviewed_amount="200.0000",
            reduction_amount="0.0000",
        )
        create_row_decision(
            submission.rows.get(sequence_no="3"),
            result_type=PriceAuditRowDecision.ResultType.ADJUSTED,
            reviewed_unit="",
            reviewed_unit_price=None,
            reviewed_quantity=None,
            reviewed_days=None,
            reviewed_amount="400.0000",
            reduction_amount="100.0000",
            reason="按实际用电需求下调。",
        )

    @patch("price_audit.tasks.process_price_audit_submission.delay")
    def test_dispatch_process_price_audit_submission_returns_task_id(self, delay_mock):
        """派发 helper 应返回 Celery 任务 ID。"""

        delay_mock.return_value = Mock(id="task-123")

        task_id = dispatch_process_price_audit_submission(11)

        self.assertEqual(task_id, "task-123")
        delay_mock.assert_called_once_with(11)

    @patch("price_audit.services.row_review_service.review_row_with_agent")
    def test_process_submission_completes_and_exports_excel(self, review_mock):
        """任务成功时应生成逐行结果、汇总结果和审核表文件。"""

        submission = self._create_submission()
        review_mock.side_effect = self._mock_agent

        process_price_audit_submission.apply(args=[submission.id], throw=True)

        submission.refresh_from_db()
        self.assertEqual(submission.status, "completed")
        self.assertEqual(submission.current_step, "completed")
        self.assertEqual(submission.progress_percent, 100)
        self.assertEqual(submission.total_rows, 4)
        self.assertEqual(submission.processed_rows, 4)
        self.assertEqual(submission.failed_rows, 0)
        self.assertEqual(submission.current_message, "审核完成，审核表已生成。")
        self.assertEqual(str(submission.submitted_total_amount), "4500.0000")
        self.assertEqual(str(submission.reviewed_total_amount), "4100.0000")
        self.assertEqual(str(submission.reduction_total_amount), "400.0000")
        self.assertTrue(bool(submission.audited_excel_file))
        self.assertEqual(submission.report_json["statistics"]["failed_rows"], 0)
        tax_decision = submission.rows.get(fee_type="税费").decision
        self.assertEqual(tax_decision.result_type, "skipped")
        self.assertEqual(str(tax_decision.reviewed_amount), "100.0000")
        group_decision = submission.rows.get(sequence_no="2").decision
        self.assertEqual(group_decision.result_type, "aggregated")
        self.assertEqual(str(group_decision.reviewed_amount), "900.0000")
        total_decision = submission.rows.get(fee_type="合计").decision
        self.assertEqual(str(total_decision.reviewed_amount), "4100.0000")

    @patch("price_audit.tasks.populate_submission_rows")
    def test_process_submission_marks_failed_when_parsing_raises(self, populate_mock):
        """解析失败时应终止任务并写入 report_json 错误。"""

        submission = self._create_submission()
        populate_mock.side_effect = ValueError("价格审核模板格式错误")

        process_price_audit_submission.apply(args=[submission.id], throw=True)

        submission.refresh_from_db()
        self.assertEqual(submission.status, "failed")
        self.assertEqual(submission.current_step, "failed")
        self.assertEqual(submission.progress_percent, 100)
        self.assertEqual(submission.current_message, "审核失败。")
        self.assertEqual(submission.error_message, "价格审核模板格式错误")
        self.assertEqual(submission.report_json["error"], "价格审核模板格式错误")
        self.assertFalse(bool(submission.audited_excel_file))

    @patch("price_audit.services.row_review_service.review_row_with_agent")
    def test_process_submission_marks_failed_when_leaf_row_fails_but_continues_other_rows(
        self,
        review_mock,
    ):
        """单个叶子行失败后，其余叶子行仍继续处理。"""

        submission = self._create_submission()

        def _side_effect(row):
            if row.fee_type == "特装展台-地台制作":
                raise RuntimeError("AI 审核失败")
            return self._mock_agent(row)

        review_mock.side_effect = _side_effect
        process_price_audit_submission.apply(args=[submission.id], throw=True)

        submission.refresh_from_db()
        self.assertEqual(submission.status, "failed")
        self.assertEqual(submission.current_step, "failed")
        self.assertEqual(submission.progress_percent, 100)
        self.assertEqual(submission.total_rows, 4)
        self.assertEqual(submission.processed_rows, 4)
        self.assertEqual(submission.failed_rows, 4)
        self.assertEqual(submission.current_message, "审核完成，共 4 行失败。")
        self.assertFalse(bool(submission.audited_excel_file))
        failed_decision = submission.rows.get(fee_type="特装展台-地台制作").decision
        self.assertEqual(failed_decision.status, "failed")
        self.assertIn("AI 审核失败", failed_decision.error_message)
        electric_decision = submission.rows.get(fee_type="电费").decision
        self.assertEqual(electric_decision.status, "completed")
        total_decision = submission.rows.get(fee_type="合计").decision
        self.assertEqual(total_decision.status, "failed")
        self.assertEqual(submission.report_json["statistics"]["failed_rows"], 4)

    def test_aggregate_non_leaf_rows_builds_group_subtotal_tax_and_total(self):
        """程序汇总应生成 group、小计、税费、合计结果。"""

        submission = self._create_populated_submission()
        self._create_completed_leaf_decisions(submission)

        _aggregate_non_leaf_rows(submission)

        group_decision = submission.rows.get(sequence_no="2").decision
        subtotal_decision = submission.rows.get(fee_type="小计").decision
        tax_decision = submission.rows.get(fee_type="税费").decision
        total_decision = submission.rows.get(fee_type="合计").decision

        self.assertEqual(group_decision.status, "completed")
        self.assertEqual(group_decision.result_type, "aggregated")
        self.assertEqual(str(group_decision.reviewed_amount), "900.0000")
        self.assertEqual(str(subtotal_decision.reviewed_amount), "4000.0000")
        self.assertEqual(tax_decision.result_type, "skipped")
        self.assertEqual(str(tax_decision.reviewed_amount), "100.0000")
        self.assertEqual(str(total_decision.reviewed_amount), "4100.0000")

    def test_aggregate_non_leaf_rows_marks_group_failed_when_child_failed(self):
        """父项有失败子项时，group 结果应失败。"""

        submission = self._create_populated_submission()
        self._create_completed_leaf_decisions(submission)
        child_decision = submission.rows.get(sequence_no="2.1").decision
        child_decision.status = PriceAuditRowDecision.Status.FAILED
        child_decision.error_message = "子项审核失败"
        child_decision.save(update_fields=["status", "error_message", "updated_at"])

        _aggregate_non_leaf_rows(submission)

        group_decision = submission.rows.get(sequence_no="2").decision
        self.assertEqual(group_decision.status, "failed")
        self.assertIn("父项存在未完成或失败的子项", group_decision.error_message)

    def test_aggregate_non_leaf_rows_marks_subtotal_and_total_failed_when_dependency_missing(self):
        """顶层费用项缺少结果时，小计和合计都应失败。"""

        submission = self._create_populated_submission()
        create_row_decision(submission.rows.get(sequence_no="1"))
        create_row_decision(
            submission.rows.get(sequence_no="2.1"),
            result_type=PriceAuditRowDecision.ResultType.ADJUSTED,
            reviewed_amount="700.0000",
            reduction_amount="300.0000",
        )
        create_row_decision(submission.rows.get(sequence_no="2.2"), reviewed_amount="200.0000")

        _aggregate_non_leaf_rows(submission)

        subtotal_decision = submission.rows.get(fee_type="小计").decision
        total_decision = submission.rows.get(fee_type="合计").decision
        self.assertEqual(subtotal_decision.status, "failed")
        self.assertIn("无法计算小计", subtotal_decision.error_message)
        self.assertEqual(total_decision.status, "failed")
        self.assertIn("无法计算合计", total_decision.error_message)

    def test_update_submission_totals_reads_total_row_and_decision(self):
        """总金额应取自合计行及其审核结果。"""

        submission = self._create_populated_submission()
        self._create_completed_leaf_decisions(submission)
        _aggregate_non_leaf_rows(submission)

        refreshed = PriceAuditSubmission.objects.prefetch_related("rows__decision").get(id=submission.id)
        _update_submission_totals(refreshed)

        self.assertEqual(str(refreshed.submitted_total_amount), "4500.0000")
        self.assertEqual(str(refreshed.reviewed_total_amount), "4100.0000")
        self.assertEqual(str(refreshed.reduction_total_amount), "400.0000")

    def test_update_submission_totals_returns_none_when_total_row_missing(self):
        """缺少合计行时，总金额字段应保持为空。"""

        submission = self._create_submission()
        _update_submission_totals(submission)

        self.assertIsNone(submission.submitted_total_amount)
        self.assertIsNone(submission.reviewed_total_amount)
        self.assertIsNone(submission.reduction_total_amount)

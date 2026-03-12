"""价格送审服务测试。"""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from price_audit.models import GovernmentPriceBatch, PriceAuditSubmission
from price_audit.services.submission_service import (
    create_submission_from_upload,
    get_default_price_batch,
)
from price_audit.tests.helpers import TempMediaRootMixin, build_price_audit_submission_workbook


User = get_user_model()


class SubmissionServiceTests(TempMediaRootMixin, TestCase):
    """验证送审单创建服务。"""

    def setUp(self):
        self.user = User.objects.create_user(username="submission-service", password="Testpass123")

    def test_get_default_price_batch_picks_latest_active_vectorized_batch(self):
        """应选择最新年份且可用于审核的批次。"""

        GovernmentPriceBatch.objects.create(
            region_name="天津",
            year=2025,
            is_active=True,
            vector_status=GovernmentPriceBatch.VectorStatus.ACTIVE,
        )
        expected = GovernmentPriceBatch.objects.create(
            region_name="天津",
            year=2026,
            is_active=True,
            vector_status=GovernmentPriceBatch.VectorStatus.ACTIVE,
        )
        GovernmentPriceBatch.objects.create(
            region_name="天津",
            year=2027,
            is_active=True,
            vector_status=GovernmentPriceBatch.VectorStatus.PROCESSING,
        )

        self.assertEqual(get_default_price_batch(), expected)

    def test_get_default_price_batch_raises_when_no_active_vectorized_batch(self):
        """没有可用标准价批次时应报错。"""

        GovernmentPriceBatch.objects.create(
            region_name="天津",
            year=2026,
            is_active=True,
            vector_status=GovernmentPriceBatch.VectorStatus.PROCESSING,
        )

        with self.assertRaisesRegex(ValueError, "暂无可用的政府标准价批次"):
            get_default_price_batch()

    @patch("price_audit.services.submission_service.dispatch_process_price_audit_submission")
    def test_create_submission_from_upload_creates_submission_and_dispatches_on_commit(
        self,
        dispatch_mock,
    ):
        """成功上传后应保存 submission 并在事务提交后派发任务。"""

        batch = GovernmentPriceBatch.objects.create(
            region_name="天津",
            year=2026,
            is_active=True,
            vector_status=GovernmentPriceBatch.VectorStatus.ACTIVE,
        )
        uploaded_file = build_price_audit_submission_workbook(filename="示例项目.xlsx")

        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            submission = create_submission_from_upload(uploaded_file, created_by=self.user)

        self.assertEqual(submission.created_by, self.user)
        self.assertEqual(submission.price_batch, batch)
        self.assertEqual(submission.project_name, "示例项目")
        self.assertEqual(submission.status, PriceAuditSubmission.Status.PENDING)
        self.assertEqual(submission.current_step, PriceAuditSubmission.Step.QUEUED)
        self.assertEqual(submission.progress_percent, 0)
        self.assertEqual(submission.total_rows, 0)
        self.assertEqual(submission.processed_rows, 0)
        self.assertEqual(submission.failed_rows, 0)
        self.assertIn("等待开始审核", submission.current_message)
        self.assertTrue(bool(submission.source_file))
        self.assertEqual(len(callbacks), 1)
        dispatch_mock.assert_not_called()

        callbacks[0]()
        dispatch_mock.assert_called_once_with(submission.id)

    def test_create_submission_from_upload_rejects_non_xlsx(self):
        """上传扩展名不符合要求时应报错。"""

        with self.assertRaisesRegex(ValueError, "仅支持上传 .xlsx 格式文件"):
            create_submission_from_upload(
                build_price_audit_submission_workbook(filename="bad.csv"),
                created_by=self.user,
            )

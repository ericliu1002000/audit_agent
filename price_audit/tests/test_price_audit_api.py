"""价格审核 API 测试。"""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase
from django.urls import reverse

from price_audit.constants import EXHIBITION_CENTER_NEC, PROJECT_NATURE_PERMANENT
from price_audit.models import GovernmentPriceBatch, PriceAuditSubmission
from price_audit.tests.helpers import (
    TempMediaRootMixin,
    build_price_audit_submission_workbook,
    create_row_decision,
    create_submission_row,
    create_submission_with_workbook,
)


User = get_user_model()


class PriceAuditApiTests(TempMediaRootMixin, TestCase):
    """验证价格审核 API 行为。"""

    def setUp(self):
        self.user = User.objects.create_user(username="apiuser", password="Testpass123")
        self.other_user = User.objects.create_user(username="other-apiuser", password="Testpass123")
        self.client.force_login(self.user)
        self.batch = GovernmentPriceBatch.objects.create(
            region_name="天津",
            year=2026,
            is_active=True,
            vector_status=GovernmentPriceBatch.VectorStatus.ACTIVE,
        )
        self.create_url = reverse("api:v1:price-audit-submission-create")

    def _create_completed_submission(self, *, created_by=None) -> PriceAuditSubmission:
        submission = create_submission_with_workbook(
            created_by=created_by or self.user,
            price_batch=self.batch,
            status="completed",
        )
        submission.submitted_total_amount = "4500.0000"
        submission.reviewed_total_amount = "4100.0000"
        submission.reduction_total_amount = "400.0000"
        submission.report_json = {"status": "completed"}
        submission.current_step = "completed"
        submission.progress_percent = 100
        submission.total_rows = 2
        submission.processed_rows = 2
        submission.failed_rows = 0
        submission.current_message = "审核完成，审核表已生成。"
        submission.save(
            update_fields=[
                "current_step",
                "progress_percent",
                "total_rows",
                "processed_rows",
                "failed_rows",
                "current_message",
                "submitted_total_amount",
                "reviewed_total_amount",
                "reduction_total_amount",
                "report_json",
                "updated_at",
            ]
        )
        row1 = create_submission_row(submission, excel_row_no=3, sequence_no="1", fee_type="场地租")
        row2 = create_submission_row(
            submission,
            excel_row_no=4,
            sequence_no="2",
            fee_type="电费",
            submitted_unit="",
            submitted_unit_price=None,
            submitted_quantity=None,
            submitted_days=None,
            submitted_amount="500.0000",
        )
        create_row_decision(row1)
        create_row_decision(
            row2,
            result_type="adjusted",
            reviewed_unit="",
            reviewed_unit_price=None,
            reviewed_quantity=None,
            reviewed_days=None,
            reviewed_amount="400.0000",
            reduction_amount="100.0000",
            reason="按实际用电需求下调。",
        )
        return submission

    @patch("price_audit.services.submission_service.dispatch_process_price_audit_submission")
    def test_create_submission_uploads_and_dispatches_task(self, dispatch_mock):
        """上传接口应创建 submission 并提交异步任务。"""

        dispatch_mock.return_value = "task-id"
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                self.create_url,
                data={
                    "file": build_price_audit_submission_workbook(),
                    "exhibition_center_id": EXHIBITION_CENTER_NEC,
                    "project_nature": PROJECT_NATURE_PERMANENT,
                },
            )

        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["status"], "pending")
        self.assertEqual(payload["data"]["current_step"], "queued")
        self.assertEqual(payload["data"]["progress_percent"], 0)
        self.assertEqual(payload["data"]["total_rows"], 0)
        self.assertEqual(payload["data"]["processed_rows"], 0)
        self.assertEqual(payload["data"]["failed_rows"], 0)
        self.assertEqual(payload["data"]["exhibition_center_id"], EXHIBITION_CENTER_NEC)
        self.assertEqual(payload["data"]["exhibition_center_name"], "天津国家会展中心")
        self.assertEqual(payload["data"]["project_nature"], PROJECT_NATURE_PERMANENT)
        self.assertEqual(payload["data"]["project_nature_name"], "常设陈列")
        self.assertIn("/api/v1/price-audit/submissions/", payload["data"]["detail_url"])
        self.assertIn("/rows/", payload["data"]["rows_url"])
        submission = PriceAuditSubmission.objects.get()
        self.assertEqual(submission.created_by, self.user)
        self.assertEqual(submission.exhibition_center_id, EXHIBITION_CENTER_NEC)
        self.assertEqual(submission.project_nature, PROJECT_NATURE_PERMANENT)
        dispatch_mock.assert_called_once_with(submission.id)

    def test_create_submission_returns_validation_error_when_file_is_missing(self):
        """缺少文件字段时应返回统一 validation error。"""

        response = self.client.post(self.create_url, data={})

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["success"])
        self.assertEqual(payload["error"]["code"], "validation_error")
        self.assertIn("file", payload["error"]["fields"])
        self.assertIn("exhibition_center_id", payload["error"]["fields"])
        self.assertIn("project_nature", payload["error"]["fields"])

    def test_create_submission_rejects_non_xlsx(self):
        """上传非 xlsx 文件应返回校验错误。"""

        response = self.client.post(
            self.create_url,
            data={
                "file": ContentFile(b"bad", name="bad.csv"),
                "exhibition_center_id": EXHIBITION_CENTER_NEC,
                "project_nature": PROJECT_NATURE_PERMANENT,
            },
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["success"])
        self.assertEqual(payload["error"]["code"], "validation_error")

    def test_create_submission_rejects_invalid_scene_values(self):
        """非法会展中心或项目性质应返回校验错误。"""

        response = self.client.post(
            self.create_url,
            data={
                "file": build_price_audit_submission_workbook(),
                "exhibition_center_id": 99,
                "project_nature": 88,
            },
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["success"])
        self.assertEqual(payload["error"]["code"], "validation_error")
        self.assertIn("exhibition_center_id", payload["error"]["fields"])
        self.assertIn("project_nature", payload["error"]["fields"])

    @patch("api.v1.views.price_audit.create_submission_from_upload")
    def test_create_submission_returns_service_validation_error(self, create_mock):
        """业务服务返回 ValueError 时应转成统一错误响应。"""

        create_mock.side_effect = ValueError("暂无可用的政府标准价批次，请先导入并完成向量化。")

        response = self.client.post(
            self.create_url,
            data={
                "file": build_price_audit_submission_workbook(),
                "exhibition_center_id": EXHIBITION_CENTER_NEC,
                "project_nature": PROJECT_NATURE_PERMANENT,
            },
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["success"])
        self.assertEqual(payload["error"]["code"], "validation_error")
        self.assertIn("暂无可用的政府标准价批次", payload["error"]["message"])

    def test_detail_endpoint_returns_submission_data(self):
        """详情接口应返回 submission 数据和下载地址。"""

        submission = self._create_completed_submission()
        submission.audited_excel_file.save(
            "submission_audited.xlsx",
            ContentFile(build_price_audit_submission_workbook().read()),
            save=True,
        )
        detail_url = reverse(
            "api:v1:price-audit-submission-detail",
            kwargs={"submission_id": submission.id},
        )

        response = self.client.get(detail_url)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["id"], submission.id)
        self.assertEqual(payload["data"]["current_step"], "completed")
        self.assertEqual(payload["data"]["progress_percent"], 100)
        self.assertEqual(payload["data"]["processed_rows"], 2)
        self.assertEqual(payload["data"]["failed_rows"], 0)
        self.assertEqual(payload["data"]["exhibition_center_id"], submission.exhibition_center_id)
        self.assertEqual(payload["data"]["exhibition_center_name"], "天津梅江会展中心")
        self.assertEqual(payload["data"]["project_nature"], submission.project_nature)
        self.assertEqual(payload["data"]["project_nature_name"], "临时展会")
        self.assertIn("/api/v1/price-audit/submissions/", payload["data"]["detail_url"])
        self.assertIn("/rows/", payload["data"]["rows_url"])
        self.assertIn("/api/v1/price-audit/submissions/", payload["data"]["audited_excel_download_url"])

    def test_detail_endpoint_returns_404_for_missing_or_other_user_submission(self):
        """不是当前用户的 submission 不应可见。"""

        submission = self._create_completed_submission(created_by=self.other_user)
        detail_url = reverse(
            "api:v1:price-audit-submission-detail",
            kwargs={"submission_id": submission.id},
        )

        response = self.client.get(detail_url)

        self.assertEqual(response.status_code, 404)
        payload = response.json()
        self.assertFalse(payload["success"])
        self.assertEqual(payload["error"]["code"], "not_found")

    def test_rows_endpoint_returns_paginated_items(self):
        """行列表接口应返回统一分页结构。"""

        submission = self._create_completed_submission()
        rows_url = reverse(
            "api:v1:price-audit-submission-rows",
            kwargs={"submission_id": submission.id},
        )

        response = self.client.get(rows_url, data={"page_size": 1})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(len(payload["data"]["items"]), 1)
        self.assertEqual(payload["meta"]["pagination"]["page_size"], 1)
        self.assertEqual(payload["meta"]["pagination"]["total"], 2)
        self.assertIn("decision", payload["data"]["items"][0])

    def test_rows_endpoint_returns_empty_items_for_submission_without_rows(self):
        """没有送审行时也应返回空分页结果。"""

        submission = create_submission_with_workbook(created_by=self.user, price_batch=self.batch)
        rows_url = reverse(
            "api:v1:price-audit-submission-rows",
            kwargs={"submission_id": submission.id},
        )

        response = self.client.get(rows_url)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["data"]["items"], [])
        self.assertEqual(payload["meta"]["pagination"]["total"], 0)

    def test_rows_endpoint_returns_404_for_missing_submission(self):
        """不存在的 submission 行列表应返回 404。"""

        rows_url = reverse(
            "api:v1:price-audit-submission-rows",
            kwargs={"submission_id": 999999},
        )

        response = self.client.get(rows_url)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "not_found")

    def test_download_endpoint_returns_file_response(self):
        """审核表已生成时应能下载。"""

        submission = self._create_completed_submission()
        source = build_price_audit_submission_workbook()
        submission.audited_excel_file.save(
            "submission_audited.xlsx",
            ContentFile(source.read()),
            save=True,
        )
        download_url = reverse(
            "api:v1:price-audit-submission-download-audited-excel",
            kwargs={"submission_id": submission.id},
        )

        response = self.client.get(download_url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment;", response["Content-Disposition"])
        self.assertIn("submission_audited.xlsx", response["Content-Disposition"])

    def test_download_endpoint_returns_404_when_file_not_ready(self):
        """审核表未生成时应返回 not_found。"""

        submission = self._create_completed_submission()
        download_url = reverse(
            "api:v1:price-audit-submission-download-audited-excel",
            kwargs={"submission_id": submission.id},
        )

        response = self.client.get(download_url)

        self.assertEqual(response.status_code, 404)
        payload = response.json()
        self.assertFalse(payload["success"])
        self.assertEqual(payload["error"]["code"], "not_found")
        self.assertIn("尚未生成", payload["error"]["message"])

    def test_download_endpoint_returns_404_for_other_user_submission(self):
        """不是当前用户的下载请求应返回 404。"""

        submission = self._create_completed_submission(created_by=self.other_user)
        download_url = reverse(
            "api:v1:price-audit-submission-download-audited-excel",
            kwargs={"submission_id": submission.id},
        )

        response = self.client.get(download_url)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "not_found")

    def test_all_price_audit_endpoints_require_authentication(self):
        """四个价格审核接口都应要求登录。"""

        submission = self._create_completed_submission()
        self.client.logout()

        endpoints = [
            (
                "post",
                self.create_url,
                {
                    "file": build_price_audit_submission_workbook(),
                    "exhibition_center_id": EXHIBITION_CENTER_NEC,
                    "project_nature": PROJECT_NATURE_PERMANENT,
                },
            ),
            (
                "get",
                reverse("api:v1:price-audit-submission-detail", kwargs={"submission_id": submission.id}),
                None,
            ),
            (
                "get",
                reverse("api:v1:price-audit-submission-rows", kwargs={"submission_id": submission.id}),
                None,
            ),
            (
                "get",
                reverse(
                    "api:v1:price-audit-submission-download-audited-excel",
                    kwargs={"submission_id": submission.id},
                ),
                None,
            ),
        ]

        for method, url, data in endpoints:
            response = getattr(self.client, method)(url, data=data)
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.json()["error"]["code"], "authentication_required")

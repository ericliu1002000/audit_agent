"""价格审核 admin 交互测试。"""

from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from openpyxl import Workbook

from price_audit.models import GovernmentPriceBatch


User = get_user_model()


def build_workbook_file() -> SimpleUploadedFile:
    """构造一份最小可导入的政府标准价 Excel。"""

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(
        [
            "材料名称",
            "规格型号",
            "单位",
            "中准价格",
            "区间最低价",
            "区间最高价",
            "说明",
            "是否含税",
        ]
    )
    sheet.append(
        [
            "普通硅酸盐水泥",
            "42.5级 散装",
            "t",
            "437.53",
            "351.55",
            "550.00",
            "",
            "是",
        ]
    )
    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return SimpleUploadedFile(
        "government_price.xlsx",
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


class GovernmentPriceAdminTests(TestCase):
    """验证后台模板下载和上传入口。"""

    def setUp(self):
        self.user = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="Adminpass123",
        )
        self.client.force_login(self.user)
        self.template_url = reverse(
            "admin:price_audit_governmentpricebatch_download_template"
        )
        self.import_url = reverse("admin:price_audit_governmentpricebatch_import_prices")

    def test_download_template(self):
        """模板下载接口应返回 xlsx 文件。"""

        response = self.client.get(self.template_url)

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            response["Content-Type"],
        )
        self.assertIn("attachment;", response["Content-Disposition"])

    def test_import_view_creates_batch(self):
        """后台上传 Excel 后应创建新批次。"""

        with patch(
            "price_audit.services.government_price_service.dispatch_vectorize_government_price_batch"
        ) as dispatch_mock:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    self.import_url,
                    data={
                        "excel_file": build_workbook_file(),
                        "region_name": "天津",
                        "year": 2026,
                        "default_tax_included": "on",
                        "remark": "测试导入",
                    },
                    follow=True,
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(GovernmentPriceBatch.objects.count(), 1)
        batch = GovernmentPriceBatch.objects.first()
        self.assertEqual(batch.region_name, "天津")
        self.assertEqual(batch.year, 2026)
        self.assertEqual(batch.total_rows, 1)
        self.assertEqual(batch.vector_status, GovernmentPriceBatch.VectorStatus.PENDING)
        dispatch_mock.assert_called_once_with(batch.id, [])

    def test_import_view_rejects_non_xlsx_file(self):
        """上传非 xlsx 文件时应停留在表单页并展示错误。"""

        invalid_file = SimpleUploadedFile("invalid.csv", b"a,b,c\n", content_type="text/csv")

        response = self.client.post(
            self.import_url,
            data={
                "excel_file": invalid_file,
                "region_name": "天津",
                "year": 2026,
                "default_tax_included": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "仅支持上传 .xlsx 格式文件")
        self.assertEqual(GovernmentPriceBatch.objects.count(), 0)

    def test_import_view_shows_value_error_message(self):
        """service 抛出 ValueError 时应回到列表页并展示业务错误。"""

        with patch(
            "price_audit.admin.government_price_service.import_excel",
            side_effect=ValueError("业务校验失败"),
        ):
            response = self.client.post(
                self.import_url,
                data={
                    "excel_file": build_workbook_file(),
                    "region_name": "天津",
                    "year": 2026,
                    "default_tax_included": "on",
                },
                follow=True,
            )

        messages = [message.message for message in get_messages(response.wsgi_request)]
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any("导入失败：业务校验失败" in message for message in messages))
        self.assertEqual(GovernmentPriceBatch.objects.count(), 0)

    def test_import_view_shows_generic_error_message(self):
        """service 抛出非业务异常时也应展示错误提示。"""

        with patch(
            "price_audit.admin.government_price_service.import_excel",
            side_effect=RuntimeError("系统异常"),
        ):
            response = self.client.post(
                self.import_url,
                data={
                    "excel_file": build_workbook_file(),
                    "region_name": "天津",
                    "year": 2026,
                    "default_tax_included": "on",
                },
                follow=True,
            )

        messages = [message.message for message in get_messages(response.wsgi_request)]
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any("导入失败：系统异常" in message for message in messages))
        self.assertEqual(GovernmentPriceBatch.objects.count(), 0)

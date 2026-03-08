"""价格审核 admin 交互测试。"""

from io import BytesIO

from django.contrib.auth import get_user_model
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

"""价格审核 service 测试。"""

from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from openpyxl import Workbook

from price_audit.models import GovernmentPriceBatch, GovernmentPriceItem
from price_audit.services import government_price_service


User = get_user_model()


def build_template_like_workbook(
    *,
    include_tax_column: bool = True,
    combined_range: bool = False,
    include_range_columns: bool = True,
) -> SimpleUploadedFile:
    """构造一份用于 service 测试的 Excel 文件。"""

    workbook = Workbook()
    sheet = workbook.active
    headers = ["材料名称", "规格型号", "单位", "中准价格"]
    if include_range_columns and combined_range:
        headers.append("区间价格")
    elif include_range_columns:
        headers.extend(["区间最低价", "区间最高价"])
    headers.append("说明")
    if include_tax_column:
        headers.append("是否含税")
    sheet.append(headers)

    row = ["矿渣硅酸盐水泥", "32.5级 散装", "t", "379.42"]
    if include_range_columns and combined_range:
        row.append("285.80-515.00")
    elif include_range_columns:
        row.extend(["285.80", "515.00"])
    row.append("测试数据")
    if include_tax_column:
        row.append("")
    sheet.append(row)

    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return SimpleUploadedFile(
        "government_prices.xlsx",
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


class GovernmentPriceServiceTests(TestCase):
    """验证政府标准价 service 的解析与覆盖导入逻辑。"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="tester",
            password="Testpass123",
        )

    def test_parse_excel_defaults_tax_included(self):
        """缺少含税列时应默认按含税处理。"""

        rows = government_price_service.parse_excel(
            build_template_like_workbook(include_tax_column=False),
            default_tax_included=True,
        )

        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0].is_tax_included)
        self.assertEqual(str(rows[0].price_min), "285.80")
        self.assertEqual(str(rows[0].price_max), "515.00")

    def test_parse_excel_supports_combined_range_column(self):
        """兼容单列区间价格格式。"""

        rows = government_price_service.parse_excel(
            build_template_like_workbook(combined_range=True),
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(str(rows[0].price_min), "285.80")
        self.assertEqual(str(rows[0].price_max), "515.00")

    def test_parse_excel_allows_missing_range_columns(self):
        """区间价格列整体缺失时也应允许导入。"""

        rows = government_price_service.parse_excel(
            build_template_like_workbook(include_range_columns=False),
        )

        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0].price_min)
        self.assertIsNone(rows[0].price_max)

    def test_import_excel_replaces_active_batch(self):
        """同地区同年份再次上传时，应使旧批次失效并创建新批次。"""

        first_result = government_price_service.import_excel(
            build_template_like_workbook(),
            region_name="天津",
            year=2026,
            uploaded_by=self.user,
            remark="第一次导入",
        )
        second_result = government_price_service.import_excel(
            build_template_like_workbook(),
            region_name="天津",
            year=2026,
            uploaded_by=self.user,
            remark="第二次导入",
        )

        self.assertEqual(GovernmentPriceBatch.objects.count(), 2)
        self.assertEqual(GovernmentPriceItem.objects.count(), 2)
        self.assertFalse(GovernmentPriceBatch.objects.get(id=first_result.batch.id).is_active)
        self.assertTrue(GovernmentPriceBatch.objects.get(id=second_result.batch.id).is_active)
        self.assertEqual(second_result.replaced_batches, 1)

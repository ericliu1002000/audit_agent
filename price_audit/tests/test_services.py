"""价格审核 service 测试。"""

from io import BytesIO
from unittest.mock import patch

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
    rows: list[list[str]] | None = None,
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

    actual_rows = rows or [["矿渣硅酸盐水泥", "32.5级 散装", "t", "379.42", "测试数据", ""]]
    for source_row in actual_rows:
        material_name, spec_model, unit, benchmark_price, description, tax_flag = source_row
        row = [material_name, spec_model, unit, benchmark_price]
        if include_range_columns and combined_range:
            row.append("285.80-515.00")
        elif include_range_columns:
            row.extend(["285.80", "515.00"])
        row.append(description)
        if include_tax_column:
            row.append(tax_flag)
        sheet.append(row)

    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return SimpleUploadedFile(
        "government_prices.xlsx",
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def build_custom_workbook(
    headers: list[str],
    rows: list[list[object]],
    *,
    filename: str = "government_prices.xlsx",
) -> SimpleUploadedFile:
    """按原始表头和行值构造测试 Excel。"""

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(headers)
    for row in rows:
        sheet.append(row)

    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return SimpleUploadedFile(
        filename,
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

    def test_parse_excel_can_default_tax_to_false(self):
        """缺少含税列时，也应支持默认按不含税处理。"""

        rows = government_price_service.parse_excel(
            build_template_like_workbook(include_tax_column=False),
            default_tax_included=False,
        )

        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0].is_tax_included)

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

    def test_parse_excel_raises_when_header_invalid(self):
        """表头不符合模板要求时应报错。"""

        workbook = build_custom_workbook(
            ["错误列1", "错误列2"],
            [["a", "b"]],
        )

        with self.assertRaisesRegex(ValueError, "表头不符合模板要求"):
            government_price_service.parse_excel(workbook)

    def test_parse_excel_raises_when_material_name_missing(self):
        """材料名称为空时应报错。"""

        workbook = build_custom_workbook(
            ["材料名称", "规格型号", "单位", "中准价格", "说明"],
            [["", "32.5级 散装", "t", "379.42", "说明"]],
        )

        with self.assertRaisesRegex(ValueError, "材料名称为空"):
            government_price_service.parse_excel(workbook)

    def test_parse_excel_raises_when_benchmark_price_invalid(self):
        """中准价格无效时应报错。"""

        workbook = build_custom_workbook(
            ["材料名称", "规格型号", "单位", "中准价格", "说明"],
            [["矿渣硅酸盐水泥", "32.5级 散装", "t", "abc", "说明"]],
        )

        with self.assertRaisesRegex(ValueError, "中准价格无效"):
            government_price_service.parse_excel(workbook)

    def test_parse_excel_raises_when_price_min_greater_than_max(self):
        """区间下限大于上限时应报错。"""

        workbook = build_custom_workbook(
            ["材料名称", "规格型号", "单位", "中准价格", "区间最低价", "区间最高价", "说明"],
            [["矿渣硅酸盐水泥", "32.5级 散装", "t", "379.42", "600", "500", "说明"]],
        )

        with self.assertRaisesRegex(ValueError, "区间最低价不能大于区间最高价"):
            government_price_service.parse_excel(workbook)

    def test_parse_excel_raises_when_no_valid_rows_found(self):
        """数据区全为空时应报错。"""

        workbook = build_custom_workbook(
            ["材料名称", "规格型号", "单位", "中准价格", "说明"],
            [["", "", "", "", ""]],
        )

        with self.assertRaisesRegex(ValueError, "未解析到有效政府标准价数据"):
            government_price_service.parse_excel(workbook)

    def test_import_excel_raises_when_region_is_blank(self):
        """地区为空时应报错。"""

        with self.assertRaisesRegex(ValueError, "地区不能为空"):
            government_price_service.import_excel(
                build_template_like_workbook(),
                region_name="   ",
                year=2026,
                uploaded_by=self.user,
            )

    def test_import_excel_raises_when_year_missing(self):
        """年份为空时应报错。"""

        with self.assertRaisesRegex(ValueError, "年份不能为空"):
            government_price_service.import_excel(
                build_template_like_workbook(),
                region_name="天津",
                year=0,
                uploaded_by=self.user,
            )

    def test_import_excel_updates_existing_batch_in_place(self):
        """同地区同年份再次上传时，应在原批次上做增量更新。"""

        with patch(
            "price_audit.services.government_price_service.dispatch_vectorize_government_price_batch"
        ) as dispatch_mock:
            with self.captureOnCommitCallbacks(execute=True):
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

        self.assertEqual(GovernmentPriceBatch.objects.count(), 1)
        self.assertEqual(GovernmentPriceItem.objects.count(), 1)
        self.assertEqual(first_result.batch.id, second_result.batch.id)
        self.assertEqual(second_result.created_rows, 0)
        self.assertEqual(second_result.updated_rows, 0)
        self.assertEqual(second_result.deleted_rows, 0)
        self.assertEqual(dispatch_mock.call_count, 2)

    def test_import_excel_skips_vector_sync_when_nothing_changed_and_items_vectorized(self):
        """完全无变更且记录已向量化时，不应再次派发向量化任务。"""

        with patch(
            "price_audit.services.government_price_service.dispatch_vectorize_government_price_batch"
        ) as dispatch_mock:
            with self.captureOnCommitCallbacks(execute=True):
                first_result = government_price_service.import_excel(
                    build_template_like_workbook(),
                    region_name="天津",
                    year=2026,
                    uploaded_by=self.user,
                )

        item = GovernmentPriceItem.objects.get(batch=first_result.batch)
        item.is_vectorized = True
        item.save(update_fields=["is_vectorized"])

        with patch(
            "price_audit.services.government_price_service.dispatch_vectorize_government_price_batch"
        ) as dispatch_mock:
            with self.captureOnCommitCallbacks(execute=True):
                second_result = government_price_service.import_excel(
                    build_template_like_workbook(),
                    region_name="天津",
                    year=2026,
                    uploaded_by=self.user,
                )

        second_result.batch.refresh_from_db()
        item.refresh_from_db()
        self.assertFalse(second_result.vector_task_dispatched)
        self.assertEqual(dispatch_mock.call_count, 0)
        self.assertTrue(item.is_vectorized)
        self.assertEqual(
            second_result.batch.vector_status,
            GovernmentPriceBatch.VectorStatus.ACTIVE,
        )

    def test_import_excel_updates_non_embedding_fields_without_resetting_vectorized(self):
        """只改价格等非向量字段时，应保留已向量化标记。"""

        with patch(
            "price_audit.services.government_price_service.dispatch_vectorize_government_price_batch"
        ):
            with self.captureOnCommitCallbacks(execute=True):
                first_result = government_price_service.import_excel(
                    build_template_like_workbook(),
                    region_name="天津",
                    year=2026,
                    uploaded_by=self.user,
                )

        item = GovernmentPriceItem.objects.get(batch=first_result.batch)
        item.is_vectorized = True
        item.save(update_fields=["is_vectorized"])

        modified_file = build_template_like_workbook(
            rows=[["矿渣硅酸盐水泥", "32.5级 散装", "t", "499.99", "新说明", ""]],
        )
        with patch(
            "price_audit.services.government_price_service.dispatch_vectorize_government_price_batch"
        ) as dispatch_mock:
            with self.captureOnCommitCallbacks(execute=True):
                result = government_price_service.import_excel(
                    modified_file,
                    region_name="天津",
                    year=2026,
                    uploaded_by=self.user,
                )

        item.refresh_from_db()
        self.assertEqual(result.updated_rows, 1)
        self.assertFalse(result.vector_task_dispatched)
        self.assertEqual(dispatch_mock.call_count, 0)
        self.assertTrue(item.is_vectorized)
        self.assertEqual(str(item.benchmark_price), "499.99")
        self.assertEqual(item.description, "新说明")

    def test_import_excel_resets_vectorized_when_embedding_text_changes(self):
        """规格原文变化但业务 key 不变时，应重置向量化标记并重新同步。"""

        with patch(
            "price_audit.services.government_price_service.dispatch_vectorize_government_price_batch"
        ):
            with self.captureOnCommitCallbacks(execute=True):
                first_result = government_price_service.import_excel(
                    build_template_like_workbook(),
                    region_name="天津",
                    year=2026,
                    uploaded_by=self.user,
                )

        item = GovernmentPriceItem.objects.get(batch=first_result.batch)
        item.is_vectorized = True
        item.embedding_text = "old-text"
        item.save(update_fields=["is_vectorized", "embedding_text"])

        modified_file = build_template_like_workbook(
            rows=[["矿渣硅酸盐水泥", "32.5级散装", "t", "379.42", "测试数据", ""]],
        )
        with patch(
            "price_audit.services.government_price_service.dispatch_vectorize_government_price_batch"
        ) as dispatch_mock:
            with self.captureOnCommitCallbacks(execute=True):
                result = government_price_service.import_excel(
                    modified_file,
                    region_name="天津",
                    year=2026,
                    uploaded_by=self.user,
                )

        item.refresh_from_db()
        self.assertEqual(result.updated_rows, 1)
        self.assertTrue(result.vector_task_dispatched)
        dispatch_mock.assert_called_once_with(result.batch.id, [])
        self.assertFalse(item.is_vectorized)
        self.assertNotEqual(item.embedding_text, "old-text")

    def test_import_excel_adds_updates_and_deletes_items_in_same_batch(self):
        """同城同年再次上传时，应只对差异行做增量同步。"""

        first_file = build_template_like_workbook(
            rows=[
                ["矿渣硅酸盐水泥", "32.5级 散装", "t", "379.42", "旧说明", ""],
                ["普通硅酸盐水泥", "42.5级 散装", "t", "437.53", "保留项", ""],
            ]
        )
        second_file = build_template_like_workbook(
            rows=[
                ["矿渣硅酸盐水泥", "32.5级 散装", "t", "399.99", "新说明", ""],
                ["粉煤灰水泥", "P.F 32.5", "t", "288.00", "新增项", ""],
            ]
        )

        with patch(
            "price_audit.services.government_price_service.dispatch_vectorize_government_price_batch"
        ) as dispatch_mock:
            with self.captureOnCommitCallbacks(execute=True):
                first_result = government_price_service.import_excel(
                    first_file,
                    region_name="天津",
                    year=2026,
                    uploaded_by=self.user,
                )
                second_result = government_price_service.import_excel(
                    second_file,
                    region_name="天津",
                    year=2026,
                    uploaded_by=self.user,
                )

        self.assertEqual(first_result.batch.id, second_result.batch.id)
        self.assertEqual(GovernmentPriceBatch.objects.count(), 1)
        self.assertEqual(GovernmentPriceItem.objects.count(), 2)
        self.assertEqual(second_result.created_rows, 1)
        self.assertEqual(second_result.updated_rows, 1)
        self.assertEqual(second_result.deleted_rows, 1)
        item_names = set(GovernmentPriceItem.objects.values_list("material_name_raw", flat=True))
        self.assertEqual(item_names, {"矿渣硅酸盐水泥", "粉煤灰水泥"})
        updated_item = GovernmentPriceItem.objects.get(material_name_raw="矿渣硅酸盐水泥")
        self.assertEqual(str(updated_item.benchmark_price), "399.99")
        self.assertFalse(updated_item.is_vectorized)
        self.assertEqual(dispatch_mock.call_count, 2)

    def test_import_excel_dispatches_deleted_item_ids(self):
        """删除旧条目时，应把被删除的 item id 一并传给向量同步任务。"""

        first_file = build_template_like_workbook(
            rows=[
                ["矿渣硅酸盐水泥", "32.5级 散装", "t", "379.42", "旧说明", ""],
                ["普通硅酸盐水泥", "42.5级 散装", "t", "437.53", "保留项", ""],
            ]
        )
        second_file = build_template_like_workbook(
            rows=[["矿渣硅酸盐水泥", "32.5级 散装", "t", "379.42", "旧说明", ""]],
        )
        with patch(
            "price_audit.services.government_price_service.dispatch_vectorize_government_price_batch"
        ) as dispatch_mock:
            with self.captureOnCommitCallbacks(execute=True):
                result1 = government_price_service.import_excel(
                    first_file,
                    region_name="天津",
                    year=2026,
                    uploaded_by=self.user,
                )
                deleted_item_id = GovernmentPriceItem.objects.exclude(
                    material_name_raw="矿渣硅酸盐水泥"
                ).get(batch=result1.batch).id
                result2 = government_price_service.import_excel(
                    second_file,
                    region_name="天津",
                    year=2026,
                    uploaded_by=self.user,
                )

        self.assertEqual(result2.deleted_rows, 1)
        self.assertEqual(dispatch_mock.call_args_list[-1].args, (result2.batch.id, [deleted_item_id]))

    def test_import_excel_deactivates_extra_duplicate_batches(self):
        """若历史上同城同年存在多个批次，应复用主批次并让其它批次失效。"""

        old_batch = GovernmentPriceBatch.objects.create(
            region_name="天津",
            year=2026,
            is_active=True,
            total_rows=1,
            success_rows=1,
        )
        new_batch = GovernmentPriceBatch.objects.create(
            region_name="天津",
            year=2026,
            is_active=True,
            total_rows=1,
            success_rows=1,
        )
        GovernmentPriceItem.objects.create(
            batch=new_batch,
            row_no=2,
            material_name_raw="矿渣硅酸盐水泥",
            material_name_normalized="矿渣硅酸盐水泥",
            spec_model_raw="32.5级 散装",
            spec_model_normalized="32.5级散装",
            unit_raw="t",
            unit_normalized="t",
            benchmark_price="379.42",
            price_min="285.80",
            price_max="515.00",
            description="测试数据",
            embedding_text="材料名称:矿渣硅酸盐水泥 | 规格型号:32.5级 散装 | 单位:t",
            is_vectorized=True,
            raw_row_data={
                "material_name": "矿渣硅酸盐水泥",
                "spec_model": "32.5级 散装",
                "unit": "t",
                "benchmark_price": "379.42",
                "price_min": "285.80",
                "price_max": "515.00",
                "description": "测试数据",
                "is_tax_included": True,
                "embedding_text": "材料名称:矿渣硅酸盐水泥 | 规格型号:32.5级 散装 | 单位:t",
            },
        )

        with patch(
            "price_audit.services.government_price_service.dispatch_vectorize_government_price_batch"
        ) as dispatch_mock:
            with self.captureOnCommitCallbacks(execute=True):
                result = government_price_service.import_excel(
                    build_template_like_workbook(),
                    region_name="天津",
                    year=2026,
                    uploaded_by=self.user,
                )

        old_batch.refresh_from_db()
        new_batch.refresh_from_db()
        self.assertFalse(old_batch.is_active)
        self.assertTrue(new_batch.is_active)
        self.assertEqual(result.batch.id, new_batch.id)
        self.assertEqual(dispatch_mock.call_count, 0)

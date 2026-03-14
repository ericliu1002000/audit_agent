"""价格审核测试辅助函数。"""

from __future__ import annotations

import tempfile
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from openpyxl import Workbook

from price_audit.constants import EXHIBITION_CENTER_MEIJIANG, PROJECT_NATURE_TEMPORARY
from price_audit.models import PriceAuditRowDecision, PriceAuditSubmission, PriceAuditSubmissionRow


DEFAULT_SUBMISSION_DATA_ROWS = [
    [1, "场地租", "平米", 9, 100, 3, 2700, "场地租赁说明", None, None, None, None, None, None, None],
    [2, "特装展台搭建", "-", None, None, None, 1200, "特装父项", None, None, None, None, None, None, None],
    ["2.1", "特装展台-地台制作", "㎡", 100, 10, None, 1000, "地台制作说明", None, None, None, None, None, None, None],
    ["2.2", "特装展台-地台包边", "m", 20, 10, None, 200, "地台包边说明", None, None, None, None, None, None, None],
    [3, "电费", None, None, None, None, 500, "电费预估", None, None, None, None, None, None, None],
    [None, "小计", "-", "-", "-", "-", 4400, "-", None, None, None, None, None, None, None],
    [None, "税费", "-", "-", "-", "-", 100, "税费说明", None, None, None, None, None, None, None],
    [None, "合计", "-", "-", "-", "-", 4500, None, None, None, None, None, None, None, None],
]


class TempMediaRootMixin:
    """为文件类测试提供隔离的 MEDIA_ROOT。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_root_dir = tempfile.TemporaryDirectory()
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root_dir.name)
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_override.disable()
        cls._media_root_dir.cleanup()
        super().tearDownClass()


def _append_template_headers(sheet, *, clear_audit_headers: bool = False) -> None:
    audit_title = None if clear_audit_headers else "审核"
    reduction_title = None if clear_audit_headers else "审减原因/未审减原因"
    audit_sub_headers = [None, None, None, None, None, None]
    if not clear_audit_headers:
        audit_sub_headers = ["计量\n单位", "单价（元）", "数量", "天数", "审核金额（元）", "审减金额（元）"]

    sheet.append(
        [
            "序号",
            "费用类型",
            "送审",
            None,
            None,
            None,
            None,
            None,
            audit_title,
            None,
            None,
            None,
            None,
            None,
            reduction_title,
        ]
    )
    sheet.append(
        [
            None,
            None,
            "计量\n单位",
            "单价（元）",
            "数量",
            "天数",
            "预算金额（元）",
            "预算编制说明",
            *audit_sub_headers,
            None,
        ]
    )


def build_price_audit_submission_workbook(
    *,
    filename: str = "submission.xlsx",
    data_rows: list[list[object]] | None = None,
    clear_audit_headers: bool = False,
) -> SimpleUploadedFile:
    """构造一份价格审核送审表测试文件。"""

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "审核"
    _append_template_headers(sheet, clear_audit_headers=clear_audit_headers)
    for row in DEFAULT_SUBMISSION_DATA_ROWS if data_rows is None else data_rows:
        sheet.append(row)

    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return SimpleUploadedFile(
        filename,
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def create_submission_with_workbook(
    *,
    created_by,
    price_batch,
    workbook: SimpleUploadedFile | None = None,
    original_filename: str = "submission.xlsx",
    project_name: str = "submission",
    exhibition_center_id: int = EXHIBITION_CENTER_MEIJIANG,
    project_nature: int = PROJECT_NATURE_TEMPORARY,
    status: str = PriceAuditSubmission.Status.PENDING,
) -> PriceAuditSubmission:
    """创建一条带源文件的送审单。"""

    submission = PriceAuditSubmission.objects.create(
        created_by=created_by,
        price_batch=price_batch,
        original_filename=original_filename,
        project_name=project_name,
        exhibition_center_id=exhibition_center_id,
        project_nature=project_nature,
        status=status,
    )
    uploaded_file = workbook or build_price_audit_submission_workbook(filename=original_filename)
    submission.source_file.save(uploaded_file.name, uploaded_file, save=True)
    return submission


def create_submission_row(
    submission: PriceAuditSubmission,
    **overrides,
) -> PriceAuditSubmissionRow:
    """创建一条送审行。"""

    defaults = {
        "excel_row_no": 3,
        "sequence_no": "1",
        "parent_sequence_no": "",
        "row_type": PriceAuditSubmissionRow.RowType.LEAF,
        "fee_type": "场地租",
        "submitted_unit": "平米",
        "submitted_unit_price": "9.0000",
        "submitted_quantity": "100.0000",
        "submitted_days": "3.0000",
        "submitted_amount": "2700.0000",
        "budget_note": "场地租赁说明",
        "raw_row_data": {},
    }
    defaults.update(overrides)
    row = PriceAuditSubmissionRow.objects.create(submission=submission, **defaults)
    row.refresh_from_db()
    return row


def create_row_decision(
    submission_row: PriceAuditSubmissionRow,
    **overrides,
) -> PriceAuditRowDecision:
    """创建一条审核结果。"""

    defaults = {
        "status": PriceAuditRowDecision.Status.COMPLETED,
        "result_type": PriceAuditRowDecision.ResultType.UNCHANGED,
        "reviewed_unit": submission_row.submitted_unit,
        "reviewed_unit_price": submission_row.submitted_unit_price,
        "reviewed_quantity": submission_row.submitted_quantity,
        "reviewed_days": submission_row.submitted_days,
        "reviewed_amount": submission_row.submitted_amount,
        "reduction_amount": "0.0000",
        "reason": "价格合理",
        "evidence_json": {},
        "error_message": "",
    }
    defaults.update(overrides)
    decision = PriceAuditRowDecision.objects.create(submission_row=submission_row, **defaults)
    decision.refresh_from_db()
    return decision

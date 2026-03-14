"""价格送审单模型。"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from price_audit.constants import EXHIBITION_CENTER_CHOICES, PROJECT_NATURE_CHOICES
from price_audit.models.common import (
    price_audit_submission_audited_excel_upload_to,
    price_audit_submission_source_upload_to,
)


class PriceAuditSubmission(models.Model):
    """一次送审文件上传与审核任务。"""

    class Status(models.TextChoices):
        PENDING = "pending", "排队中"
        PROCESSING = "processing", "处理中"
        COMPLETED = "completed", "已完成"
        FAILED = "failed", "失败"

    class Step(models.TextChoices):
        QUEUED = "queued", "已入队"
        PARSING = "parsing", "解析中"
        REVIEWING = "reviewing", "审核中"
        AGGREGATING = "aggregating", "汇总中"
        EXPORTING = "exporting", "导出中"
        COMPLETED = "completed", "已完成"
        FAILED = "failed", "失败"

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="price_audit_submissions",
        verbose_name="上传人",
    )
    price_batch = models.ForeignKey(
        "price_audit.GovernmentPriceBatch",
        on_delete=models.PROTECT,
        related_name="submissions",
        verbose_name="使用标准价批次",
    )
    original_filename = models.CharField("原始文件名", max_length=255)
    project_name = models.CharField("项目名称", max_length=255, blank=True)
    exhibition_center_id = models.PositiveSmallIntegerField(
        "会展中心",
        choices=EXHIBITION_CENTER_CHOICES,
    )
    project_nature = models.PositiveSmallIntegerField(
        "项目性质",
        choices=PROJECT_NATURE_CHOICES,
    )
    source_file = models.FileField(
        "送审文件",
        upload_to=price_audit_submission_source_upload_to,
    )
    audited_excel_file = models.FileField(
        "审核表文件",
        upload_to=price_audit_submission_audited_excel_upload_to,
        blank=True,
    )
    status = models.CharField(
        "状态",
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    current_step = models.CharField(
        "当前阶段",
        max_length=20,
        choices=Step.choices,
        default=Step.QUEUED,
        db_index=True,
    )
    progress_percent = models.PositiveSmallIntegerField("进度百分比", default=0)
    total_rows = models.PositiveIntegerField("待审核明细行数", default=0)
    processed_rows = models.PositiveIntegerField("已处理明细行数", default=0)
    failed_rows = models.PositiveIntegerField("失败行数", default=0)
    current_message = models.CharField("当前进度说明", max_length=255, blank=True)
    submitted_total_amount = models.DecimalField(
        "送审总金额",
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
    )
    reviewed_total_amount = models.DecimalField(
        "审核总金额",
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
    )
    reduction_total_amount = models.DecimalField(
        "审减总金额",
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
    )
    report_json = models.JSONField("审核报告", default=dict, blank=True)
    error_message = models.TextField("错误信息", blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "price_audit_submission"
        verbose_name = "价格送审单"
        verbose_name_plural = "价格送审单"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"送审#{self.pk} {self.original_filename}"

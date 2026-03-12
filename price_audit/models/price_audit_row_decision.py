"""价格送审审核结果模型。"""

from __future__ import annotations

from django.db import models


class PriceAuditRowDecision(models.Model):
    """一条送审行对应的一条审核结果。"""

    class Status(models.TextChoices):
        PENDING = "pending", "排队中"
        PROCESSING = "processing", "处理中"
        COMPLETED = "completed", "已完成"
        FAILED = "failed", "失败"

    class ResultType(models.TextChoices):
        UNCHANGED = "unchanged", "未调整"
        ADJUSTED = "adjusted", "已调整"
        AGGREGATED = "aggregated", "汇总结果"
        SKIPPED = "skipped", "跳过"

    submission_row = models.OneToOneField(
        "price_audit.PriceAuditSubmissionRow",
        on_delete=models.CASCADE,
        related_name="decision",
        verbose_name="所属送审行",
    )
    status = models.CharField(
        "状态",
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    result_type = models.CharField(
        "结果类型",
        max_length=20,
        choices=ResultType.choices,
        blank=True,
    )
    reviewed_unit = models.CharField("审核单位", max_length=32, blank=True)
    reviewed_unit_price = models.DecimalField(
        "审核单价",
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
    )
    reviewed_quantity = models.DecimalField(
        "审核数量",
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
    )
    reviewed_days = models.DecimalField(
        "审核天数",
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
    )
    reviewed_amount = models.DecimalField(
        "审核金额",
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
    )
    reduction_amount = models.DecimalField(
        "审减金额",
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
    )
    reason = models.TextField("审减原因", blank=True)
    evidence_json = models.JSONField("审核证据", default=dict, blank=True)
    error_message = models.TextField("错误信息", blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "price_audit_row_decision"
        verbose_name = "价格审核结果"
        verbose_name_plural = "价格审核结果"
        ordering = ("submission_row__submission_id", "submission_row__excel_row_no")

    def __str__(self) -> str:
        return f"结果#{self.pk} row={self.submission_row_id}"

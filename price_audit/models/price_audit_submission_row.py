"""价格送审明细行模型。"""

from __future__ import annotations

from django.db import models


class PriceAuditSubmissionRow(models.Model):
    """送审表中的一行原始数据。"""

    class RowType(models.TextChoices):
        LEAF = "leaf", "明细行"
        GROUP = "group", "父项汇总行"
        SUMMARY = "summary", "汇总行"

    submission = models.ForeignKey(
        "price_audit.PriceAuditSubmission",
        on_delete=models.CASCADE,
        related_name="rows",
        verbose_name="所属送审单",
    )
    excel_row_no = models.PositiveIntegerField("Excel 行号")
    sequence_no = models.CharField("序号", max_length=32, blank=True)
    parent_sequence_no = models.CharField("父级序号", max_length=32, blank=True)
    row_type = models.CharField(
        "行类型",
        max_length=16,
        choices=RowType.choices,
        default=RowType.LEAF,
        db_index=True,
    )
    fee_type = models.CharField("费用类型", max_length=255)
    submitted_unit = models.CharField("送审单位", max_length=32, blank=True)
    submitted_unit_price = models.DecimalField(
        "送审单价",
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
    )
    submitted_quantity = models.DecimalField(
        "送审数量",
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
    )
    submitted_days = models.DecimalField(
        "送审天数",
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
    )
    submitted_amount = models.DecimalField(
        "送审金额",
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
    )
    budget_note = models.TextField("预算说明", blank=True)
    raw_row_data = models.JSONField("原始行数据", default=dict, blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "price_audit_submission_row"
        verbose_name = "价格送审明细行"
        verbose_name_plural = "价格送审明细行"
        ordering = ("submission_id", "excel_row_no")
        constraints = [
            models.UniqueConstraint(
                fields=["submission", "excel_row_no"],
                name="uniq_price_audit_submission_row_excel_row",
            )
        ]

    def __str__(self) -> str:
        return f"{self.sequence_no or '-'} {self.fee_type}"

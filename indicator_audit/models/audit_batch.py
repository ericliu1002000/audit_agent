from django.conf import settings
from django.db import models


class AuditBatch(models.Model):
    """审核批次：对应一次“文件夹级”的批量审核任务。"""

    batch_name = models.CharField(
        "批次名称",
        max_length=255,
        unique=True,
        help_text="批次展示名称，通常为目录名，例如“2025教育局专项资金第一批”。",
    )
    AUDIT_TYPE_DECLARATION = "declaration"
    AUDIT_TYPE_SELF_EVAL = "self_eval"
    AUDIT_TYPE_CHOICES = (
        (AUDIT_TYPE_DECLARATION, "目标申报"),
        (AUDIT_TYPE_SELF_EVAL, "自评自查"),
    )

    audit_type = models.CharField(
        "审核类型",
        max_length=32,
        choices=AUDIT_TYPE_CHOICES,
        default=AUDIT_TYPE_DECLARATION,
        db_index=True,
        help_text="区分绩效目标申报与绩效自评自查两类业务。",
    )
    description = models.TextField(
        "批次说明",
        blank=True,
        null=True,
        help_text="可选说明信息，用于描述本批次的来源或用途。",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="创建人",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="audit_batches",
        help_text="发起本次批量审核的用户。",
    )

    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = (
        (STATUS_PENDING, "排队中"),
        (STATUS_PROCESSING, "处理中"),
        (STATUS_COMPLETED, "已完成"),
        (STATUS_FAILED, "失败"),
    )

    status = models.CharField(
        "状态",
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
        help_text="批次当前的处理状态：排队中/处理中/已完成/失败。",
    )

    total_files = models.PositiveIntegerField(
        "文件总数",
        default=0,
        help_text="该批次包含的文件总数。",
    )
    completed_files = models.PositiveIntegerField(
        "已完成文件数",
        default=0,
        help_text="审核已完成的文件数量。",
    )
    failed_files = models.PositiveIntegerField(
        "失败文件数",
        default=0,
        help_text="审核失败的文件数量。",
    )

    created_at = models.DateTimeField(
        "创建时间",
        auto_now_add=True,
        help_text="批次创建时间。",
    )
    updated_at = models.DateTimeField(
        "更新时间",
        auto_now=True,
        help_text="批次最近一次状态更新的时间。",
    )

    class Meta:
        db_table = "indicator_audit_batch"
        verbose_name = "审核批次"
        verbose_name_plural = "审核批次"
        ordering = ("-created_at",)

    def __str__(self) -> str:  # pragma: no cover - 调试友好的展示
        return self.batch_name

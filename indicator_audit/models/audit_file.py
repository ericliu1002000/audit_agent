from django.conf import settings
from django.db import models


class AuditFile(models.Model):
    """单个 Excel 文件的审核记录，无论是否隶属于某个批次。"""

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="创建人",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="audit_files",
        help_text="发起本次审核的用户。",
    )
    batch = models.ForeignKey(
        "indicator_audit.AuditBatch",
        verbose_name="所属批次",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="files",
        help_text="所属审核批次，为空表示独立文件审核。",
    )
    original_filename = models.CharField(
        "原始文件名",
        max_length=255,
        help_text="上传时的原始 Excel 文件名。",
    )
    relative_path = models.CharField(
        "相对路径",
        max_length=512,
        blank=True,
        null=True,
        help_text="文件夹内的相对路径，用于批次内断点续传与文件匹配。",
    )
    file_size = models.BigIntegerField(
        "文件大小",
        blank=True,
        null=True,
        help_text="文件大小（字节）。",
    )
    file_hash = models.CharField(
        "文件指纹",
        max_length=64,
        db_index=True,
        help_text="文件内容指纹（如 SHA256），用于跨批次结果复用与去重。",
    )

    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_SKIPPED = "skipped"
    STATUS_CHOICES = (
        (STATUS_PENDING, "排队中"),
        (STATUS_PROCESSING, "处理中"),
        (STATUS_COMPLETED, "已完成"),
        (STATUS_FAILED, "失败"),
        (STATUS_SKIPPED, "已跳过"),
    )

    status = models.CharField(
        "处理状态",
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
        help_text="文件审核状态：排队中/处理中/已完成/失败/已跳过。",
    )
    reused_from_file = models.ForeignKey(
        "self",
        verbose_name="复用来源文件",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="reused_by_files",
        help_text="如果本次结果复用了历史审核结果，这里指向原始文件记录。",
    )

    project_name = models.CharField(
        "项目名称",
        max_length=255,
        blank=True,
        null=True,
        help_text="从结构化数据中提取的项目名称，便于列表展示与检索。",
    )
    department = models.CharField(
        "主管部门",
        max_length=255,
        blank=True,
        null=True,
        help_text="项目所属主管预算部门。",
    )
    score = models.IntegerField(
        "健康分",
        blank=True,
        null=True,
        help_text="该文件审核结果的健康分（0-100），来自审核报告。",
    )
    critical_count = models.PositiveIntegerField(
        "红灯数量",
        default=0,
        help_text="该文件中红灯（critical）问题数量。",
    )
    warning_count = models.PositiveIntegerField(
        "黄灯数量",
        default=0,
        help_text="该文件中黄灯（warning）问题数量。",
    )
    info_count = models.PositiveIntegerField(
        "蓝灯数量",
        default=0,
        help_text="该文件中蓝灯（info）提示数量。",
    )
    total_amount = models.DecimalField(
        "项目总金额",
        max_digits=18,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="该项目的资金总额（万元），可从结构化数据中提取。",
    )

    pydantic_json = models.JSONField(
        "结构化数据",
        blank=True,
        null=True,
        help_text="原始结构化数据（PerformanceDeclarationSchema）序列化后的 JSON。",
    )
    report_json = models.JSONField(
        "审核报告",
        blank=True,
        null=True,
        help_text="标准化后的审核报告 JSON，对应前端展示的数据结构。",
    )

    created_at = models.DateTimeField(
        "创建时间",
        auto_now_add=True,
        help_text="文件记录创建时间（上传时间）。",
    )
    updated_at = models.DateTimeField(
        "更新时间",
        auto_now=True,
        help_text="文件记录最近一次更新的时间。",
    )

    class Meta:
        db_table = "indicator_audit_file"
        verbose_name = "审核文件"
        verbose_name_plural = "审核文件"
        ordering = ("-created_at",)

    def __str__(self) -> str:  # pragma: no cover - 调试友好的展示
        return self.original_filename

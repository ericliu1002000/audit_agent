from django.db import models

from indicator_audit.constants import ISSUE_TYPE_CHOICES, SEVERITY_CHOICES


class AuditIssue(models.Model):
    """审核问题明细：记录每一条红灯/黄灯/蓝灯问题。"""

    file = models.ForeignKey(
        "indicator_audit.AuditFile",
        verbose_name="所属文件",
        on_delete=models.CASCADE,
        related_name="issues",
        help_text="该问题所属的 Excel 文件。",
    )

    severity = models.CharField(
        "严重程度",
        max_length=16,
        choices=SEVERITY_CHOICES,
        help_text="问题严重程度：红灯/黄灯/蓝灯。",
        db_index=True,
    )
    source = models.CharField(
        "来源",
        max_length=20,
        help_text="问题来源：rules（刚性规则）/ai（语义审查）/system（系统）。",
    )
    source_label = models.CharField(
        "来源标签",
        max_length=32,
        blank=True,
        null=True,
        help_text="来源中文标签，如“刚性规则”“智能审查”“系统”。",
    )
    type = models.CharField(
        "问题类型",
        max_length=32,
        choices=ISSUE_TYPE_CHOICES,
        blank=True,
        null=True,
        db_index=True,
        help_text=(
            "业务问题类型：完整性缺失 / 合规性问题 / 可衡量性不足 / "
            "相关性缺失 / 投入产出不匹配。"
        ),
    )
    title = models.CharField(
        "标题",
        max_length=255,
        help_text="问题的简短标题，便于列表快速浏览。",
    )
    description = models.TextField(
        "问题描述",
        blank=True,
        null=True,
        help_text="问题的详细说明或判定依据。",
    )
    position = models.CharField(
        "定位信息",
        max_length=255,
        blank=True,
        null=True,
        help_text="问题所在位置，例如“项目资金”“指标：系统验收合格率”等。",
    )
    suggestion = models.TextField(
        "整改建议",
        blank=True,
        null=True,
        help_text="针对该问题的整改建议或优化意见。",
    )

    created_at = models.DateTimeField(
        "创建时间",
        auto_now_add=True,
        help_text="问题记录生成时间。",
    )

    class Meta:
        db_table = "indicator_audit_issue"
        verbose_name = "审核问题"
        verbose_name_plural = "审核问题"
        ordering = ("-created_at",)

    def __str__(self) -> str:  # pragma: no cover - 调试友好的展示
        return f"[{self.severity}] {self.title}"


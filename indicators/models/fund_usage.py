from django.db import models


class FundUsage(models.Model):
    """表示从外部数据导入的资金使用类型。"""

    # 资金使用类别名称（如“信息系统建设运维类”）
    name = models.CharField(
        "资金使用类别名称",
        max_length=255,
        help_text="资金使用类别名称，例如“信息系统建设运维类”。",
    )
    # 可选：记录来源 CSV 文件名或标识
    source_file = models.CharField(
        "来源文件",
        max_length=255,
        blank=True,
        null=True,
        help_text="可选：标记该类别来自哪一个 CSV 或外部文件。",
    )

    def __str__(self) -> str:  # pragma: no cover - simple debug helper
        return self.name

    class Meta:
        verbose_name = "资金用途/项目"
        verbose_name_plural = "资金用途/项目"


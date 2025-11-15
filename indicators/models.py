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


class Indicator(models.Model):
    """指标主表，描述三级指标的层级与元数据。"""

    # 对应的资金使用类别
    fund_usage = models.ForeignKey(
        FundUsage,
        verbose_name="资金使用类别",
        on_delete=models.CASCADE,
        related_name="indicators",
        help_text="该指标所属的资金使用类别。",
    )
    # 一级指标分类（如“产出指标”）
    level_1 = models.CharField(
        "一级指标",
        max_length=255,
        help_text="一级指标分类，例如“产出指标”。",
    )
    # 二级指标分类（如“质量指标”）
    level_2 = models.CharField(
        "二级指标",
        max_length=255,
        help_text="二级指标分类，例如“质量指标”。",
    )
    # 三级指标名称，描述具体指标
    level_3 = models.CharField(
        "三级指标",
        max_length=255,
        help_text="三级指标名称，如“系统验收合格率”。",
    )
    # 指标的解释说明，可为空
    explanation = models.TextField(
        "指标解释",
        blank=True,
        null=True,
        help_text="指标解释或补充说明，可为空。",
    )
    # 指标性质或比较符号（如“≥”“≤”“定性描述”）
    nature = models.CharField(
        "指标性质",
        max_length=255,
        help_text="指标的性质或比较符号，例如“≥”“≤”“定性描述”。",
    )
    # 指标计量单位（如“%”“个”“万元”）
    unit = models.CharField(
        "计量单位",
        max_length=20,
        help_text="指标计量单位，如“%”“个”“万元”。",
    )
    # 指标来源（如“中央”“广东”）
    province = models.CharField(
        "指标省份",
        max_length=10,
        help_text="数据来源或发布主体，例如“天津市”“广东省”。",
    )
    # 是否已向量化，用于后续检索同步
    is_vectorized = models.BooleanField(
        "是否向量化",
        default=False,
        help_text="是否已向量化（由脚本维护，后台仅展示）。",
    )

    def __str__(self) -> str:  # pragma: no cover - simple debug helper
        return self.level_3

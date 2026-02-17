from django.db import models


class BudgetPriceItem(models.Model):
    """预算审核标准价格清单（政府侧）。"""

    material_name = models.CharField("材料名称", max_length=255)
    spec_model = models.CharField("规格型号", max_length=255, blank=True, null=True)
    unit = models.CharField("单位", max_length=50, blank=True, null=True)
    base_price = models.DecimalField("中准价格", max_digits=12, decimal_places=2)
    price_low = models.DecimalField(
        "区间最低价", max_digits=12, decimal_places=2, blank=True, null=True
    )
    price_high = models.DecimalField(
        "区间最高价", max_digits=12, decimal_places=2, blank=True, null=True
    )
    is_tax_included = models.BooleanField("是否含税", default=True)
    publish_month = models.CharField("发布月份", max_length=20, db_index=True)
    region = models.CharField("地区", max_length=100, db_index=True)
    embedding_text = models.CharField("向量文本", max_length=600)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "budget_audit_price_item"
        verbose_name = "预算审核标准价"
        verbose_name_plural = "预算审核标准价"
        ordering = ("-publish_month", "material_name", "spec_model")
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "region",
                    "publish_month",
                    "material_name",
                    "spec_model",
                    "unit",
                    "is_tax_included",
                ],
                name="uniq_budget_price_item_main_fields",
            )
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.material_name} {self.spec_model or ''}".strip()


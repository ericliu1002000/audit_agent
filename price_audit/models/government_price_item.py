"""政府标准价明细模型。"""

from django.db import models


class GovernmentPriceItem(models.Model):
    """政府标准价明细行。

    功能说明:
        存储某个导入批次中的单行政府标准价数据，作为后续供应商报价比对的标准来源。
    使用示例:
        item = GovernmentPriceItem.objects.create(batch=batch, row_no=2, ...)
    """

    batch = models.ForeignKey(
        "price_audit.GovernmentPriceBatch",
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="所属批次",
    )
    row_no = models.PositiveIntegerField("Excel 行号")
    material_name_raw = models.CharField("材料名称", max_length=255)
    material_name_normalized = models.CharField(
        "材料名称标准化",
        max_length=255,
        db_index=True,
    )
    spec_model_raw = models.CharField("规格型号", max_length=255, blank=True)
    spec_model_normalized = models.CharField(
        "规格型号标准化",
        max_length=255,
        blank=True,
        db_index=True,
    )
    unit_raw = models.CharField("单位", max_length=50, blank=True)
    unit_normalized = models.CharField(
        "单位标准化",
        max_length=50,
        blank=True,
        db_index=True,
    )
    benchmark_price = models.DecimalField("中准价格", max_digits=12, decimal_places=2)
    price_min = models.DecimalField(
        "区间最低价",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    price_max = models.DecimalField(
        "区间最高价",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    description = models.TextField("说明", blank=True)
    is_tax_included = models.BooleanField("是否含税", default=True)
    raw_row_data = models.JSONField("原始行数据", default=dict, blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        db_table = "price_audit_government_price_item"
        verbose_name = "政府标准价明细"
        verbose_name_plural = "政府标准价明细"
        ordering = ("batch_id", "row_no")
        constraints = [
            models.UniqueConstraint(
                fields=["batch", "row_no"],
                name="uniq_government_price_item_batch_row_no",
            )
        ]

    def __str__(self):
        """返回更适合后台列表展示的材料名称。"""

        spec_text = f" {self.spec_model_raw}" if self.spec_model_raw else ""
        return f"{self.material_name_raw}{spec_text}".strip()

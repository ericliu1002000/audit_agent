"""政府标准价导入批次模型。"""

from django.conf import settings
from django.db import models

from price_audit.models.common import government_price_source_upload_to


class GovernmentPriceBatch(models.Model):
    """政府标准价导入批次。

    功能说明:
        记录一次完整的政府标准价导入任务，包括地区、年份、上传文件、上传人和是否生效。
        同地区同年份再次上传时，旧批次会被标记为失效，新批次成为当前生效版本。
    使用示例:
        batch = GovernmentPriceBatch.objects.create(region_name="天津", year=2026)
    """

    region_name = models.CharField("地区", max_length=100, db_index=True)
    year = models.PositiveIntegerField("年份", db_index=True)
    source_file = models.FileField(
        "源文件",
        upload_to=government_price_source_upload_to,
        blank=True,
    )
    source_filename = models.CharField("原始文件名", max_length=255, blank=True)
    is_active = models.BooleanField("是否生效", default=True, db_index=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="government_price_batches",
        verbose_name="上传人",
    )
    replaced_batch = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="replacement_batches",
        verbose_name="被替换批次",
    )
    total_rows = models.PositiveIntegerField("总行数", default=0)
    success_rows = models.PositiveIntegerField("有效行数", default=0)
    remark = models.TextField("备注", blank=True)
    template_version = models.CharField("模板版本", max_length=20, default="v1")
    deactivated_at = models.DateTimeField("失效时间", null=True, blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "price_audit_government_price_batch"
        verbose_name = "政府标准价批次"
        verbose_name_plural = "政府标准价批次"
        ordering = ("-year", "region_name", "-created_at")

    def __str__(self):
        """返回后台列表和日志中更易识别的批次显示名。"""

        return f"{self.region_name} {self.year} 批次#{self.pk}"

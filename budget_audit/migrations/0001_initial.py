from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="BudgetPriceItem",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("material_name", models.CharField(max_length=255, verbose_name="材料名称")),
                (
                    "spec_model",
                    models.CharField(
                        blank=True, max_length=255, null=True, verbose_name="规格型号"
                    ),
                ),
                (
                    "unit",
                    models.CharField(blank=True, max_length=50, null=True, verbose_name="单位"),
                ),
                (
                    "base_price",
                    models.DecimalField(decimal_places=2, max_digits=12, verbose_name="中准价格"),
                ),
                (
                    "price_low",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=12,
                        null=True,
                        verbose_name="区间最低价",
                    ),
                ),
                (
                    "price_high",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=12,
                        null=True,
                        verbose_name="区间最高价",
                    ),
                ),
                ("is_tax_included", models.BooleanField(default=True, verbose_name="是否含税")),
                ("publish_month", models.CharField(db_index=True, max_length=20, verbose_name="发布月份")),
                ("region", models.CharField(db_index=True, max_length=100, verbose_name="地区")),
                ("embedding_text", models.CharField(max_length=600, verbose_name="向量文本")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
            ],
            options={
                "verbose_name": "预算审核标准价",
                "verbose_name_plural": "预算审核标准价",
                "db_table": "budget_audit_price_item",
                "ordering": ("-publish_month", "material_name", "spec_model"),
            },
        ),
        migrations.AddConstraint(
            model_name="budgetpriceitem",
            constraint=models.UniqueConstraint(
                fields=(
                    "region",
                    "publish_month",
                    "material_name",
                    "spec_model",
                    "unit",
                    "is_tax_included",
                ),
                name="uniq_budget_price_item_main_fields",
            ),
        ),
    ]


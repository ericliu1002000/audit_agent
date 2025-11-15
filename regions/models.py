from django.db import models


class Province(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        verbose_name="省份名称",
    )
    code = models.CharField(
        max_length=20,
        unique=True,
        db_index=True,
        verbose_name="省份代码",
        help_text="例如：11",
    )

    class Meta:
        verbose_name = "省份"
        verbose_name_plural = "省份"

    def __str__(self) -> str:
        return f"{self.id}-{self.name}-{self.code}"


class City(models.Model):
    id = models.BigAutoField(primary_key=True)
    province = models.ForeignKey(
        Province,
        on_delete=models.CASCADE,
        related_name="cities",
        verbose_name="所属省份",
    )
    name = models.CharField(
        max_length=100,
        db_index=True,
        verbose_name="城市名称",
    )
    code = models.CharField(
        max_length=20,
        unique=True,
        db_index=True,
        verbose_name="城市代码",
        help_text="例如：1101",
    )

    class Meta:
        verbose_name = "城市"
        verbose_name_plural = "城市"
        unique_together = ("province", "name")

    def __str__(self) -> str:
        return self.name

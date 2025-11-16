from django.db import models


class IndicatorManager(models.Manager):
    """默认只返回启用的指标."""

    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)


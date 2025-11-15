from django.contrib import admin

from .models import FundUsage, Indicator


class IndicatorInline(admin.TabularInline):
    """允许在 FundUsage 页面内直接维护指标。"""

    model = Indicator
    extra = 0
    fields = (
        "level_1",
        "level_2",
        "level_3",
        "province_id",
        "nature",
        "unit",
        "is_vectorized",
    )
    readonly_fields = ("is_vectorized",)
    show_change_link = True


@admin.register(FundUsage)
class FundUsageAdmin(admin.ModelAdmin):
    """资金使用类别管理，同时展示其下的指标。"""

    list_display = ("name", "source_file", "indicator_count")
    search_fields = ("name", "source_file")
    inlines = (IndicatorInline,)

    @admin.display(description="指标数量")
    def indicator_count(self, obj):
        return obj.indicators.count()


@admin.register(Indicator)
class IndicatorAdmin(admin.ModelAdmin):
    """指标管理，支持按资金使用类别筛选。"""

    list_display = (
        "level_3",
        "fund_usage",
        "level_1",
        "level_2",
        "province_id",
        "nature",
        "unit",
        "is_vectorized",
    )
    list_filter = ("fund_usage", "province_id", "is_vectorized")
    search_fields = (
        "level_1",
        "level_2",
        "level_3",
        "explanation",
        "province_id__name",
        "province_id__code",
    )
    list_select_related = ("fund_usage", "province_id")
    readonly_fields = ("is_vectorized",)

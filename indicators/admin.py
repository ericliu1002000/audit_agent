from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse

from .models import FundUsage, Indicator
from .services import export_indicators_excel, full_sync_from_excel
from .tasks import sync_all_unvectorized
from regions.models import Province


class ActiveStatusFilter(admin.SimpleListFilter):
    title = "是否启用"
    parameter_name = "is_active"

    def lookups(self, request, model_admin):
        return (
            ("1", "是"),
            ("0", "否"),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value == "0":
            return queryset.filter(is_active=False)
        if value == "all":
            return queryset
        return queryset.filter(is_active=True)

    def choices(self, changelist):
        value = self.value()
        for lookup, title in self.lookup_choices:
            yield {
                "selected": value == lookup or (value is None and lookup == "1"),
                "query_string": changelist.get_query_string(
                    {self.parameter_name: lookup}
                ),
                "display": title,
            }
        yield {
            "selected": value == "all",
            "query_string": changelist.get_query_string(
                {self.parameter_name: "all"}
            ),
            "display": "全部",
        }


class IndicatorInline(admin.TabularInline):
    """允许在 FundUsage 页面内直接维护指标。"""

    model = Indicator
    extra = 0
    fields = (
        "business_code",
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

    list_display = ("name", "province", "source_file", "indicator_count")
    search_fields = ("name", "source_file", "province__name", "province__code")
    list_filter = ("province",)
    list_per_page = 30
    inlines = (IndicatorInline,)

    @admin.display(description="指标数量")
    def indicator_count(self, obj):
        return obj.indicators.count()

    def save_formset(self, request, form, formset, change):
        """在内联中保存指标时，重置向量化状态并触发同步任务。"""

        instances = formset.save(commit=False)
        needs_vector_sync = False

        for obj in instances:
            if isinstance(obj, Indicator):
                obj.is_vectorized = False
                obj.is_active = True
                needs_vector_sync = True
            obj.save()

        formset.save_m2m()

        for obj in formset.deleted_objects:
            if isinstance(obj, Indicator) and obj.pk:
                Indicator.all_objects.filter(pk=obj.pk).update(is_active=False)
                needs_vector_sync = True

        if needs_vector_sync:
            sync_all_unvectorized.delay()


@admin.register(Indicator)
class IndicatorAdmin(admin.ModelAdmin):
    """指标管理，支持自定义导入/导出和软删除。"""

    change_list_template = "admin/indicators/indicator/change_list.html"
    list_display = (
        "business_code",
        "fund_usage",
        "level_1",
        "level_2",
        "level_3",
        "province_id",
        "nature",
        "unit",
        "explanation",
        "is_vectorized",
        "is_active",
        "source_tag",
    )
    list_filter = (
        "is_vectorized",
        ActiveStatusFilter,
        "source_tag",
        "province_id",
        "fund_usage",
    )
    search_fields = (
        "business_code",
        "level_1",
        "level_2",
        "level_3",
        "explanation",
        "province_id__name",
        "province_id__code",
    )
    list_select_related = ("fund_usage", "province_id")
    readonly_fields = ("is_vectorized",)
    list_per_page = 30

    def get_queryset(self, request):
        qs = self.model.all_objects.all()
        qs = qs.order_by("fund_usage__name", "level_1", "level_2", "level_3")
        qs = qs.select_related(*self.list_select_related)
        ordering = self.get_ordering(request)
        if ordering:
            qs = qs.order_by(*ordering)
        return qs

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "export/",
                self.admin_site.admin_view(self.export_view),
                name="indicators_indicator_export",
            ),
            path(
                "import/",
                self.admin_site.admin_view(self.import_view),
                name="indicators_indicator_import",
            ),
        ]
        return custom_urls + urls

    def export_view(self, request):
        if not self.has_view_permission(request):
            raise PermissionDenied

        changelist = self.get_changelist_instance(request)
        queryset = changelist.get_queryset(request)

        province_name = "全部省份"
        province_id = request.GET.get("province_id__id__exact")
        if province_id:
            province = Province.objects.filter(id=province_id).first()
            if province:
                province_name = province.name
        return export_indicators_excel(queryset, province_name)

    def import_view(self, request):
        if not self.has_change_permission(request):
            raise PermissionDenied

        changelist_url = reverse("admin:indicators_indicator_changelist")
        if request.method == "POST":
            excel_file = request.FILES.get("excel_file")
            source_tag = request.POST.get("source_tag", "").strip()

            if not excel_file:
                messages.error(request, "请提供 Excel 文件")
                return redirect(changelist_url)

            try:
                result = full_sync_from_excel(excel_file, source_tag or "")
            except ValidationError as exc:
                messages.error(request, f"导入失败：{'；'.join(exc.messages)}")
                return redirect(changelist_url)
            except Exception as exc:  # pragma: no cover - unexpected path
                messages.error(request, f"导入失败：{exc}")
                return redirect(changelist_url)

            messages.success(
                request,
                f"导入完成：创建 {result['created']} 条，更新 {result['updated']} 条，软删除 {result['soft_deleted']} 条",
            )
            if result["created"] or result["updated"] or result["soft_deleted"]:
                sync_all_unvectorized.delay()
                messages.info(request, "已派发向量化同步任务，稍后自动更新向量状态。")
            return redirect(changelist_url)

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "导入指标",
        }
        return TemplateResponse(
            request, "admin/indicators/indicator/import.html", context
        )

    def changelist_view(self, request, extra_context=None):
        export_url = reverse("admin:indicators_indicator_export")
        if request.GET:
            export_url = f"{export_url}?{request.GET.urlencode()}"
        extra_context = extra_context or {}
        extra_context["export_url_with_filters"] = export_url
        return super().changelist_view(request, extra_context=extra_context)

    def save_model(self, request, obj, form, change):
        """保存指标时，重置向量化标记并触发同步。"""

        obj.is_vectorized = False
        obj.is_active = True
        super().save_model(request, obj, form, change)
        sync_all_unvectorized.delay()

    def delete_model(self, request, obj):
        """删除指标时执行软删除并触发同步。"""

        Indicator.all_objects.filter(pk=obj.pk).update(is_active=False)
        sync_all_unvectorized.delay()

    def delete_queryset(self, request, queryset):
        """批量删除指标时执行软删除并触发同步。"""

        updated = Indicator.all_objects.filter(pk__in=queryset.values_list("pk", flat=True)).update(
            is_active=False
        )
        if updated:
            sync_all_unvectorized.delay()

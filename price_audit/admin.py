"""价格审核后台管理。"""

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse

from price_audit.forms import GovernmentPriceImportForm
from price_audit.models import GovernmentPriceBatch, GovernmentPriceItem
from price_audit.services import government_price_service
from price_audit.tasks import dispatch_vectorize_government_price_batch


class GovernmentPriceItemInline(admin.TabularInline):
    """批次详情页中展示明细行。"""

    model = GovernmentPriceItem
    extra = 0
    can_delete = False
    fields = (
        "row_no",
        "material_name_raw",
        "spec_model_raw",
        "unit_raw",
        "benchmark_price",
        "price_min",
        "price_max",
        "is_tax_included",
    )
    readonly_fields = fields
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(GovernmentPriceBatch)
class GovernmentPriceBatchAdmin(admin.ModelAdmin):
    """政府标准价批次管理，提供模板下载与 Excel 导入入口。"""

    change_list_template = "admin/price_audit/governmentpricebatch/change_list.html"
    list_display = (
        "id",
        "region_name",
        "year",
        "is_active",
        "vector_status",
        "vector_progress",
        "total_rows",
        "success_rows",
        "vector_success",
        "vector_failed",
        "uploaded_by",
        "created_at",
        "source_filename",
    )
    list_filter = ("region_name", "year", "is_active", "vector_status")
    search_fields = ("region_name", "source_filename", "remark")
    actions = ("requeue_vectorization",)
    readonly_fields = (
        "region_name",
        "year",
        "is_active",
        "source_file",
        "source_filename",
        "uploaded_by",
        "replaced_batch",
        "total_rows",
        "success_rows",
        "vector_status",
        "vector_task_id",
        "vector_queued_at",
        "vector_started_at",
        "vector_total",
        "vector_success",
        "vector_failed",
        "vectorized_at",
        "last_error",
        "remark",
        "template_version",
        "deactivated_at",
        "created_at",
        "updated_at",
    )
    list_per_page = 30
    inlines = (GovernmentPriceItemInline,)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "download-template/",
                self.admin_site.admin_view(self.download_template_view),
                name="price_audit_governmentpricebatch_download_template",
            ),
            path(
                "import-prices/",
                self.admin_site.admin_view(self.import_prices_view),
                name="price_audit_governmentpricebatch_import_prices",
            ),
        ]
        return custom_urls + urls

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="向量进度")
    def vector_progress(self, obj):
        """展示标准价向量化当前进度。"""

        return f"{obj.vector_success + obj.vector_failed}/{obj.vector_total}"

    def download_template_view(self, request):
        """下载政府标准价导入模板。"""

        if not self.has_view_permission(request):
            raise PermissionDenied

        content = government_price_service.build_template_content()
        response = HttpResponse(
            content,
            content_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )
        response["Content-Disposition"] = (
            'attachment; filename="government_price_template_v1.xlsx"'
        )
        return response

    def import_prices_view(self, request):
        """在 admin 后台导入政府标准价 Excel。"""

        if not self.has_change_permission(request):
            raise PermissionDenied

        changelist_url = reverse("admin:price_audit_governmentpricebatch_changelist")
        if request.method == "POST":
            form = GovernmentPriceImportForm(request.POST, request.FILES)
            if form.is_valid():
                cleaned = form.cleaned_data
                try:
                    result = government_price_service.import_excel(
                        cleaned["excel_file"],
                        region_name=cleaned["region_name"],
                        year=cleaned["year"],
                        uploaded_by=request.user,
                        remark=cleaned["remark"],
                        default_tax_included=cleaned["default_tax_included"],
                    )
                except ValueError as exc:
                    messages.error(request, f"导入失败：{exc}")
                    return redirect(changelist_url)
                except Exception as exc:  # pragma: no cover
                    messages.error(request, f"导入失败：{exc}")
                    return redirect(changelist_url)

                messages.success(
                    request,
                    (
                        f"导入完成：同步批次 #{result.batch.id}，解析 {result.parsed_rows} 行，"
                        f"新增 {result.created_rows} 行，更新 {result.updated_rows} 行，"
                        f"删除 {result.deleted_rows} 行。"
                    ),
                )
                if result.vector_task_dispatched:
                    messages.info(
                        request,
                        "已提交标准价向量化任务。请确保 Celery worker 已启动，批次状态会自动更新。",
                    )
                return redirect(changelist_url)
        else:
            form = GovernmentPriceImportForm()

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "导入政府标准价",
            "form": form,
            "template_download_url": reverse(
                "admin:price_audit_governmentpricebatch_download_template"
            ),
        }
        return TemplateResponse(
            request,
            "admin/price_audit/governmentpricebatch/import_prices.html",
            context,
        )

    def changelist_view(self, request, extra_context=None):
        """在批次列表页显示上传和模板下载入口。"""

        extra_context = extra_context or {}
        extra_context["import_prices_url"] = reverse(
            "admin:price_audit_governmentpricebatch_import_prices"
        )
        extra_context["download_template_url"] = reverse(
            "admin:price_audit_governmentpricebatch_download_template"
        )
        return super().changelist_view(request, extra_context=extra_context)

    @admin.action(description="重新提交向量化任务")
    def requeue_vectorization(self, request, queryset):
        """对选中的批次重新提交 Celery 向量化任务。"""

        selected = list(queryset)
        for batch in selected:
            dispatch_vectorize_government_price_batch(batch.id)
        self.message_user(
            request,
            f"已重新提交 {len(selected)} 个批次的向量化任务。",
            level=messages.SUCCESS,
        )


@admin.register(GovernmentPriceItem)
class GovernmentPriceItemAdmin(admin.ModelAdmin):
    """政府标准价明细查看页。"""

    list_display = (
        "id",
        "region_name",
        "year",
        "material_name_raw",
        "spec_model_raw",
        "unit_raw",
        "benchmark_price",
        "price_min",
        "price_max",
        "is_tax_included",
        "is_vectorized",
        "batch",
    )
    list_filter = ("batch__region_name", "batch__year", "batch__is_active", "is_tax_included")
    search_fields = ("material_name_raw", "spec_model_raw", "unit_raw", "batch__region_name")
    list_select_related = ("batch",)
    list_per_page = 50
    readonly_fields = (
        "batch",
        "row_no",
        "material_name_raw",
        "material_name_normalized",
        "spec_model_raw",
        "spec_model_normalized",
        "unit_raw",
        "unit_normalized",
        "benchmark_price",
        "price_min",
        "price_max",
        "description",
        "is_tax_included",
        "embedding_text",
        "is_vectorized",
        "raw_row_data",
        "created_at",
    )

    @admin.display(description="地区")
    def region_name(self, obj):
        return obj.batch.region_name

    @admin.display(description="年份")
    def year(self, obj):
        return obj.batch.year

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

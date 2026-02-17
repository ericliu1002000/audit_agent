from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse

from budget_audit.models import BudgetPriceItem
from budget_audit.services import import_standard_price_excel


@admin.register(BudgetPriceItem)
class BudgetPriceItemAdmin(admin.ModelAdmin):
    change_list_template = "admin/budget_audit/budgetpriceitem/change_list.html"
    list_display = (
        "material_name",
        "spec_model",
        "unit",
        "base_price",
        "price_low",
        "price_high",
        "is_tax_included",
        "region",
        "publish_month",
        "updated_at",
    )
    list_filter = ("region", "publish_month", "is_tax_included", "unit")
    search_fields = ("material_name", "spec_model", "unit", "region", "publish_month")
    list_per_page = 30

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "import-standard/",
                self.admin_site.admin_view(self.import_standard_view),
                name="budget_audit_budgetpriceitem_import_standard",
            ),
        ]
        return custom_urls + urls

    def import_standard_view(self, request):
        if not self.has_change_permission(request):
            raise PermissionDenied

        changelist_url = reverse("admin:budget_audit_budgetpriceitem_changelist")
        if request.method == "POST":
            excel_file = request.FILES.get("excel_file")
            region = (request.POST.get("region") or "").strip()
            publish_month = (request.POST.get("publish_month") or "").strip()
            replace_existing = request.POST.get("replace_existing") == "on"
            default_tax_included = request.POST.get("default_tax_included") == "on"

            if not excel_file:
                messages.error(request, "请上传标准价格 Excel 文件。")
                return redirect(changelist_url)

            try:
                result = import_standard_price_excel(
                    excel_file,
                    region=region,
                    publish_month=publish_month,
                    replace_existing=replace_existing,
                    default_tax_included=default_tax_included,
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
                    f"导入完成：解析 {result['parsed']} 条，入库 {result['created']} 条，"
                    f"删除旧数据 {result['deleted']} 条，向量索引成功 {result['indexed']} 条。"
                ),
            )
            if result["index_failed"]:
                messages.warning(
                    request,
                    f"有 {result['index_failed']} 条向量构建失败，请检查嵌入服务配置。",
                )
            return redirect(changelist_url)

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "导入政府标准价格",
        }
        return TemplateResponse(
            request, "admin/budget_audit/budgetpriceitem/import_standard.html", context
        )

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["import_standard_url"] = reverse(
            "admin:budget_audit_budgetpriceitem_import_standard"
        )
        return super().changelist_view(request, extra_context=extra_context)

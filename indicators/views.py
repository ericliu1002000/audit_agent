from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.generic import TemplateView

from indicators.services import get_fund_usage_recommendations


class FundUsageRecommendationPage(LoginRequiredMixin, TemplateView):
    """展示资金用途智能推荐页面."""

    template_name = "indicators/fund_usage_recommendation.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        province_param = (self.request.GET.get("province") or "").strip()
        context["default_province_id"] = province_param if province_param.isdigit() else ""
        return context


@require_http_methods(["GET"])
def fund_usage_recommendations(request):
    """API: 根据用户查询推荐资金用途."""

    user_query = (request.GET.get("query") or "").strip()
    if not user_query:
        return JsonResponse(
            {"error": "query 参数不能为空"}, status=400, json_dumps_params={"ensure_ascii": False}
        )

    province_param = request.GET.get("province_id")
    try:
        province_id = int(province_param) if province_param else None
    except ValueError:
        return JsonResponse(
            {"error": "province_id 必须为整数"},
            status=400,
            json_dumps_params={"ensure_ascii": False},
        )

    try:
        recommendations = get_fund_usage_recommendations(user_query, province_id=province_id)
    except Exception as exc:  # pragma: no cover - 依赖外部服务
        return JsonResponse(
            {"error": f"服务异常：{exc}"},
            status=500,
            json_dumps_params={"ensure_ascii": False},
        )

    return JsonResponse(
        {"results": recommendations},
        json_dumps_params={"ensure_ascii": False},
    )

import os
from uuid import uuid4

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.cache import cache
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.views.generic import TemplateView

from indicators.services import get_fund_usage_recommendations
from indicators.services.check_indicator_excel.tasks import run_audit_task


class FundUsageRecommendationPage(LoginRequiredMixin, TemplateView):
    """展示资金用途智能推荐页面."""

    template_name = "indicators/fund_usage_recommendation.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        province_param = (self.request.GET.get("province") or "").strip()
        context["default_province_id"] = province_param if province_param.isdigit() else ""
        return context


class AuditIndicatorPage(LoginRequiredMixin, TemplateView):
    """上传并查看指标审核结果的前端页面."""

    template_name = "indicators/audit_indicator_table.html"


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


AUDIT_TASK_TTL = 60 * 60  # 审核任务状态在缓存中保留 24 小时


def _audit_cache_key(task_id: str) -> str:
    """构造审核任务状态缓存键，确保与 Celery 任务使用的格式一致。"""

    return f"audit_task_{task_id}"


def _init_task_status(task_id: str) -> None:
    """初始化任务状态，标记为排队中并写入首条日志。"""

    cache.set(
        _audit_cache_key(task_id),
        {
            "status": "pending",
            "logs": [{"status": "pending", "message": "任务排队中..."}],
        },
        timeout=AUDIT_TASK_TTL,
    )


def _save_uploaded_file(uploaded_file) -> str:
    """将上传的 Excel 保存到 MEDIA_ROOT 指定目录并返回绝对路径。"""

    today = timezone.now()
    relative_dir = os.path.join(
        "uploads",
        "indicators",
        today.strftime("%Y"),
        today.strftime("%m"),
        today.strftime("%d"),
    )
    target_dir = os.path.join(settings.MEDIA_ROOT, relative_dir)
    os.makedirs(target_dir, exist_ok=True)

    safe_name = os.path.basename(uploaded_file.name)
    filename = f"{uuid4().hex}_{safe_name}"
    full_path = os.path.join(target_dir, filename)

    with open(full_path, "wb+") as destination:
        for chunk in uploaded_file.chunks():
            destination.write(chunk)

    return full_path


@require_http_methods(["POST"])
def audit_upload(request):
    """上传 Excel，落盘后派发异步审核任务并返回 task_id。"""

    uploaded_file = request.FILES.get("file") or request.FILES.get("excel_file")
    if not uploaded_file:
        return JsonResponse(
            {"error": "请上传 Excel 文件"},
            status=400,
            json_dumps_params={"ensure_ascii": False},
        )

    task_id = uuid4().hex
    file_path = _save_uploaded_file(uploaded_file)
    _init_task_status(task_id)

    run_audit_task.delay(file_path, task_id)

    return JsonResponse({"task_id": task_id}, json_dumps_params={"ensure_ascii": False})


@require_http_methods(["GET"])
def audit_status(request, task_id: str):
    """查询审核任务的实时状态、日志与结果。"""

    data = cache.get(_audit_cache_key(task_id))
    if not data:
        return JsonResponse(
            {"error": "任务不存在或已过期"},
            status=404,
            json_dumps_params={"ensure_ascii": False},
        )

    return JsonResponse(data, json_dumps_params={"ensure_ascii": False})

"""API 路径下的 CSRF 失败处理。"""

from django.http import JsonResponse
from django.views.csrf import csrf_failure as default_csrf_failure


def csrf_failure(request, reason="", template_name="403_csrf.html"):
    """为 `/api/` 路径返回 JSON 版 CSRF 错误，其余路径沿用 Django 默认页面。"""

    if request.path.startswith("/api/"):
        response = JsonResponse(
            {
                "success": False,
                "error": {
                    "code": "csrf_failed",
                    "message": "CSRF 校验失败，请刷新页面后重试。",
                    "details": {"reason": reason},
                },
            },
            status=403,
            json_dumps_params={"ensure_ascii": False},
        )
        response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response["Pragma"] = "no-cache"
        return response
    return default_csrf_failure(request, reason=reason, template_name=template_name)

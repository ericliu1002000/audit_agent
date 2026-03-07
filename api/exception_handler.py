"""DRF 全局异常处理，统一输出项目约定的错误结构。"""

from __future__ import annotations

from typing import Any

from rest_framework.exceptions import AuthenticationFailed, NotAuthenticated, PermissionDenied, ValidationError
from rest_framework.views import exception_handler

from api.responses import apply_no_store_headers


def _extract_validation_fields(data: Any) -> dict[str, list[str]] | None:
    """从 DRF 校验错误中提取字段错误，转换成前端稳定可消费的结构。"""

    if not isinstance(data, dict):
        return None

    fields: dict[str, list[str]] = {}
    for key, value in data.items():
        if key == "detail":
            continue
        if isinstance(value, list):
            fields[key] = [str(item) for item in value]
        else:
            fields[key] = [str(value)]
    return fields or None


def _first_field_message(fields: dict[str, list[str]] | None) -> str | None:
    """取第一条字段错误，作为接口的主错误消息。"""

    if not fields:
        return None
    for messages in fields.values():
        if messages:
            return messages[0]
    return None


def custom_exception_handler(exc, context):
    """包装 DRF 默认异常响应，统一为 `{success: false, error: ...}`。"""

    response = exception_handler(exc, context)
    if response is None:
        return None

    code = "api_error"
    message = "请求失败。"
    fields = None

    if isinstance(exc, (NotAuthenticated, AuthenticationFailed)):
        code = "authentication_required"
        message = str(response.data.get("detail", "未登录或登录已失效。"))
    elif isinstance(exc, PermissionDenied):
        code = "permission_denied"
        message = str(response.data.get("detail", "无权访问此资源。"))
    elif isinstance(exc, ValidationError):
        code = "validation_error"
        fields = _extract_validation_fields(response.data)
        message = _first_field_message(fields) or "请求参数校验失败。"
    elif isinstance(response.data, dict) and "detail" in response.data:
        message = str(response.data["detail"])

    response.data = {
        "success": False,
        "error": {
            "code": code,
            "message": message,
        },
    }
    if fields:
        response.data["error"]["fields"] = fields
    apply_no_store_headers(response)
    return response

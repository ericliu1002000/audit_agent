"""统一 API 成功/失败响应封装。"""

from __future__ import annotations

from typing import Any

from rest_framework.response import Response


def apply_no_store_headers(response: Response) -> Response:
    """给敏感响应添加禁止缓存头，避免浏览器缓存认证类数据。"""

    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    return response


def success_response(
    *,
    data: Any | None = None,
    message: str | None = None,
    meta: dict[str, Any] | None = None,
    status: int = 200,
    no_store: bool = False,
) -> Response:
    """构造统一成功响应。

    参数:
    - `data`: 业务数据
    - `message`: 给前端展示的简短提示
    - `meta`: 分页等附加信息
    - `status`: HTTP 状态码
    - `no_store`: 是否附加禁止缓存头
    """

    payload: dict[str, Any] = {"success": True}
    if message is not None:
        payload["message"] = message
    if data is not None:
        payload["data"] = data
    if meta:
        payload["meta"] = meta

    response = Response(payload, status=status)
    if no_store:
        apply_no_store_headers(response)
    return response


def error_response(
    code: str,
    message: str,
    *,
    status: int,
    fields: dict[str, list[str]] | None = None,
    details: dict[str, Any] | None = None,
    no_store: bool = False,
) -> Response:
    """构造统一失败响应。

    参数:
    - `code`: 稳定错误码
    - `message`: 错误描述
    - `fields`: 表单/序列化器字段错误
    - `details`: 额外调试信息
    - `no_store`: 是否附加禁止缓存头
    """

    payload: dict[str, Any] = {
        "success": False,
        "error": {
            "code": code,
            "message": message,
        },
    }
    if fields:
        payload["error"]["fields"] = fields
    if details:
        payload["error"]["details"] = details

    response = Response(payload, status=status)
    if no_store:
        apply_no_store_headers(response)
    return response

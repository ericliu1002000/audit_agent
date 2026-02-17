from __future__ import annotations

import json
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from budget_audit.services.match_service import audit_single_item
from budget_audit.services.normalization import normalize_tax_flag, parse_decimal


def _parse_tax_flag(value, *, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    return normalize_tax_flag(value, default=default)


@login_required
@require_http_methods(["POST"])
def api_budget_audit(request):
    """预算审核 API：接收单条输入，返回 DeepSeek 格式化结论 + 候选项。"""

    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse(
            {"error": "请求体必须是合法的 JSON。"},
            status=400,
            json_dumps_params={"ensure_ascii": False},
        )

    material_name = (payload.get("material_name") or "").strip()
    spec_model = (payload.get("spec_model") or "").strip()
    unit = (payload.get("unit") or "").strip()

    vendor_price_raw = payload.get("vendor_price")
    vendor_price: Decimal | None = parse_decimal(vendor_price_raw)
    is_tax_included = _parse_tax_flag(payload.get("is_tax_included"), default=True)

    if not material_name:
        return JsonResponse(
            {"error": "商品/材料名称不能为空。"},
            status=400,
            json_dumps_params={"ensure_ascii": False},
        )
    if vendor_price is None:
        return JsonResponse(
            {"error": "价格不能为空或格式不正确。"},
            status=400,
            json_dumps_params={"ensure_ascii": False},
        )

    try:
        result = audit_single_item(
            material_name=material_name,
            spec_model=spec_model,
            unit=unit,
            vendor_price=vendor_price,
            is_tax_included=is_tax_included,
            top_k=10,
        )
    except ValueError as exc:
        return JsonResponse(
            {"error": str(exc)},
            status=400,
            json_dumps_params={"ensure_ascii": False},
        )
    except Exception as exc:  # pragma: no cover
        return JsonResponse(
            {"error": f"预算审核失败：{exc}"},
            status=500,
            json_dumps_params={"ensure_ascii": False},
        )

    return JsonResponse(result, json_dumps_params={"ensure_ascii": False})


from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from .models import Province
from .services import get_cities_for_province, list_provinces


@require_http_methods(["GET"])
def province_list(request):
    """API: 返回全部省份."""

    provinces = [
        {"id": province.id, "name": province.name, "code": province.code}
        for province in list_provinces()
    ]
    return JsonResponse(
        {"results": provinces},
        json_dumps_params={"ensure_ascii": False},
    )


@require_http_methods(["GET"])
def province_cities(request, province_id: int):
    """API: 返回指定省份的所有城市."""

    province = get_object_or_404(
        Province.objects.prefetch_related("cities"),
        pk=province_id,
    )
    cities = [
        {"id": city.id, "name": city.name, "code": city.code}
        for city in get_cities_for_province(province)
    ]
    return JsonResponse(
        {
            "province": {"id": province.id, "name": province.name, "code": province.code},
            "results": cities,
        },
        json_dumps_params={"ensure_ascii": False},
    )

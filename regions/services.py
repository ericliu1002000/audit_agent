from typing import Iterable

from .models import Province


def list_provinces() -> Iterable[Province]:
    """Return all provinces ordered by id."""
    return Province.objects.all().order_by('id')


def list_provinces_with_cities() -> Iterable[Province]:
    """Return provinces with prefetched cities for convenient access."""
    return Province.objects.prefetch_related('cities').order_by('id')


def get_cities_for_province(province: Province):
    """Convenience helper that exposes a province's related cities."""
    return province.cities.all().order_by('id')

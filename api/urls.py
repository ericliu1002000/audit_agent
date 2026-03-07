"""API 顶层路由。

这里统一暴露 schema、Swagger/ReDoc 文档，以及各版本 API 路由。
"""

from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

app_name = "api"

urlpatterns = [
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "docs/swagger/",
        SpectacularSwaggerView.as_view(url_name="api:schema"),
        name="docs-swagger",
    ),
    path(
        "docs/redoc/",
        SpectacularRedocView.as_view(url_name="api:schema"),
        name="docs-redoc",
    ),
    path(
        "v1/",
        include(("api.v1.urls", "api_v1"), namespace="v1"),
    ),
]

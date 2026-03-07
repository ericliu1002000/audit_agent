"""API 应用配置。"""

from django.apps import AppConfig


class ApiConfig(AppConfig):
    """注册 API app，并在启动时挂载文档扩展。"""

    default_auto_field = "django.db.models.BigAutoField"
    name = "api"
    verbose_name = "API"

    def ready(self):
        """加载 drf-spectacular 扩展，确保自定义认证写入 OpenAPI 文档。"""

        from . import schema  # noqa: F401

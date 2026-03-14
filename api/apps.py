"""API 应用配置。"""

import logging
import sys

from django.apps import AppConfig
from django.core.management import call_command


logger = logging.getLogger(__name__)


class ApiConfig(AppConfig):
    """注册 API app，并在启动时挂载文档扩展。"""

    default_auto_field = "django.db.models.BigAutoField"
    name = "api"
    verbose_name = "API"

    def ready(self):
        """加载 drf-spectacular 扩展，确保自定义认证写入 OpenAPI 文档。"""

        from . import schema  # noqa: F401

        if len(sys.argv) > 1 and sys.argv[1] == "ensure_vector_collections":
            return

        try:
            call_command("ensure_vector_collections")
        except Exception as exc:  # pragma: no cover - depends on Milvus runtime
            logger.warning(
                "Failed to initialize Milvus collections during Django startup: %s",
                exc,
                exc_info=True,
            )

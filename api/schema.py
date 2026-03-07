"""OpenAPI 文档扩展。"""

from django.conf import settings

from drf_spectacular.extensions import OpenApiAuthenticationExtension


class ApiSessionScheme(OpenApiAuthenticationExtension):
    """为自定义 Session 认证声明 OpenAPI 安全方案。"""

    target_class = "api.authentication.ApiSessionAuthentication"
    name = "cookieAuth"

    def get_security_definition(self, auto_schema):
        """告诉文档生成器：认证依赖 session cookie，并需要配合 CSRF 头。"""

        return {
            "type": "apiKey",
            "in": "cookie",
            "name": settings.SESSION_COOKIE_NAME,
            "description": (
                "Django session cookie authentication. Unsafe methods must also send "
                "the X-CSRFToken header after fetching /api/v1/auth/csrf/."
            ),
        }

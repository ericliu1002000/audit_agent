"""API 认证相关扩展。"""

from rest_framework.authentication import SessionAuthentication


class ApiSessionAuthentication(SessionAuthentication):
    """API 专用 Session 认证类。

    Django/DRF 默认的 SessionAuthentication 在未登录时更容易落成 403。
    这里补一个 authenticate header，让未登录请求统一返回 401，
    便于 React 前端按“需要登录”处理。
    """

    def authenticate_header(self, request):
        """声明认证头名称，触发 DRF 对未登录请求返回 401。"""

        return "Session"

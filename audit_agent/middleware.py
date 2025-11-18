import logging
import time
from urllib.parse import unquote

from django.utils.deprecation import MiddlewareMixin


logger = logging.getLogger("audit_agent.request")


class RequestLoggingMiddleware(MiddlewareMixin):
    def process_request(self, request):
        request._start_time = time.time()

    def process_response(self, request, response):
        try:
            duration_ms = None
            if hasattr(request, "_start_time"):
                duration_ms = int((time.time() - request._start_time) * 1000)

            user = getattr(request, "user", None)
            if user and user.is_authenticated:
                user_repr = f"{user.id}:{user.username}"
            else:
                user_repr = "anonymous"

            raw_path = request.path
            raw_query = request.META.get("QUERY_STRING", "")
            path = unquote(raw_path)
            if raw_query:
                full_path = f"{path}?{unquote(raw_query)}"
            else:
                full_path = path

            msg = f"{request.method} {full_path} status={response.status_code} user={user_repr}"
            if duration_ms is not None:
                msg += f" duration_ms={duration_ms}"

            logger.info(msg)
        except Exception:
            # 不能影响正常请求流程
            logging.getLogger("audit_agent").exception(
                "RequestLoggingMiddleware failed"
            )
        return response

import logging
import time
import uuid
from urllib.parse import unquote

from django.utils.deprecation import MiddlewareMixin


logger = logging.getLogger("audit_agent.request")


class RequestLoggingMiddleware(MiddlewareMixin):
    def process_request(self, request):
        request._start_time = time.time()

    def process_response(self, request, response):
        try:
            duration = None
            if hasattr(request, "_start_time"):
                duration = time.time() - request._start_time

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

            remote_addr = request.META.get("REMOTE_ADDR") or ""
            real_ip = (
                request.META.get("HTTP_X_REAL_IP")
                or request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
                or remote_addr
            )

            protocol = request.META.get("SERVER_PROTOCOL", "HTTP/1.1")

            content_length = response.get("Content-Length")
            if content_length is None:
                try:
                    content_length = str(len(response.content))
                except Exception:
                    content_length = ""

            if duration is not None:
                request_time = f"{duration:.3f}"
            else:
                request_time = ""

            request_id = (
                request.META.get("HTTP_X_REQUEST_ID") or str(uuid.uuid4())
            )
            response["X-Request-ID"] = request_id

            data = {
                "remote_addr": remote_addr,
                "real_ip": real_ip,
                "request": f"{request.method} {full_path}",
                "status": str(response.status_code),
                "body_bytes_sent": content_length,
                "upstream_response_time": request_time,
                "http_user_agent": request.META.get("HTTP_USER_AGENT", ""),
                "request_id": request_id,
                "user": user_repr,
                "request_time": request_time,
            }

            logger.info(data)
        except Exception:
            # 不能影响正常请求流程
            logging.getLogger("audit_agent").exception(
                "RequestLoggingMiddleware failed"
            )
        return response

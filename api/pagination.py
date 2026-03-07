"""API 分页配置。"""

from rest_framework.pagination import PageNumberPagination

from api.responses import success_response


class StandardResultsSetPagination(PageNumberPagination):
    """统一分页输出格式，兼容 React 列表页的常见元信息需求。"""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data):
        """返回带 `items + pagination meta` 的统一成功响应。"""

        pagination = {
            "page": self.page.number,
            "page_size": self.get_page_size(self.request) or self.page_size,
            "total": self.page.paginator.count,
            "total_pages": self.page.paginator.num_pages,
            "has_next": self.page.has_next(),
            "has_previous": self.page.has_previous(),
        }
        return success_response(
            data={"items": data},
            meta={"pagination": pagination},
        )

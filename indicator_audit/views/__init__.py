"""
indicator_audit.views
======================

按职责拆分的视图模块聚合入口。

- 页面类视图统一放在 pages.py 中，例如：
  - AuditIndicatorPage：单文件智能审核页面 `/indicator_audit/audit/indicator/`
  - AuditBatchPage：批量审核页面 `/indicator_audit/audit/batch/`
  - MyAuditFileListPage：我的审核记录页面 `/indicator_audit/my/files/`
  - AuditFileDetailPage：单文件历史报告详情 `/indicator_audit/file/<pk>/`
  - AuditBatchDetailPage：批次详情页（占位） `/indicator_audit/batch/<pk>/`

- JSON / 文件下载 API 统一放在 api.py 中，例如：
  - audit_upload / audit_status：单文件审核上传与轮询接口
  - api_create_batch / api_batch_upload / api_batch_progress：批次创建与多文件上传、进度查询
  - export_audit_file_markdown / export_audit_file_pdf：报告导出接口
"""

from .pages import (
    AuditIndicatorPage,
    AuditBatchPage,
    MyAuditFileListPage,
    AuditFileDetailPage,
    AuditBatchDetailPage,
)
from .api import (
    audit_upload,
    audit_status,
    api_create_batch,
    api_batch_upload,
    api_batch_progress,
    api_batch_summary,
    export_audit_file_markdown,
    export_audit_file_pdf,
)

__all__ = [
    # 页面类视图
    "AuditIndicatorPage",
    "AuditBatchPage",
    "MyAuditFileListPage",
    "AuditFileDetailPage",
    "AuditBatchDetailPage",
    # API 视图
    "audit_upload",
    "audit_status",
    "api_create_batch",
    "api_batch_upload",
    "api_batch_progress",
    "api_batch_summary",
    "export_audit_file_markdown",
    "export_audit_file_pdf",
]

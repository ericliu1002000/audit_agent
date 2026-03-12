"""价格审核模型公共工具。"""

from __future__ import annotations

import os
from uuid import uuid4


def _safe_filename(filename: str) -> str:
    """清洗上传文件名，避免路径注入并保留后缀。"""

    base = os.path.basename(filename or "")
    if not base:
        return "upload.xlsx"
    return base.replace("/", "_")


def government_price_source_upload_to(instance, filename):
    """生成政府标准价源文件上传路径。

    功能说明:
        按“年份/地区/原始文件名”的层级组织上传文件，便于后台追溯来源文件。
    使用示例:
        path = government_price_source_upload_to(batch, "prices.xlsx")
    输入参数:
        instance: `GovernmentPriceBatch` 实例。
        filename: 原始上传文件名。
    输出参数:
        str: 形如 `price_audit/government_prices/2026/天津/prices.xlsx` 的相对路径。
    """

    year = instance.year or "unknown"
    region = (instance.region_name or "unknown").strip().replace("/", "_")
    return f"price_audit/government_prices/{year}/{region}/{_safe_filename(filename)}"


def price_audit_submission_source_upload_to(instance, filename):
    """生成送审表源文件上传路径。"""

    submission_id = getattr(instance, "id", None) or "pending"
    return (
        f"price_audit/submissions/{submission_id}/source/"
        f"{uuid4().hex}_{_safe_filename(filename)}"
    )


def price_audit_submission_audited_excel_upload_to(instance, filename):
    """生成审核表导出文件上传路径。"""

    submission_id = getattr(instance, "id", None) or "pending"
    return (
        f"price_audit/submissions/{submission_id}/audited/"
        f"{uuid4().hex}_{_safe_filename(filename)}"
    )

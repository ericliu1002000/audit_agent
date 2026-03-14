"""价格送审单创建与查询服务。"""

from __future__ import annotations

from pathlib import Path

from django.db import transaction

from price_audit.models import GovernmentPriceBatch, PriceAuditSubmission
from price_audit.tasks import dispatch_process_price_audit_submission


def get_default_price_batch() -> GovernmentPriceBatch:
    """返回当前可用于价格审核的标准价批次。"""

    batch = (
        GovernmentPriceBatch.objects.filter(
            is_active=True,
            vector_status=GovernmentPriceBatch.VectorStatus.ACTIVE,
        )
        .order_by("-year", "-created_at")
        .first()
    )
    if batch is None:
        raise ValueError("暂无可用的政府标准价批次，请先导入并完成向量化。")
    return batch


def create_submission_from_upload(
    uploaded_file,
    *,
    created_by=None,
    exhibition_center_id: int,
    project_nature: int,
) -> PriceAuditSubmission:
    """创建送审单并提交异步审核任务。"""

    filename = (uploaded_file.name or "").strip()
    if not filename.lower().endswith(".xlsx"):
        raise ValueError("仅支持上传 .xlsx 格式文件。")

    batch = get_default_price_batch()
    project_name = Path(filename).stem
    submission = PriceAuditSubmission.objects.create(
        created_by=created_by,
        price_batch=batch,
        original_filename=filename,
        project_name=project_name,
        exhibition_center_id=exhibition_center_id,
        project_nature=project_nature,
        current_step=PriceAuditSubmission.Step.QUEUED,
        progress_percent=0,
        total_rows=0,
        processed_rows=0,
        failed_rows=0,
        current_message="送审表上传成功，等待开始审核。",
    )
    submission.source_file.save(filename, uploaded_file, save=True)

    transaction.on_commit(lambda: dispatch_process_price_audit_submission(submission.id))
    return submission

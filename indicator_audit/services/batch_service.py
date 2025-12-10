from __future__ import annotations

from typing import Iterable, Dict, Any

from django.db import IntegrityError, transaction
from django.db.models import F, Count, Q
from django.utils import timezone

from indicator_audit.models import AuditBatch, AuditFile


def create_batch(user, batch_name: str, description: str | None = None) -> AuditBatch:
    """
    创建一个新的审核批次。

    - 批次名称在模型层面已设置 unique，因此这里主要负责封装错误信息。
    """

    batch_name = (batch_name or "").strip()
    if not batch_name:
        raise ValueError("批次名称不能为空。")

    creator = user if user and user.is_authenticated else None

    # 若已存在同名批次，视为同一批次，直接复用（便于断点续传）
    try:
        batch = AuditBatch.objects.get(batch_name=batch_name, created_by=creator)
        # 如有新的描述信息，可按需更新
        new_desc = (description or "").strip() or None
        if new_desc and batch.description != new_desc:
            batch.description = new_desc
            batch.save(update_fields=["description"])
        return batch
    except AuditBatch.DoesNotExist:
        pass

    try:
        batch = AuditBatch.objects.create(
            batch_name=batch_name,
            description=(description or "").strip() or None,
            created_by=creator,
            status=AuditBatch.STATUS_PENDING,
        )
    except IntegrityError as exc:  # pragma: no cover - 由唯一索引兜底
        raise ValueError("批次名称已存在，请更换一个名称。") from exc
    return batch


def attach_files(batch: AuditBatch, files: Iterable[AuditFile]) -> None:
    """
    将一批文件挂到批次上，并更新 total_files / status。

    该函数假设 AuditFile 已经保存到数据库。
    """

    file_list = list(files)
    if not file_list:
        return

    count = len(file_list)
    with transaction.atomic():
        AuditBatch.objects.filter(pk=batch.pk).update(
            total_files=F("total_files") + count,
            status=AuditBatch.STATUS_PROCESSING,
            updated_at=timezone.now(),
        )


def mark_file_finished(audit_file: AuditFile, success: bool) -> None:
    """
    在单个文件任务结束后，更新所属批次的计数和状态。
    """

    if not audit_file.batch_id:
        return

    batch_id = audit_file.batch_id

    with transaction.atomic():
        update_kwargs = {"updated_at": timezone.now()}
        if success:
            update_kwargs["completed_files"] = F("completed_files") + 1
        else:
            update_kwargs["failed_files"] = F("failed_files") + 1

        AuditBatch.objects.filter(pk=batch_id).update(**update_kwargs)

        batch = (
            AuditBatch.objects.select_for_update()
            .only("id", "total_files", "completed_files", "failed_files", "status")
            .get(pk=batch_id)
        )

        finished = batch.completed_files + batch.failed_files
        if finished >= batch.total_files and batch.total_files > 0:
            # 所有文件都已结束
            new_status = (
                AuditBatch.STATUS_FAILED
                if batch.failed_files > 0
                else AuditBatch.STATUS_COMPLETED
            )
            if batch.status != new_status:
                batch.status = new_status
                batch.updated_at = timezone.now()
                batch.save(update_fields=["status", "updated_at"])
        else:
            # 仍有任务执行中，确保状态至少为 processing
            if batch.status == AuditBatch.STATUS_PENDING:
                batch.status = AuditBatch.STATUS_PROCESSING
                batch.updated_at = timezone.now()
                batch.save(update_fields=["status", "updated_at"])


def get_batch_progress(batch_id: int) -> Dict[str, Any]:
    """
    基于 AuditFile 实时聚合批次下的文件数量与状态。

    数据量预期不大，直接用聚合查询即可。
    """

    batch = AuditBatch.objects.only(
        "id",
        "batch_name",
        "status",
        "created_at",
        "updated_at",
    ).get(pk=batch_id)

    agg = AuditFile.objects.filter(batch_id=batch_id).aggregate(
        total=Count("id"),
        completed=Count("id", filter=Q(status=AuditFile.STATUS_COMPLETED)),
        failed=Count("id", filter=Q(status=AuditFile.STATUS_FAILED)),
    )

    total = agg["total"] or 0
    completed = agg["completed"] or 0
    failed = agg["failed"] or 0
    queued = max(total - completed - failed, 0)

    # 基于聚合结果推导出更可靠的批次状态，避免历史计数字段导致“卡住”
    if total == 0:
        derived_status = AuditBatch.STATUS_PENDING
    else:
        finished = completed + failed
        if finished >= total:
            derived_status = (
                AuditBatch.STATUS_FAILED if failed > 0 else AuditBatch.STATUS_COMPLETED
            )
        else:
            derived_status = AuditBatch.STATUS_PROCESSING

    # 若推导状态与数据库不一致，可顺便修正，保持字段收敛
    if derived_status != batch.status:
        AuditBatch.objects.filter(pk=batch.id).update(
            status=derived_status, updated_at=timezone.now()
        )
        batch.status = derived_status

    return {
        "id": batch.id,
        "batch_name": batch.batch_name,
        "status": batch.status,
        "total_files": total,
        "completed_files": completed,
        "failed_files": failed,
        "queued_files": queued,
        "created_at": batch.created_at,
        "updated_at": batch.updated_at,
    }

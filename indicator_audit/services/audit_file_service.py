from __future__ import annotations

import hashlib
import os
from typing import Any, Dict, Tuple, Optional

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from indicator_audit.models import AuditFile, AuditBatch
from indicator_audit.services.audit_issue_service import create_audit_issue


def save_uploaded_file(uploaded_file) -> Tuple[str, str, str]:
    """
    将上传的 Excel 按内容指纹保存到 MEDIA_ROOT，并返回
    (绝对路径, 相对路径, file_hash)。

    设计说明：
        - 使用文件内容的 SHA256 作为唯一指纹。
        - 所有具有相同 file_hash 的文件共享同一物理文件，避免磁盘空间被重复占用。
        - relative_path 指向按指纹命名的统一存储位置，original_filename 由模型字段单独保存。
    """

    # 先读取上传内容并计算指纹（Excel 文件通常不大）
    sha256 = hashlib.sha256()
    chunks: list[bytes] = []
    for chunk in uploaded_file.chunks():
        if not chunk:
            continue
        sha256.update(chunk)
        chunks.append(chunk)
    content = b"".join(chunks)
    file_hash = sha256.hexdigest()

    # 按指纹构造统一的存储路径
    relative_dir = os.path.join("uploads", "indicator_audit", "by_hash")
    os.makedirs(os.path.join(settings.MEDIA_ROOT, relative_dir), exist_ok=True)

    # 尽量保留扩展名，便于排查与手工打开
    safe_name = os.path.basename(uploaded_file.name or "")
    _, ext = os.path.splitext(safe_name)
    ext = ext or ".xlsx"
    filename = f"{file_hash}{ext}"
    relative_path = os.path.join(relative_dir, filename)
    full_path = os.path.join(settings.MEDIA_ROOT, relative_path)

    # 若磁盘上尚不存在该指纹文件，则写入一次；否则复用已有文件
    if not os.path.exists(full_path):
        with open(full_path, "wb") as destination:
            destination.write(content)

    return full_path, relative_path, file_hash


def create_audit_file_for_upload(
    *,
    user,
    batch,
    original_filename: str,
    file_size: int | None,
    relative_path: str,
    file_hash: Optional[str] = None,
) -> AuditFile:
    """
    为一次上传创建初始的 AuditFile 记录。

    - 如果已知 file_hash，可一并写入；否则用空字符串占位，待审核完成后补齐。
    """

    return AuditFile.objects.create(
        created_by=user if user and getattr(user, "is_authenticated", False) else None,
        batch=batch,
        original_filename=original_filename or os.path.basename(relative_path),
        relative_path=relative_path,
        file_size=file_size or None,
        file_hash=file_hash or "",
        status=AuditFile.STATUS_PENDING,
        reused_from_file=None,
    )


def calculate_file_hash(file_path: str) -> str:
    """计算文件的 SHA256 指纹，用于去重与结果复用。"""

    sha256 = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
    except OSError:  # pragma: no cover - IO 异常仅记录日志
        return ""
    return sha256.hexdigest()


def apply_audit_result_to_file(
    audit_file: AuditFile,
    file_path: str,
    pydantic_data: Any,
    final_result: Dict[str, Any],
) -> AuditFile:
    """
    将审核结构化结果写回既有 AuditFile，并生成对应的 AuditIssue。
    """

    try:
        file_hash = calculate_file_hash(file_path)
        size = audit_file.file_size or os.path.getsize(file_path)
    except OSError:
        file_hash = calculate_file_hash(file_path)
        size = audit_file.file_size or 0

    project_info = getattr(pydantic_data, "project_info", None)
    project_name = getattr(project_info, "project_name", None) if project_info else None
    department = getattr(project_info, "department", None) if project_info else None
    total_amount = (
        getattr(project_info, "total_budget", None) if project_info else None
    )

    issues = final_result.get("issues") or []
    score = final_result.get("score")

    critical_count = sum(1 for i in issues if i.get("severity") == "critical")
    warning_count = sum(1 for i in issues if i.get("severity") == "warning")
    info_count = sum(
        1 for i in issues if i.get("severity") not in ("critical", "warning")
    )

    with transaction.atomic():
        audit_file.file_hash = file_hash
        audit_file.file_size = size
        audit_file.project_name = project_name
        audit_file.department = department
        audit_file.score = score
        audit_file.critical_count = critical_count
        audit_file.warning_count = warning_count
        audit_file.info_count = info_count
        audit_file.total_amount = total_amount
        audit_file.pydantic_json = (
            pydantic_data.model_dump()
            if hasattr(pydantic_data, "model_dump")
            else None
        )
        audit_file.report_json = final_result
        audit_file.status = AuditFile.STATUS_COMPLETED
        audit_file.save()

        # 当前设计中，一个文件的审核只执行一次，因此不需要先删除旧的 issues。
        for issue in issues:
            create_audit_issue(audit_file, issue)

    return audit_file


def mark_audit_file_failed(audit_file: AuditFile) -> None:
    """标记文件审核失败。"""

    audit_file.status = AuditFile.STATUS_FAILED
    audit_file.save(update_fields=["status"])


def find_reusable_source_file(file_hash: str) -> Optional[AuditFile]:
    """
    根据文件指纹查找可复用的历史审核结果。

    条件：
        - file_hash 完全一致。
        - 审核状态为 completed。
        - report_json 非空（确保有可供前端展示的完整报告）。
    """

    if not file_hash:
        return None

    return (
        AuditFile.objects.filter(
            file_hash=file_hash,
            status=AuditFile.STATUS_COMPLETED,
            report_json__isnull=False,
        )
        .order_by("-created_at")
        .first()
    )


def find_existing_in_batch_by_hash(
    batch: AuditBatch, file_hash: str
) -> Optional[AuditFile]:
    """
    在指定批次内，根据文件指纹查找是否已存在同内容文件。

    用途：
        - 批次内部去重：当同时或多次上传同一目录时，避免重复计数与重复创建记录。
    """

    if not file_hash or not batch:
        return None

    return (
        AuditFile.objects.filter(batch=batch, file_hash=file_hash)
        .order_by("-created_at")
        .first()
    )


def create_reused_audit_file(
    *,
    user,
    batch,
    original_filename: str,
    file_size: int | None,
    relative_path: str,
    file_hash: str,
    source_file: AuditFile,
) -> AuditFile:
    """
    基于已有的 AuditFile 结果创建一条复用记录。

    行为：
        - 新建一条 AuditFile，reused_from_file 指向 source_file。
        - 复制项目名称、部门、得分、红黄蓝灯数量、资金总额、结构化数据与报告 JSON。
        - 审核状态直接标记为 completed，不再触发 Celery。
    """

    return AuditFile.objects.create(
        created_by=user if user and getattr(user, "is_authenticated", False) else None,
        batch=batch,
        original_filename=original_filename or os.path.basename(relative_path),
        relative_path=relative_path,
        file_size=file_size or source_file.file_size,
        file_hash=file_hash or source_file.file_hash or "",
        status=AuditFile.STATUS_COMPLETED,
        reused_from_file=source_file,
        project_name=source_file.project_name,
        department=source_file.department,
        score=source_file.score,
        critical_count=source_file.critical_count,
        warning_count=source_file.warning_count,
        info_count=source_file.info_count,
        total_amount=source_file.total_amount,
        pydantic_json=source_file.pydantic_json,
        report_json=source_file.report_json,
    )

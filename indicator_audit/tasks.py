"""异步审核任务与 Redis 进度写入工具。"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Any, Dict, List

from celery import shared_task
from django.core.cache import cache
from django.conf import settings

from indicator_audit.models import AuditFile
from indicator_audit.services.audit_issue_service import create_audit_issue
from indicator_audit.services.check_indicator_excel import audit_pipeline

logger = logging.getLogger(__name__)


TASK_CACHE_TTL = 24 * 60 * 60  # 结果在 Redis 中保留 24 小时


def _cache_key(task_id: str) -> str:
    """构造缓存键，确保不同任务隔离。"""

    return f"audit_task_{task_id}"


def _update_log(
    task_id: str, status: str, message: str, result: Any | None = None
) -> Dict:
    """追加日志并同步任务状态到 Redis。"""

    key = _cache_key(task_id)
    data = cache.get(key) or {}
    logs: List[Dict[str, str]] = data.get("logs") or []
    logs.append({"status": status, "message": message})
    data["status"] = status
    data["logs"] = logs
    if result is not None:
        data["result"] = result
    cache.set(key, data, timeout=TASK_CACHE_TTL)
    return data


def _calculate_file_hash(file_path: str) -> str:
    """计算文件的 SHA256 指纹，用于去重与结果复用。"""

    sha256 = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
    except OSError as exc:  # pragma: no cover - IO 异常仅记录日志
        logger.warning("计算文件哈希失败: %s", exc)
        return ""
    return sha256.hexdigest()


def _persist_audit_result(
    file_path: str,
    original_filename: str,
    file_size: int,
    pydantic_data: Any,
    final_result: Dict[str, Any],
) -> None:
    """
    将本次审核结果落地为 AuditFile 和 AuditIssue 记录。

    该函数在 Celery 任务中调用，任何异常都只记录日志，不影响任务返回。
    """

    try:
        file_hash = _calculate_file_hash(file_path)
        size = file_size or os.path.getsize(file_path)
    except OSError:
        file_hash = _calculate_file_hash(file_path)
        size = file_size or 0

    # 计算相对路径，便于后续做批次内断点续传
    try:
        relative_path = os.path.relpath(file_path, settings.MEDIA_ROOT)
    except Exception:
        relative_path = file_path

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
        1
        for i in issues
        if i.get("severity") not in ("critical", "warning")
    )

    audit_file = AuditFile.objects.create(
        batch=None,
        original_filename=original_filename or os.path.basename(file_path),
        relative_path=relative_path,
        file_size=size,
        file_hash=file_hash,
        status="completed",
        reused_from_file=None,
        project_name=project_name,
        department=department,
        score=score,
        critical_count=critical_count,
        warning_count=warning_count,
        info_count=info_count,
        total_amount=total_amount,
        pydantic_json=pydantic_data.model_dump() if hasattr(pydantic_data, "model_dump") else None,
        report_json=final_result,
    )

    for issue in issues:
        try:
            create_audit_issue(audit_file, issue)
        except Exception as exc:  # pragma: no cover - 单条问题失败不影响整体
            logger.warning("创建 AuditIssue 失败: %s", exc)


@shared_task(bind=True)
def run_audit_task(
    self, file_path: str, task_id: str, original_filename: str, file_size: int
) -> Dict[str, Any]:
    """分步骤执行 Excel 审核并在阶段间写入进度日志。"""

    try:
        _update_log(task_id, "processing", "正在读取并解析 Excel 结构...")
        markdown_text = audit_pipeline.parse_excel_to_markdown(file_path)

        _update_log(task_id, "processing", "AI 正在分析数据，请耐心等待约 10-15 秒...")
        pydantic_data = audit_pipeline.extract_data_with_ai(markdown_text)

        _update_log(task_id, "processing", "正在进行资金与逻辑校验...")
        rigid_issues = audit_pipeline.run_rigid_validation(pydantic_data)

        normalized_rigid = [
            audit_pipeline.normalize_rigid_issue(item) for item in rigid_issues
        ]
        critical_count = sum(
            1 for issue in normalized_rigid if issue["severity"] == "critical"
        )

        semantic_issues = []
        if critical_count < 5:
            _update_log(
                task_id,
                "processing",
                "AI 正在进行深度语义复核，请等待约 10 秒...",
            )
            semantic_issues = audit_pipeline.run_semantic_check(pydantic_data)

        final_result = audit_pipeline.format_final_report(
            pydantic_data, rigid_issues, semantic_issues
        )

        # 审核结果写入缓存（供前端轮询展示）
        _update_log(task_id, "completed", "审核完成！", result=final_result)

        # 将结果落地到数据库，任何异常都不会影响前端拿到结果
        try:
            _persist_audit_result(
                file_path=file_path,
                original_filename=original_filename,
                file_size=file_size,
                pydantic_data=pydantic_data,
                final_result=final_result,
            )
        except Exception as exc:  # pragma: no cover - 持久化失败不阻断任务
            logger.warning("持久化审核结果失败: %s", exc)

        return final_result

    except Exception as exc:  # pragma: no cover - 运行时保护
        logger.exception("审核任务失败: %s", exc)
        _update_log(task_id, "failed", f"任务失败：{exc}")
        raise

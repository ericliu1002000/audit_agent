"""异步审核任务与 Redis 进度写入工具。"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from celery import shared_task
from django.core.cache import cache

from indicator_audit.models import AuditFile
from indicator_audit.services import audit_file_service, batch_service
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


@shared_task(bind=True)
def run_audit_task(
    self,
    file_path: str,
    task_id: str,
    audit_file_id: int,
) -> Dict[str, Any]:
    """分步骤执行 Excel 审核并在阶段间写入进度日志。"""

    audit_file: AuditFile | None = None

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

        try:
            audit_file = AuditFile.objects.get(pk=audit_file_id)
        except AuditFile.DoesNotExist:  # pragma: no cover - 极端情况
            logger.warning("审核结果持久化失败：AuditFile(id=%s) 不存在。", audit_file_id)
            return final_result

        # 将结果落地到数据库，任何异常都不会影响前端拿到结果
        try:
            audit_file_service.apply_audit_result_to_file(
                audit_file=audit_file,
                file_path=file_path,
                pydantic_data=pydantic_data,
                final_result=final_result,
            )
        except Exception as exc:  # pragma: no cover - 持久化失败不阻断任务
            logger.warning("持久化审核结果失败: %s", exc)

        try:
            batch_service.mark_file_finished(audit_file, success=True)
        except Exception as exc:  # pragma: no cover - 批次统计失败不阻断任务
            logger.warning("更新批次统计失败: %s", exc)

        return final_result

    except Exception as exc:  # pragma: no cover - 运行时保护
        logger.exception("审核任务失败: %s", exc)
        _update_log(task_id, "failed", f"任务失败：{exc}")

        # 如果已经有对应的 AuditFile，则标记为失败并更新批次
        if audit_file is None:
            try:
                audit_file = AuditFile.objects.get(pk=audit_file_id)
            except AuditFile.DoesNotExist:
                audit_file = None

        if audit_file is not None:
            try:
                audit_file_service.mark_audit_file_failed(audit_file)
            except Exception as mark_exc:  # pragma: no cover
                logger.warning("标记 AuditFile 失败: %s", mark_exc)
            try:
                batch_service.mark_file_finished(audit_file, success=False)
            except Exception as batch_exc:  # pragma: no cover
                logger.warning("更新批次统计失败: %s", batch_exc)

        raise

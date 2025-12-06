"""异步审核任务与 Redis 进度写入工具。"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from celery import shared_task
from django.core.cache import cache

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
def run_audit_task(self, file_path: str, task_id: str) -> Dict[str, Any]:
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
        _update_log(task_id, "completed", "审核完成！", result=final_result)
        return final_result

    except Exception as exc:  # pragma: no cover - 运行时保护
        logger.exception("审核任务失败: %s", exc)
        _update_log(task_id, "failed", f"任务失败：{exc}")
        raise


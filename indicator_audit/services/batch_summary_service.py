from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List

from django.db.models import Avg, Count, Q, Sum

from indicator_audit.constants import ISSUE_TYPE_CHOICES
from indicator_audit.models import AuditBatch, AuditFile, AuditIssue


def _decimal_to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def build_batch_summary(batch: AuditBatch) -> Dict[str, Any]:
    """
    构建单个批次的统计汇总数据，用于“批次统计大屏”。

    统计维度：
        - 资金盘子：total_amount
        - 健康度：平均分 / 合格率 / 不合格数量 / 需整改数量
        - 问题分布：按问题类型 + 严重程度聚合
        - 部门排名：按部门聚合平均分 / 合格率 / 红灯数量
        - 资金-质量散点：用于四象限图（金额 vs 评分）
    """

    # 文件基础集合
    all_files_qs = AuditFile.objects.filter(batch=batch)
    completed_files_qs = all_files_qs.filter(status=AuditFile.STATUS_COMPLETED)

    total_files = all_files_qs.count()
    completed_files = completed_files_qs.count()

    # ---------------- KPI：资金盘子 & 健康度 ----------------
    agg = completed_files_qs.aggregate(
        avg_score=Avg("score"),
        total_amount=Sum("total_amount"),
        pass_count=Count(
            "id",
            filter=Q(score__gte=80, critical_count=0),
        ),
        fail_count=Count(
            "id",
            filter=Q(Q(score__lt=60) | Q(critical_count__gt=0)),
        ),
        warning_count=Count(
            "id",
            filter=Q(score__gte=60, score__lt=80, critical_count=0),
        ),
    )

    avg_score = agg["avg_score"] or 0
    total_amount = agg["total_amount"]
    pass_count = agg["pass_count"] or 0
    fail_count = agg["fail_count"] or 0
    warning_count = agg["warning_count"] or 0

    if completed_files:
        pass_rate = round(float(pass_count) * 100.0 / float(completed_files), 1)
    else:
        pass_rate = 0.0

    kpi_summary = {
        "avg_score": round(float(avg_score), 1) if avg_score is not None else None,
        "pass_rate": pass_rate,  # 百分比 0-100
        "fail_count": int(fail_count),
        "warning_count": int(warning_count),
        "total_completed_files": completed_files,
        "total_files": total_files,
    }

    fund_summary = {
        "total_amount": _decimal_to_float(total_amount),
        "currency": "万元",
    }

    # ---------------- 问题分布：按问题类型 + 严重程度 ----------------
    issues_qs = AuditIssue.objects.filter(
        file__batch=batch,
        file__status=AuditFile.STATUS_COMPLETED,
    )
    issues_agg = issues_qs.values("type").annotate(
        total=Count("id"),
        critical=Count("id", filter=Q(severity="critical")),
        warning=Count("id", filter=Q(severity="warning")),
        info=Count("id", filter=Q(severity="info")),
    )

    type_label_map = dict(ISSUE_TYPE_CHOICES)
    issues_by_type: List[Dict[str, Any]] = []
    for row in issues_agg:
        issue_type = row["type"] or ""
        issues_by_type.append(
            {
                "type": issue_type,
                "label": type_label_map.get(issue_type, issue_type or "未分类"),
                "total": row["total"] or 0,
                "critical": row["critical"] or 0,
                "warning": row["warning"] or 0,
                "info": row["info"] or 0,
            }
        )
    # 按总数量降序排序
    issues_by_type.sort(key=lambda x: x["total"], reverse=True)

    # ---------------- 部门排名：平均分 / 合格率 / 红灯数量 ----------------
    dept_qs = completed_files_qs.exclude(department__isnull=True).exclude(
        department__exact=""
    )
    dept_agg = dept_qs.values("department").annotate(
        file_count=Count("id"),
        avg_score=Avg("score"),
        pass_count=Count(
            "id",
            filter=Q(score__gte=80, critical_count=0),
        ),
        critical_total=Sum("critical_count"),
    )

    dept_ranking: List[Dict[str, Any]] = []
    for row in dept_agg:
        file_count = row["file_count"] or 0
        if not file_count:
            continue
        dept_pass_count = row["pass_count"] or 0
        dept_avg_score = row["avg_score"] or 0
        dept_pass_rate = round(
            float(dept_pass_count) * 100.0 / float(file_count), 1
        )
        dept_ranking.append(
            {
                "department": row["department"],
                "file_count": file_count,
                "avg_score": round(float(dept_avg_score), 1),
                "pass_rate": dept_pass_rate,
                "critical_total": int(row["critical_total"] or 0),
            }
        )
    # 排名：先按平均分升序，再按红灯数量降序
    dept_ranking.sort(
        key=lambda x: (x["avg_score"], -x["critical_total"]),
    )
    # 取前 10 名作为“红黑榜”
    dept_ranking = dept_ranking[:10]

    # ---------------- 资金-质量散点：金额 vs 评分 ----------------
    scatter_qs = completed_files_qs.exclude(total_amount__isnull=True).exclude(
        score__isnull=True
    )
    scatter_points: List[Dict[str, Any]] = []
    for f in scatter_qs[:300]:  # 上限 300 个点，防止图过密
        scatter_points.append(
            {
                "file_id": f.id,
                "project_name": f.project_name or f.original_filename,
                "department": f.department or "",
                "amount": _decimal_to_float(f.total_amount) or 0.0,
                "score": float(f.score or 0),
            }
        )

    return {
        "batch": {
            "id": batch.id,
            "name": batch.batch_name,
            "status": batch.status,
            "total_files": total_files,
            "completed_files": completed_files,
            "created_at": batch.created_at.isoformat() if batch.created_at else None,
        },
        "fund_summary": fund_summary,
        "kpi_summary": kpi_summary,
        "issues_by_type": issues_by_type,
        "department_ranking": dept_ranking,
        "scatter_points": scatter_points,
    }


"""价格审核报告结构化输出。"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from price_audit.models import PriceAuditSubmission


def _json_safe(value: Any) -> Any:
    """把 Decimal 等对象转换成可序列化值。"""

    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def build_submission_report(submission: PriceAuditSubmission) -> dict[str, Any]:
    """构造价格审核结果 JSON。"""

    rows = []
    for row in submission.rows.select_related("decision").order_by("excel_row_no"):
        decision = getattr(row, "decision", None)
        rows.append(
            {
                "row_id": row.id,
                "excel_row_no": row.excel_row_no,
                "sequence_no": row.sequence_no,
                "parent_sequence_no": row.parent_sequence_no,
                "row_type": row.row_type,
                "fee_type": row.fee_type,
                "submitted_amount": row.submitted_amount,
                "decision": {
                    "status": decision.status if decision else None,
                    "result_type": decision.result_type if decision else None,
                    "reviewed_amount": decision.reviewed_amount if decision else None,
                    "reduction_amount": decision.reduction_amount if decision else None,
                    "reason": decision.reason if decision else "",
                    "error_message": decision.error_message if decision else "",
                },
            }
        )

    failed_rows = sum(
        1 for item in rows if (item["decision"].get("status") if item["decision"] else None) == "failed"
    )
    skipped_rows = sum(
        1 for item in rows if (item["decision"].get("result_type") if item["decision"] else None) == "skipped"
    )
    completed_rows = sum(
        1
        for item in rows
        if (item["decision"].get("status") if item["decision"] else None) == "completed"
    )

    return _json_safe(
        {
        "submission_id": submission.id,
        "project_name": submission.project_name,
        "status": submission.status,
        "price_batch_id": submission.price_batch_id,
        "submitted_total_amount": submission.submitted_total_amount,
        "reviewed_total_amount": submission.reviewed_total_amount,
        "reduction_total_amount": submission.reduction_total_amount,
        "statistics": {
            "total_rows": len(rows),
            "completed_rows": completed_rows,
            "failed_rows": failed_rows,
            "skipped_rows": skipped_rows,
        },
        "rows": rows,
        }
    )

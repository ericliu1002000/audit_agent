from typing import Any, Dict, Optional

from indicator_audit.constants import ISSUE_TYPE_CHOICES
from indicator_audit.models import AuditFile, AuditIssue


_VALID_ISSUE_TYPES = {code for code, _ in ISSUE_TYPE_CHOICES}


def _normalize_issue_type(value: Optional[str]) -> Optional[str]:
    """
    将外部传入的 issue_type 规范化为内部枚举值。

    仅接受 constants 中声明的几种类型，其它值一律视为 None。
    """

    if not value:
        return None
    value = str(value).strip().lower()
    return value if value in _VALID_ISSUE_TYPES else None


def create_audit_issue(file: AuditFile, issue_data: Dict[str, Any]) -> AuditIssue:
    """
    根据规范化后的 issue 字典，为指定文件创建一条 AuditIssue 记录。

    预期的 issue_data 结构通常来自 audit_pipeline.format_final_report() 的 issues 列表：
        {
            "source": "rules" | "ai" | "system",
            "source_label": "刚性规则" | "智能审查" | "系统",
            "severity": "critical" | "warning" | "info",
            "title": "...",
            "description": "...",
            "position": "...",
            "suggestion": "...",
            "issue_type": "completeness" | "compliance" | "measurability" | "relevance" | "mismatch"
        }
    """

    severity = (issue_data.get("severity") or "info").lower()
    source = (issue_data.get("source") or "system").lower()
    source_label = issue_data.get("source_label") or None
    issue_type_raw = issue_data.get("issue_type") or issue_data.get("type")
    issue_type = _normalize_issue_type(issue_type_raw)

    title = issue_data.get("title") or "问题"
    description = issue_data.get("description") or None
    position = issue_data.get("position") or None
    suggestion = issue_data.get("suggestion") or None

    return AuditIssue.objects.create(
        file=file,
        severity=severity,
        source=source,
        source_label=source_label,
        type=issue_type,
        title=title,
        description=description,
        position=position,
        suggestion=suggestion,
    )


import logging
from typing import Any, Callable, Dict, List, Optional

from indicator_audit.services.utils.excel_to_markdown import (
    parse_excel_to_markdown as _parse_excel_to_markdown,
)
from indicator_audit.services.check_indicator_excel.ai_extractor_from_md import (
    extract_data_with_ai as _extract_data_with_ai,
)
from indicator_audit.services.check_indicator_excel.rigid_validation import (
    run_rigid_validation as _run_rigid_validation,
)
from indicator_audit.services.check_indicator_excel.semantic_validator import (
    run_semantic_check as _run_semantic_check,
)


logger = logging.getLogger(__name__)


def normalize_rigid_issue(issue: Dict) -> Dict:
    """
    将刚性校验结果转换为标准格式
    Input: {'level': 'ERROR', 'loc': '项目资金', 'msg': '资金不平...'}
    """
    severity_map = {
        "ERROR": "critical",
        "WARNING": "warning",
        "INFO": "info",
    }

    return {
        "source": "rules",  # 标识来源：规则引擎
        "source_label": "刚性规则",
        "severity": severity_map.get(issue["level"], "info"),
        "title": f"{issue['loc']}校验未通过",
        "description": issue["msg"],
        "position": issue["loc"],
        "suggestion": "请根据规则修正Excel中的对应数据。",  # 刚性错误通常不需要复杂建议，改对为止
    }


def normalize_semantic_issue(issue: Dict) -> Dict:
    """
    将语义校验结果转换为标准格式
    Input: {'type': '一致性风险', 'severity': '中', 'location': '...', 'message': '...', 'suggestion': '...'}
    """
    # 语义分析通常不应阻断流程，最高级别设为 warning
    severity_map = {
        "高": "warning",
        "中": "warning",
        "低": "info",
        "HIGH": "warning",
        "MEDIUM": "warning",
        "LOW": "info",
    }

    return {
        "source": "ai",  # 标识来源：AI引擎
        "source_label": "智能审查",
        "severity": severity_map.get(issue.get("severity", "中"), "info"),
        "title": issue.get("type", "逻辑建议"),
        "description": issue.get("message", ""),
        "position": issue.get("location", "全局"),
        "suggestion": issue.get("suggestion", ""),
    }


def parse_excel_to_markdown(file_path: str) -> str:
    """读取 Excel 文件并转成 Markdown 文本，失败会抛出 ValueError。"""

    return _parse_excel_to_markdown(file_path)


def extract_data_with_ai(markdown_text: str):
    """调用 AI 大模型，从 Markdown 文本提取结构化数据。"""

    return _extract_data_with_ai(markdown_text)


def run_rigid_validation(json_data: Any) -> List[Dict[str, Any]]:
    """执行刚性规则校验，返回原始问题列表。"""

    return _run_rigid_validation(json_data)


def run_semantic_check(json_data: Any) -> List[Dict[str, Any]]:
    """执行语义校验，返回原始问题列表。"""

    return _run_semantic_check(json_data)


def format_final_report(
    pydantic_data: Any,
    rigid_issues: List[Dict[str, Any]],
    semantic_issues: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """汇总并格式化审核报告，含健康分与问题列表。"""

    report_list: List[Dict[str, Any]] = []

    normalized_rigid = [normalize_rigid_issue(item) for item in rigid_issues]
    report_list.extend(normalized_rigid)

    critical_errors = [x for x in normalized_rigid if x["severity"] == "critical"]

    if semantic_issues is None:
        semantic_issues = []

    if len(critical_errors) < 5:
        report_list.extend(normalize_semantic_issue(item) for item in semantic_issues)
    else:
        report_list.append(
            {
                "source": "system",
                "severity": "info",
                "title": "智能审查跳过",
                "description": "由于刚性规则错误过多，系统已跳过深度语义审查，请先修正基础格式错误。",
                "position": "全局",
                "suggestion": "",
            }
        )

    severity_order = {"critical": 0, "warning": 1, "info": 2}
    report_list.sort(key=lambda x: severity_order.get(x["severity"], 3))

    return {
        "success": True,
        "score": calculate_score(report_list),
        "project_name": getattr(
            getattr(pydantic_data, "project_info", None),
            "project_name",
            "",
        ),
        "project_data": pydantic_data.model_dump() if pydantic_data else {},
        "issues": report_list,
    }


def audit_project_file(
    file_path: str,
    write_status: bool = False,
    status_callback: Optional[Callable[[str, str], None]] = None,
) -> Dict[str, Any]:
    """
    执行全流程审核，可选地向外输出进度；默认不写入任何状态。

    Returns:
        {
            "success": True/False,
            "project_data": {...},
            "report": [ ... ]
        }
    """

    def _maybe_log(status: str, message: str) -> None:
        """按需调用外部状态回调，避免在未启用时产生副作用。"""

        if write_status and status_callback:
            try:
                status_callback(status, message)
            except Exception as callback_err:  # pragma: no cover - 仅日志提示
                logger.warning("状态回调失败: %s", callback_err)

    try:
        _maybe_log("processing", "正在读取并解析 Excel 结构...")
        markdown_text = parse_excel_to_markdown(file_path)

        _maybe_log("processing", "AI 正在分析数据，请耐心等待约 20-30 秒...")
        pydantic_data = extract_data_with_ai(markdown_text)

        _maybe_log("processing", "正在进行资金与逻辑校验...")
        rigid_raw_issues = run_rigid_validation(pydantic_data)

        critical_after_rigid = [
            issue
            for issue in (normalize_rigid_issue(item) for item in rigid_raw_issues)
            if issue["severity"] == "critical"
        ]

        semantic_raw_issues: Optional[List[Dict[str, Any]]] = None
        if len(critical_after_rigid) < 5:
            _maybe_log("processing", "AI 正在进行深度语义复核，请等待约 30 秒...")
            semantic_raw_issues = run_semantic_check(pydantic_data)

        result = format_final_report(pydantic_data, rigid_raw_issues, semantic_raw_issues)
        _maybe_log("completed", "审核完成！")
        return result

    except ValueError as e:
        # 业务逻辑错误（如模板不对，AI解析失败）
        logger.warning(f"Audit failed: {e}")
        return {
            "success": False,
            "error_msg": str(e),
        }
    except Exception as e:
        # 系统级错误
        logger.error(f"Audit system error: {e}", exc_info=True)
        return {
            "success": False,
            "error_msg": "系统内部错误，请联系管理员。",
        }


def calculate_score(issues: List[Dict]) -> int:
    """
    简单计算一个健康分 (100分制)
    """
    score = 100
    for issue in issues:
        if issue["severity"] == "critical":
            score -= 10
        elif issue["severity"] == "warning":
            score -= 5
        elif issue["severity"] == "info":
            score -= 1
    return max(score, 0)


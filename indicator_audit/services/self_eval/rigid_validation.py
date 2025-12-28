"""刚性校验器：负责对自评表结构化数据做数学/逻辑核查。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from indicator_audit.constants import ISSUE_TYPE_COMPLIANCE, ISSUE_TYPE_COMPLETENESS
from indicator_audit.services.self_eval.schemas import PerformanceSelfEvalSchema


def _is_blank(value: Any) -> bool:
    """判断字段是否为空（None 或 空字符串）。"""

    return value is None or (isinstance(value, str) and value.strip() == "")


def _to_float(value: Any) -> Optional[float]:
    """将可能的字符串数值安全转换为 float，失败返回 None。"""

    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        if cleaned.endswith("%"):
            cleaned = cleaned[:-1].strip()
        if cleaned == "":
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _approx_equal(a: float, b: float, tolerance: float = 0.1) -> bool:
    """判断两个数值是否在容忍误差范围内相等。"""

    return abs(a - b) <= tolerance


def run_rigid_validation(data: PerformanceSelfEvalSchema) -> List[Dict[str, Any]]:
    """
    功能说明:
        执行绩效自评表的刚性规则校验，覆盖预算执行率与指标得分逻辑。
    使用示例:
        issues = run_rigid_validation(self_eval_data)
        for issue in issues:
            print(issue["msg"])
    输入参数:
        data: 结构化后的绩效自评表数据对象。
    输出参数:
        List[Dict[str, Any]]: 刚性校验问题列表，包含 level/loc/msg/issue_type。
    """

    results: List[Dict[str, Any]] = []

    def add_error(loc: str, msg: str, issue_type: str | None = None) -> None:
        results.append(
            {"level": "ERROR", "loc": loc, "msg": msg, "issue_type": issue_type}
        )

    def add_warning(loc: str, msg: str, issue_type: str | None = None) -> None:
        results.append(
            {"level": "WARNING", "loc": loc, "msg": msg, "issue_type": issue_type}
        )

    def add_info(loc: str, msg: str, issue_type: str | None = None) -> None:
        results.append(
            {"level": "INFO", "loc": loc, "msg": msg, "issue_type": issue_type}
        )

    # =========================================
    # 1. 预算执行率与预算得分核验
    # -----------------------------------------
    # 公式：得分 = (全年执行数 / 全年预算数) * 分值
    # =========================================
    for item in data.budget_items:
        a_value = _to_float(item.full_year_budget)
        b_value = _to_float(item.full_year_execution)
        weight = _to_float(item.score_weight)
        self_score = _to_float(item.self_score)

        if a_value is None or b_value is None or weight is None or self_score is None:
            continue

        if a_value == 0:
            add_error(
                f"项目资金: {item.item_name or '预算执行率'}",
                "全年预算数为 0，无法计算预算执行率得分。",
                ISSUE_TYPE_COMPLIANCE,
            )
            continue

        expected_score = (b_value / a_value) * weight
        if not _approx_equal(self_score, expected_score, tolerance=0.1):
            add_error(
                f"项目资金: {item.item_name or '预算执行率'}",
                f"预算执行率得分不匹配，应为 {expected_score:.2f}，实际为 {self_score:.2f}。",
                ISSUE_TYPE_COMPLIANCE,
            )

    # =========================================
    # 2. 指标得分与偏差原因核验
    # -----------------------------------------
    # 得分规则：
    # - B >= A → 应得分 = 分值
    # - B < A  → 应得分 = (B/A) * 分值
    # 偏差原因规则：
    # - B >= A → 不需要填写偏差原因
    # - B < A  → 必须填写偏差原因
    # =========================================
    for ind in data.indicators:
        a_value = _to_float(ind.target_value)
        b_value = _to_float(ind.actual_value)
        weight = _to_float(ind.score_weight)
        self_score = _to_float(ind.self_score)
        reason_blank = _is_blank(ind.deviation_reason)
        loc = f"指标: {ind.level3 or ind.level2 or ind.level1 or '未命名指标'}"

        if a_value is None or b_value is None or weight is None or self_score is None:
            continue

        if a_value == 0:
            add_error(
                loc,
                "年度指标值为 0，无法计算应得分。",
                ISSUE_TYPE_COMPLIANCE,
            )
            continue

        if b_value >= a_value:
            expected_score = weight
            if not _approx_equal(self_score, expected_score, tolerance=0.1):
                add_error(
                    loc,
                    f"指标得分不匹配，应为满分 {expected_score:.2f}，实际为 {self_score:.2f}。",
                    ISSUE_TYPE_COMPLIANCE,
                )
        else:
            expected_score = (b_value / a_value) * weight
            if not _approx_equal(self_score, expected_score, tolerance=0.1):
                add_error(
                    loc,
                    f"指标得分不匹配，应为 {expected_score:.2f}，实际为 {self_score:.2f}。",
                    ISSUE_TYPE_COMPLIANCE,
                )
            if reason_blank:
                add_error(
                    loc,
                    "指标未达成满分，但未填写偏差原因。",
                    ISSUE_TYPE_COMPLETENESS,
                )

    # =========================================
    # 3. 总分合计校验
    # -----------------------------------------
    # 得分合计应等于所有预算项得分 + 指标得分之和。
    # =========================================
    total_score = _to_float(data.total_score)
    if total_score is not None:
        component_scores: List[float] = []
        for item in data.budget_items:
            score = _to_float(item.self_score)
            if score is not None:
                component_scores.append(score)
        for ind in data.indicators:
            score = _to_float(ind.self_score)
            if score is not None:
                component_scores.append(score)

        if component_scores:
            computed_total = sum(component_scores)
            if not _approx_equal(total_score, computed_total, tolerance=0.1):
                add_error(
                    "总分/得分合计",
                    f"得分合计不匹配，应为 {computed_total:.2f}，实际为 {total_score:.2f}。",
                    ISSUE_TYPE_COMPLIANCE,
                )

    return results

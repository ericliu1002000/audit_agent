"""刚性校验器：负责对结构化后的指标数据做数学/逻辑核查。"""

import re
import math
from typing import List, Dict, Any
from datetime import datetime

from indicator_audit.schemas import PerformanceDeclarationSchema


def parse_flexible_date(text: str | None) -> datetime | None:
    """
    高容错日期解析：用于从指标描述中提取时间信息，支持多种格式的“散装文本”，便于后续比较。

    支持格式包括：
    - 2026年1月, 2026年1月1日
    - 2026-01-01, 2026.1.1, 2026/1/1
    - 26-05 (自动补全 2026-05-01)
    - 混排文本（例如 “预计2025年12月底前” 默认解析为 2025-12-01）
    """
    if not text or not isinstance(text, str):
        return None

    # 1. 标准化：将 . / 统一替换为 -
    text = text.replace(".", "-").replace("/", "-")

    # 2. 定义正则匹配模式 (优先级从高到低)
    patterns = [
        # YYYY年M月D日 或 YYYY-M-D
        r"(\d{4})[\u4e00-\u9fa5-](\d{1,2})[\u4e00-\u9fa5-](\d{1,2})",
        # YYYY年M月 (无日)
        r"(\d{4})[\u4e00-\u9fa5-](\d{1,2})",
        # YY-M-D (简写年份)
        r"(\d{2})-(\d{1,2})-(\d{1,2})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            groups = match.groups()
            try:
                year = int(groups[0])
                month = int(groups[1])
                day = int(groups[2]) if len(groups) > 2 else 1  # 缺省日子默认为1号

                # 补全简写年份 (如 26 -> 2026)
                if year < 100:
                    year += 2000

                return datetime(year, month, day)
            except ValueError:
                continue

    return None


def run_rigid_validation(data: PerformanceDeclarationSchema) -> List[Dict[str, Any]]:
    """
    执行刚性业务规则校验。

    该函数会对 LLM/解析层输出的 `PerformanceDeclarationSchema` 做“硬规则”检查，
    例如资金平衡、成本拆分、时间逻辑、占位符等，便于前端直接告警。

    返回:
        List[Dict[str, Any]]: 每条结果包含 level(ERROR/WARNING/INFO)、loc(定位) 和 msg(提示)。
    """
    results: List[Dict[str, Any]] = []

    def add_error(loc, msg):
        results.append({"level": "ERROR", "loc": loc, "msg": msg})

    def add_warning(loc, msg):
        results.append({"level": "WARNING", "loc": loc, "msg": msg})

    def add_info(loc, msg):
        results.append({"level": "INFO", "loc": loc, "msg": msg})

    def _is_blank(value: Any) -> bool:
        """判断字段是否为空（None 或 空字符串）。"""
        return value is None or (isinstance(value, str) and value.strip() == "")

    # =========================================
    # 0. 项目基础信息完整性校验
    # -----------------------------------------
    # 业务上要求：
    # - 项目名称: 未填写 -> ERROR
    # - 主管预算部门: 未填写 -> ERROR
    # - 项目实施单位: 未填写 -> INFO
    # =========================================
    project_info = data.project_info
    if _is_blank(getattr(project_info, "project_name", None)):
        add_error("项目名称", "项目名称未填写。")
    if _is_blank(getattr(project_info, "department", None)):
        add_error("主管预算部门", "主管预算部门未填写。")
    if _is_blank(getattr(project_info, "implementation_unit", None)):
        add_info("项目实施单位", "项目实施单位未填写，仅作提醒。")
    if _is_blank(getattr(project_info, "goal_description", None)):
        add_error("绩效目标", "绩效目标描述未填写")

    # =========================================
    # 1. 资金平衡性校验 (Critical Error)
    # -----------------------------------------
    # 确保总预算 = 财政资金 + 其他资金，允许 0.1 万元误差。
    # =========================================
    total = data.project_info.total_budget
    fiscal = data.project_info.fiscal_funds
    other = data.project_info.other_funds

    # 使用 math.isclose 或 差值判断，容错 0.1 万元
    if abs(total - (fiscal + other)) > 0.1:
        add_error(
            "项目资金",
            f"资金总额({total})与分项之和({fiscal + other})不符，差额超过0.1万元。",
        )

    # =========================================
    # 2. 成本拆分校验 (已关闭)
    # -----------------------------------------
    # level1=成本指标 的合计应不超过项目总预算。
    # 这里容易出现 万元+元 的混用错误，当前策略是关闭此检查。
    # =========================================
    # cost_items = [ind for ind in data.indicators if ind.level1 == '成本指标']
    # if cost_items:
    #     cost_sum = sum(
    #         [ind.target_value for ind in cost_items if isinstance(ind.target_value, (int, float))]
    #     )
    #     if cost_sum > total + 0.1:
    #         add_error(
    #             "成本指标",
    #             f"成本指标明细之和({cost_sum}万元)超出了项目总资金预算({total}万元)。"
    #         )

    # =========================================
    # 3. 完整性校验 (Critical Error)
    # -----------------------------------------
    # 指标必须覆盖三大维度：产出/效益/满意度。
    # =========================================
    level1_set = set(ind.level1 for ind in data.indicators)
    required_levels = {"产出指标", "效益指标", "满意度指标"}
    missing = required_levels - level1_set
    if missing:
        add_error("指标完整性", f"缺少以下维度的具体指标项：{', '.join(missing)}")

    # =========================================
    # 4. 时间逻辑校验 (Logic)
    # -----------------------------------------
    # 检查项目起止时间 & 指标完成时间是否在范围内。
    # =========================================
    p_start = parse_flexible_date(data.project_info.start_date)
    p_end = parse_flexible_date(data.project_info.end_date)

    # 4.1 项目自身时间校验
    if p_start and p_end:
        if p_start > p_end:
            add_error("项目起止时间", "项目结束时间早于开始时间。")
    else:
        add_warning("项目起止时间", "未检测到完整的项目起止时间，跳过部分时效校验。")

    # 4.2 指标时间 vs 项目结束时间
    if p_end:
        for ind in data.indicators:
            # 假设二级指标包含“时效”或者单位是“月/日/年”时进行检查
            is_time_ind = (ind.level2 and "时效" in ind.level2) or (
                ind.unit and any(u in ind.unit for u in ["月", "日", "年"])
            )

            if is_time_ind:
                # 尝试从 target_value (如果是字符串) 或 raw_text 中提取日期
                check_text = (
                    str(ind.target_value)
                    if isinstance(ind.target_value, str)
                    else ind.raw_text
                )
                ind_date = parse_flexible_date(check_text)

                if ind_date and ind_date > p_end:
                    add_error(
                        f"指标: {ind.level3}",
                        f"指标要求完成时间({ind_date.strftime('%Y-%m')})晚于项目结束时间({p_end.strftime('%Y-%m')})。",
                    )

    # =========================================
    # 5. 占位符与合规性校验 (Mixed)
    # -----------------------------------------
    # 检查指标中是否包含 "*" 等占位符、符号方向/百分比异常。
    # =========================================
    for ind in data.indicators:
        # 5.1 占位符清理
        # 如果值是 None 或者 包含 * 号的字符串
        val_str = str(ind.target_value) if ind.target_value is not None else ""
        raw_str = ind.raw_text or ""

        if _is_blank(raw_str):
            add_error(f"指标：{ind.level3}", "指标值未填写")

        if (ind.target_value is None) or ("*" in val_str) or ("*" in raw_str):
            # 定性指标(如"有效提升")如果没有数值是允许的，但不能包含 *
            add_error(
                f"指标: {ind.level3}", "检测到未确定的占位符(*)，请填写具体数值。"
            )

        # 5.2 符号方向 (成本不应设置下限)
        if ind.level1 == "成本指标" and ind.operator in [">", ">="]:
            add_warning(
                f"指标: {ind.level3}",
                "成本指标使用了“大于等于”符号，请确认预算是否无上限？",
            )

        # 5.3 百分比数值异常
        if ind.unit == "%" and isinstance(ind.target_value, (int, float)):
            if ind.target_value > 100:
                add_warning(
                    f"指标: {ind.level3}",
                    f"百分比指标数值({ind.target_value}%)异常，通常不应超过100%。",
                )

    # =========================================
    # 6. 基础属性枚举校验
    # =========================================
    attr = data.project_info.project_attribute
    if attr and attr not in ["经常性项目", "一次性项目"]:
        add_warning("项目属性", f"项目属性 '{attr}' 不规范，建议检查。")

    return results


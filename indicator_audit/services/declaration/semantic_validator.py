"""
semantic_validator
------------------
柔性语义校验：调用 DeepSeek 检查绩效目标与指标在语义层面的匹配关系。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from indicator_audit.schemas import PerformanceDeclarationSchema
from utils.extract_text_from_response import extract_text_from_response
from utils.clean_json_string import clean_json_string
from utils.deepseek_client import invoke_deepseek

logger = logging.getLogger(__name__)


def _build_system_prompt() -> str:
    """构建语义校验的 System Prompt，约束输出格式与审核重点。"""

    return (
        "你是一位财政绩效审核专家。请检查以下项目数据的逻辑合理性、目标与指标的一致性。\n\n"
        "请重点检查：\n"
        "1. 目标支撑度：绩效目标里承诺要做的事，指标里是否存在对应的可衡量项；\n"
        "2. 指标可衡量性：是否存在“有效提升”等模糊描述，建议量化；\n"
        "3. 轻量常识检查（可选）：仅在出现明显不合逻辑的情况时给出低级别提示，例如“满意度目标为 -10%”或“故障率目标为 200%”。"
        "4. 是否存在错别字。 如有错别字，severity值设置为'中',issue_type设置为：completeness，并给出修改建议。"
        "不要因为主观觉得“数值太大/太小”就报错，尤其不要纠结 5% 和 0.05 这类比例换算问题。\n\n"
        "特别说明：\n"
        "- 所有数值均来自系统解析的 Excel 数据，请假定它们在单位和换算（如百分比 5% 存储为 0.05）上已经经过规则校验。\n"
        "- 当同一指标同时给出 raw_text（例如 “5%”）和 target_value（例如 0.05）时，请把它们视为等价的写法，不要认为这是“数值异常”。\n"
        "- 你不需要对数值做“合理性打分”，只在“文字描述”和“数值/单位”之间出现明显矛盾时给出提示（例如文字说“提升到 90%”，但目标值只有 0.1）。\n\n"
        "type 字段的值跟issue_type 相匹配。"
        "问题类型枚举（issue_type）：请根据问题性质，从以下 5 类中选择一类作为 issue_type 字段的值：['completeness', 'compliance','measurability', 'relevance', 'mismatch']\n"
        "- completeness：完整性缺失（信息不全、缺少指标维度或占位符未替换）；\n"
        "- compliance：合规性问题（数学/时间逻辑错误或违反硬性规定，如资金不平衡、时间先后错误等）；\n"
        "- measurability：可衡量性不足（描述模糊、缺乏量化标准或计量单位）；\n"
        "- relevance：相关性缺失（指标内容与绩效目标脱节，无法支撑目标实现）；\n"
        "- mismatch：投入产出不匹配（资金投入、项目属性与指标设置不匹配）。\n\n"
        "请返回 JSON 数组，格式示例\n"
        "[\n"
        "  {\n"
        "    \"type\": \"相关性缺失\",\n"
        "    \"issue_type\": \"relevance\",\n"
        "    \"severity\": \"中\",\n"
        "    \"location\": \"产出指标\",\n"
        "    \"message\": \"目标提及'设备采购'，但未发现相关数量指标\",\n"
        "    \"suggestion\": \"建议增加数量指标，如'设备采购数量'\"\n"
        "  }\n"
        "]\n"
        "若无问题，返回 []。"
    )


def run_semantic_check(data: PerformanceDeclarationSchema) -> List[Dict[str, Any]]:
    """
    调用 DeepSeek 执行柔性语义校验。

    Args:
        data: Pydantic Schema，用于提供待分析的结构化内容。

    Returns:
        List[Dict[str, Any]]: AI 返回的风险列表，若服务异常则返回“系统错误”提示。
    """

    input_json = data.model_dump_json(exclude_none=True, ensure_ascii=False)
    system_prompt = _build_system_prompt()

    try:
        response = invoke_deepseek(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"待审核数据：\n{input_json}"},
            ],
            response_format={"type": "json_object"},
            max_tokens=2000,
        )
    except ValueError:
        # invoke_deepseek 已记录日志，这里直接返回错误提示。
        return [
            {
                "type": "系统错误",
                "severity": "低",
                "location": "AI审核服务",
                "message": "语义分析服务暂时不可用，仅执行了刚性规则校验。",
                "suggestion": "请稍后重试",
            }
        ]

    try:
        content = extract_text_from_response(response)
        cleaned_json = clean_json_string(content)
        result_data = json.loads(cleaned_json) if cleaned_json else []
    except Exception as exc:  # pragma: no cover - 调试/网络波动
        logger.error("语义校验解析失败: %s", exc)
        return [
            {
                "type": "系统错误",
                "severity": "低",
                "location": "AI审核服务",
                "message": "语义分析服务返回内容异常，仅执行了刚性规则校验。",
                "suggestion": "请稍后重试",
            }
        ]

    if isinstance(result_data, list):
        return result_data
    if isinstance(result_data, dict):
        for key in ("warnings", "issues", "result"):
            if key in result_data and isinstance(result_data[key], list):
                return result_data[key]
    return []

"""
semantic_validator
------------------
柔性语义校验：调用 DeepSeek 检查自评表偏差原因与得分表述的合理性。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from indicator_audit.services.self_eval.schemas import PerformanceSelfEvalSchema
from utils.clean_json_string import clean_json_string
from utils.deepseek_client import invoke_deepseek
from utils.extract_text_from_response import extract_text_from_response

logger = logging.getLogger(__name__)


def _build_system_prompt() -> str:
    """构建语义校验的 System Prompt，约束输出格式与审核重点。"""

    return (
        "你是一位财政绩效自评审核专家。请检查以下数据在语义层面的合理性，尤其关注偏差原因与得分之间是否自洽。\n\n"
        "请重点检查：\n"
        "1. 偏差原因合理性：未达标但原因空泛、与指标无关或明显不成立时给出提示；\n"
        "2. 满分但仍填写偏差原因，若内容与“达标/超额完成”矛盾则提示；\n"
        "3. 描述自相矛盾（例如“未完成”，但实际值远高于指标值）时给出低风险提示；\n"
        "4. 是否存在错别字。 如有错别字，severity值设置为'中',issue_type设置为：completeness，并给出修改建议。\n\n"
        "注意：\n"
        "- 只做语义合理性提醒，不做数学计算或二次推导。\n"
        "- 不要因为数值大小本身而报错，仅在“文字描述与数值关系矛盾”时提示。\n\n"
        "问题类型枚举（issue_type）：请根据问题性质，从以下 5 类中选择一类作为 issue_type 字段的值："
        "['completeness', 'compliance', 'measurability', 'relevance', 'mismatch']\n"
        "- completeness：完整性缺失（信息不全、空泛原因、错别字等）；\n"
        "- compliance：合规性问题（与规则明显冲突的表述）；\n"
        "- measurability：可衡量性不足（原因描述模糊、缺乏依据）；\n"
        "- relevance：相关性缺失（偏差原因与指标无关）；\n"
        "- mismatch：投入产出不匹配（预算、目标与结果逻辑不一致）。\n\n"
        "请返回 JSON 数组，格式示例\n"
        "[\n"
        "  {\n"
        "    \"type\": \"偏差原因合理性\",\n"
        "    \"issue_type\": \"relevance\",\n"
        "    \"severity\": \"中\",\n"
        "    \"location\": \"指标: 培训人次\",\n"
        "    \"message\": \"未达标但原因描述与培训人数无关\",\n"
        "    \"suggestion\": \"补充与培训人数不足相关的具体原因\"\n"
        "  }\n"
        "]\n"
        "若无问题，返回 []。"
    )


def run_semantic_check(data: PerformanceSelfEvalSchema) -> List[Dict[str, Any]]:
    """
    功能说明:
        调用 DeepSeek 执行绩效自评表的柔性语义校验。
    使用示例:
        semantic_issues = run_semantic_check(self_eval_data)
    输入参数:
        data: 结构化后的绩效自评表数据对象。
    输出参数:
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

"""
semantic_validator
------------------
柔性语义校验：调用 DeepSeek 检查绩效目标与指标在语义层面的匹配关系。

输出的结果示例 ：
[{'type': '一致性风险',
  'severity': '中',
  'location': '产出指标',
  'message': "目标提及'购置实验实训耗材'，但未发现相关数量指标",
  'suggestion': "建议增加数量指标，如'购置实验实训耗材数量'"},
 {'type': '一致性风险',
  'severity': '中',
  'location': '产出指标',
  'message': "目标提及'完成湖心岛教学楼育人环境提升'，但未发现相关质量或数量指标",
  'suggestion': "建议增加质量指标，如'湖心岛教学楼环境提升完成率'"},
 {'type': '可衡量性风险',
  'severity': '中',
  'location': '产出指标',
  'message': "指标'完成校园监控视频盲区提升改造'的目标值为'保障校内师生安全，维护正常教学秩序'，描述模糊，缺乏量化标准",
  'suggestion': "建议量化目标值，如'监控盲区覆盖率提升至100%'或'安全事故发生率降低至X%'"},
 {'type': '可衡量性风险',
  'severity': '中',
  'location': '效益指标',
  'message': "指标'学科影响力'的目标值为'临床医学、毒理学与药理学、化学保持ESI全球前1%'，描述具体但未明确衡量方式，可能难以评估是否达成",
  'suggestion': "建议明确衡量标准，如'通过年度ESI排名报告确认'"},
 {'type': '常识判断',
  'severity': '低',
  'location': '满意度指标',
  'message': "满意度指标'毕业生满意度'目标值为90%，数值合理，但需确保数据来源可靠",
  'suggestion': '建议明确满意度调查方法和样本量，以增强可信度'}]
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from indicators.schemas import PerformanceDeclarationSchema
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
        "3. 常识判断：数值范围是否合理（仅在出现明显不合逻辑的情况时给出低级别提示，不要因为主观觉得“数值太大/太小”就报错，数值上不要纠结 5% 和 0.05 这类比例换算问题）。\n\n"
        "请返回 JSON 数组，格式示例：\n"
        "[\n"
        "  {\"type\": \"一致性风险\", \"severity\": \"中\", \"location\": \"产出指标\","
        "   \"message\": \"目标提及'设备采购'，但未发现相关数量指标\", \"suggestion\": \"建议增加数量指标\"}\n"
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

if __name__ == "__main__":
    from indicators.services.utils.excel_to_markdown import parse_excel_to_markdown
    example_path = "/Users/liuxiaoqi/SynologyDrive/work/势术/合作/审计智能体/指标相关/实例/天津-高校改革.xlsx"
    str1 = ''
    try:
        str1 = parse_excel_to_markdown(example_path)
    except Exception as exc:
        print(f"解析 Excel 失败: {exc}")

    from indicators.services.check_indicator_excel.ai_extractor_from_md import extract_data_with_ai
    s = extract_data_with_ai(str1)

    from indicators.services.check_indicator_excel.rigid_validation import run_rigid_validation
    rigid_result = run_rigid_validation(s)

    from indicators.services.check_indicator_excel.semantic_validator import run_semantic_check
    semantic_result = run_semantic_check(s)
    
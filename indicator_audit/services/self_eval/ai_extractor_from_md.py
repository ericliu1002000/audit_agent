"""
ai_extractor
------------
负责调用 DeepSeek API，将经过 Excel 解析后的 Markdown 表格转换为结构化 JSON，
并使用 Pydantic Schema (`PerformanceSelfEvalSchema`) 进行强校验。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from pydantic import ValidationError

from indicator_audit.services.self_eval.schemas import PerformanceSelfEvalSchema
from utils.clean_json_string import clean_json_string
from utils.deepseek_client import invoke_deepseek
from utils.extract_text_from_response import extract_text_from_response


logger = logging.getLogger(__name__)


def _build_system_prompt() -> str:
    """
    功能说明:
        构造 DeepSeek 的 System Prompt，包含 schema 约束与自评表抽取规则。
    输入参数:
        无。
    输出参数:
        str: 拼装后的系统提示词。
    """

    schema_definition = json.dumps(
        PerformanceSelfEvalSchema.model_json_schema(),
        ensure_ascii=False,
        indent=2,
    )
    rules = [
        "关键字段映射：年度指标值(A)->target_value，实际完成值(B)->actual_value，分值->score_weight，得分->self_score，偏差原因分析及改进措施->deviation_reason。",
        "合并单元格在 Markdown 中会丢失层级，请继承上方最近的 level1/level2/level3 作为当前行层级。",
        "遇到“—”“*”“/”或空单元格时，输出 null。",
        "总分行通常包含“总分/得分”两个数值，请分别填充 total_weight（分值列）与 total_score（得分列）。",
        "禁止对原始内容进行推理或改写，原文是什么就输出什么。",
        "预算执行率（B/A）仅做原样抽取，暂不自行计算。",
    ]
    rule_block = "\n".join(f"- {rule}" for rule in rules)

    return (
        "你是财政绩效自评表的结构化抽取助手。"
        "请根据给定的 Markdown 表格，严格生成符合下述 JSON Schema 的内容。"
        "必须返回 JSON Object，不要多余解释。\n\n"
        "提取规则：\n"
        f"{rule_block}\n\n"
        "JSON Schema 定义如下（仅参考结构，不要原样输出）：\n"
        f"{schema_definition}"
    )


def extract_data_with_ai(markdown_text: str) -> PerformanceSelfEvalSchema:
    """
    功能说明:
        调用 DeepSeek，将 Markdown 表转换为结构化 JSON，并校验为 PerformanceSelfEvalSchema。
    使用示例:
        markdown_text = parse_excel_to_markdown("/path/to/self_eval.xlsx")
        data = extract_data_with_ai(markdown_text)
        print(data.model_dump())
    输入参数:
        markdown_text: Excel 转 Markdown 后的文本内容。
    输出参数:
        PerformanceSelfEvalSchema: 通过 Schema 校验后的结构化数据对象。
    """

    if not markdown_text or not markdown_text.strip():
        raise ValueError("Markdown 内容为空，无法进行智能抽取。")

    system_prompt = _build_system_prompt()
    response = invoke_deepseek(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": markdown_text},
        ],
        response_format={"type": "json_object"},
    )

    ai_text = extract_text_from_response(response)
    cleaned_json = clean_json_string(ai_text)

    try:
        parsed_payload: Dict[str, Any] = json.loads(cleaned_json)
    except json.JSONDecodeError as exc:
        logger.exception("DeepSeek 返回的 JSON 解析失败: %s", cleaned_json)
        raise ValueError("DeepSeek 返回的 JSON 无法解析，请检查模板内容。") from exc

    try:
        return PerformanceSelfEvalSchema.model_validate(parsed_payload)
    except ValidationError as exc:
        logger.exception("AI 抽取结果未通过 Schema 校验: %s", parsed_payload)
        raise ValueError("AI 抽取结果与数据契约不匹配，请检查输入内容或提示词。") from exc

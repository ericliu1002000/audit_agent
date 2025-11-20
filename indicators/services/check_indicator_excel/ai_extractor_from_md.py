"""
ai_extractor
------------
负责调用 DeepSeek API，将经过 Excel 解析后的 Markdown 表格转换为结构化 JSON，
并使用 Pydantic Schema (`PerformanceDeclarationSchema`) 进行强校验。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List

from pydantic import ValidationError

from indicators.schemas import PerformanceDeclarationSchema, get_ai_extraction_schema
from utils.deepseek_client import invoke_deepseek
from utils.extract_text_from_response import extract_text_from_response
from utils.clean_json_string import clean_json_string


logger = logging.getLogger(__name__)





def _build_system_prompt() -> str:
    """
    构造 DeepSeek 的 System Prompt，包含 schema 约束与业务规则。
    """

    schema_definition = json.dumps(
        get_ai_extraction_schema(), ensure_ascii=False, indent=2
    )
    rules = [
        "数值指标遇到例如“≥95%”“≤20万元”时，必须拆分 operator(>=, <= 等符号) 和 target_value(数字)。",
        "定性指标（文字描述）直接填写 target_value，operator 设为 null，不要试图转换为数字。",
        "遇到“*”“/”或空单元格时，输出 null。",
        "只有当原文明确出现“经常性”或“一次性”时，才填写 project_attribute，否则必须为 null。",
        "出现“成本指标”或“成本拆分”时，作为普通 Indicator 输出，level1 固定为“成本指标”。",
        "严禁对原始内容做加减乘除或推理，原文是什么就输出什么。",
    ]
    rule_block = "\n".join(f"- {rule}" for rule in rules)

    return (
        "你是财政绩效目标申报表的结构化抽取助手。"
        "请根据给定的 Markdown 表格，严格生成符合下述 JSON Schema 的内容。"
        "必须返回 JSON Object，不要多余解释。\n\n"
        "提取规则：\n"
        f"{rule_block}\n\n"
        "JSON Schema 定义如下（仅参考结构，不要原样输出）：\n"
        f"{schema_definition}"
    )





def extract_data_with_ai(markdown_text: str) -> PerformanceDeclarationSchema:
    """
    调用 DeepSeek，将 Markdown 表转换为结构化 JSON，并校验为 PerformanceDeclarationSchema。
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
        return PerformanceDeclarationSchema.model_validate(parsed_payload)
    except ValidationError as exc:
        logger.exception("AI 抽取结果未通过 Schema 校验: %s", parsed_payload)
        raise ValueError("AI 抽取结果与数据契约不匹配，请检查输入内容或提示词。") from exc

if __name__ == "__main__":
    from indicators.services.utils.excel_to_markdown import parse_excel_to_markdown
    example_path = "/Users/liuxiaoqi/SynologyDrive/work/势术/合作/审计智能体/指标相关/实例/天津-高校改革.xlsx"
    try:
        str = parse_excel_to_markdown(example_path)
    except Exception as exc:
        print(f"解析 Excel 失败: {exc}")

    from indicators.services.check_indicator_excel.ai_extractor_from_md import extract_data_with_ai
    extract_data_with_ai(str)

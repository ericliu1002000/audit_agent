"""
parse_indicator_excel
----------------------
本模块用于将财政绩效指标申报表（Excel）转换成扁平化的 Markdown 表格文本。
在 LLM 参与的审核流程中，扁平的 Markdown 更容易被模型读取与理解，
因此需要一个专门的工具方法来处理原始 Excel 中复杂的合并单元格以及格式差异。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException


def clean_text(value) -> str:
    """
    标准化 Excel 单元格文本：去除首尾及内部空白，以便 LLM 正确识别字段。
    业务表格常见“绩 效 目 标”这种分散对齐写法，如果不清洗，会被当成多个 token。
    """

    if value is None:
        return ""
    text = str(value).strip()
    # 使用正则移除字符串内部所有空白字符，避免中文“分散对齐”留下多余空格。
    return re.sub(r"\s+", "", text)


def parse_excel_to_markdown(file_path: str) -> str:
    """
    将 Excel 文件解析为 Markdown 表格字符串（针对指标审核场景做了定制优化）。
    处理流程包括：
    1. 计算数据实际占用的最大列数，用于约束 Markdown 行宽；
    2. 解开合并单元格并填充，避免信息丢失；
    3. 文本标准化 + 行内去重 + 补齐列数，保证输出表格列数统一、语义紧凑。

    参数:
        file_path (str): Excel 文件的绝对路径或相对路径。

    返回:
        str: 解析后的 Markdown 表格内容。

    异常:
        ValueError: 当上传的并非 xlsx 文件，或 openpyxl 无法正确解析该文件时抛出。
    """

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Excel 文件不存在: {path}")

    if path.suffix.lower() != ".xlsx":
        raise ValueError("请上传xlsx格式的表格文件")

    # data_only=True 会读取单元格计算后的值，避免公式字符串干扰规则校验。
    try:
        workbook = load_workbook(filename=path, data_only=True)
    except (InvalidFileException, ValueError) as exc:
        # 当 openpyxl 无法解析该文件时，通常意味着格式不符合预期，这里抛出统一的中文提示。
        raise ValueError("请上传xlsx格式的表格文件") from exc
    sheet = workbook.worksheets[0]

    # Step 1: 预先扫描所有行，按照“有效数据列”统计最大列数，避免依赖不准确的 sheet.max_column。
    max_cols = 0
    required_keywords = {"一级指标", "二级指标", "三级指标"}
    found_keywords = set()
    for raw_row in sheet.iter_rows(values_only=True):
        normalized_row = [clean_text(cell) for cell in raw_row]
        while normalized_row and normalized_row[-1] == "":
            normalized_row.pop()
        for text in normalized_row:
            if text in required_keywords:
                found_keywords.add(text)
        if len(normalized_row) > max_cols:
            max_cols = len(normalized_row)

    if required_keywords - found_keywords:
        raise ValueError("模板格式错误，缺少指标数据（确认文件包含一级指标、二级指标、三级指标）")
    # 先复制 merged_cells.ranges，再遍历，避免在 unmerge 过程中修改原列表导致的迭代问题。
    for merged_range in list(sheet.merged_cells.ranges):
        min_row, min_col, max_row, max_col = (
            merged_range.min_row,
            merged_range.min_col,
            merged_range.max_row,
            merged_range.max_col,
        )
        # 合并区域只有左上角有值，这里需要把左上角的值填充到整个区域，确保扁平化后信息不丢失。
        top_left_value = sheet.cell(row=min_row, column=min_col).value
        sheet.unmerge_cells(str(merged_range))
        for row in range(min_row, max_row + 1):
            for col in range(min_col, max_col + 1):
                sheet.cell(row=row, column=col).value = top_left_value

    processed_rows: List[List[str]] = []
    for row in sheet.iter_rows(values_only=True):
        original_row = [clean_text(cell) for cell in row]

        # 行内去重：必须基于“原始行”的前一个值比较，避免边修改边比较导致 ['A','A','A'] -> ['A','','A'] 的错误。
        cleaned_row: List[str] = []
        for col_index, value in enumerate(original_row):
            if col_index == 0:
                cleaned_row.append(value)
                continue
            prev_original_value = original_row[col_index - 1]
            cleaned_row.append("" if value == prev_original_value else value)

        # 先移除尾部空值，确保“实际列数”最精简，再补齐到 max_cols，保证 Markdown 列宽一致。
        while cleaned_row and cleaned_row[-1] == "":
            cleaned_row.pop()

        if not cleaned_row:
            continue

        if max_cols == 0:
            max_cols = len(cleaned_row)

        while len(cleaned_row) < max_cols:
            cleaned_row.append("")

        processed_rows.append(cleaned_row)

    if not processed_rows:
        return ""

    final_rows: List[List[str]] = []
    for cleaned_row in processed_rows:
        if final_rows and cleaned_row == final_rows[-1]:
            continue
        final_rows.append(cleaned_row)

    if not final_rows:
        return ""

    markdown_lines = ["|" + "|".join(row) + "|" for row in final_rows]

    # Markdown 表格需要在首行（表头）后插入分割线，用于区分表头和主体。
    divider = "|" + "|".join(["---"] * max(max_cols, 1)) + "|"
    markdown_lines.insert(1, divider)

    return "\n".join(markdown_lines)


"""价格审核用到的基础文本与数值归一化工具。"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation


TRUE_SET = {"1", "true", "yes", "y", "是", "含税", "含税价"}
FALSE_SET = {"0", "false", "no", "n", "否", "不含税", "未税"}


def normalize_text(value) -> str:
    """统一文本：去前后空白，并压缩中间连续空白。"""

    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


def normalize_text_no_space(value) -> str:
    """统一文本：移除全部空白，适合规格型号、单位比对。"""

    if value is None:
        return ""
    return re.sub(r"\s+", "", str(value).strip())


def normalize_tax_flag(value, default: bool = True) -> bool:
    """把“是否含税”列宽松解析成布尔值。"""

    if value is None or str(value).strip() == "":
        return default
    text = str(value).strip().lower()
    if text in TRUE_SET:
        return True
    if text in FALSE_SET:
        return False
    return default


def parse_decimal(value) -> Decimal | None:
    """把文本、整数、浮点数宽松解析为 Decimal。"""

    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))

    text = str(value).strip().replace(",", "")
    if not text:
        return None

    text = re.sub(r"[^\d\.\-]", "", text)
    if not text:
        return None

    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def parse_price_range(value):
    """解析区间价格字符串，例如 `285.80-515.00`。"""

    if value is None:
        return None, None

    text = str(value).strip()
    if not text:
        return None, None

    normalized = (
        text.replace("～", "-")
        .replace("—", "-")
        .replace("–", "-")
        .replace("~", "-")
        .replace("至", "-")
    )
    if "-" not in normalized:
        one = parse_decimal(normalized)
        return one, one

    parts = [part.strip() for part in normalized.split("-") if part.strip()]
    if len(parts) < 2:
        one = parse_decimal(parts[0]) if parts else None
        return one, one

    return parse_decimal(parts[0]), parse_decimal(parts[1])

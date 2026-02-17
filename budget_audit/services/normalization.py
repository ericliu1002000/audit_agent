from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re
from typing import Tuple


TRUE_SET = {"1", "true", "yes", "y", "是", "含税", "含税价"}
FALSE_SET = {"0", "false", "no", "n", "否", "不含税", "未税"}


def normalize_text(value) -> str:
    """统一文本：去前后空白、折叠中间空白。"""

    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


def normalize_text_no_space(value) -> str:
    """统一文本：去掉所有空白（适合规格短词对比）。"""

    if value is None:
        return ""
    return re.sub(r"\s+", "", str(value).strip())


def normalize_tax_flag(value, default: bool = True) -> bool:
    """将“是否含税”文本统一为 bool。"""

    if value is None or str(value).strip() == "":
        return default
    text = str(value).strip().lower()
    if text in TRUE_SET:
        return True
    if text in FALSE_SET:
        return False
    return default


def parse_decimal(value) -> Decimal | None:
    """宽松解析数值文本。"""

    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))

    text = str(value).strip().replace(",", "")
    if not text:
        return None

    # 去掉单位后缀，只保留数字符号。
    text = re.sub(r"[^\d\.\-]", "", text)
    if not text:
        return None

    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def parse_price_range(value) -> Tuple[Decimal | None, Decimal | None]:
    """解析区间价格字符串，如 285.80-515.00。"""

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

    parts = [p.strip() for p in normalized.split("-") if p.strip()]
    if len(parts) < 2:
        one = parse_decimal(parts[0]) if parts else None
        return one, one

    low = parse_decimal(parts[0])
    high = parse_decimal(parts[1])
    return low, high


def build_embedding_text(
    material_name: str,
    spec_model: str,
    unit: str,
    is_tax_included: bool,
) -> str:
    """构建向量化文本，固定字段顺序。"""

    tax_label = "含税" if is_tax_included else "不含税"
    return (
        f"材料名称:{normalize_text(material_name)} | "
        f"规格型号:{normalize_text(spec_model)} | "
        f"单位:{normalize_text(unit)} | "
        f"税标识:{tax_label}"
    )


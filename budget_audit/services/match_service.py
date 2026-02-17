from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from budget_audit.models import BudgetPriceItem
from budget_audit.services.excel_parser import parse_vendor_quote_excel
from budget_audit.services.milvus import get_budget_milvus_manager
from budget_audit.services.normalization import build_embedding_text, normalize_text, normalize_text_no_space
from utils.clean_json_string import clean_json_string
from utils.deepseek_client import invoke_deepseek
from utils.extract_text_from_response import extract_text_from_response
from utils.vector_api import call_siliconflow_qwen3_embedding_api

logger = logging.getLogger(__name__)


def _calc_rerank_score(vendor_row: Dict, candidate: BudgetPriceItem, retrieval_score: float):
    score = float(retrieval_score)
    vendor_name = normalize_text_no_space(vendor_row.get("material_name"))
    vendor_spec = normalize_text_no_space(vendor_row.get("spec_model"))
    vendor_unit = normalize_text_no_space(vendor_row.get("unit"))

    candidate_name = normalize_text_no_space(candidate.material_name)
    candidate_spec = normalize_text_no_space(candidate.spec_model)
    candidate_unit = normalize_text_no_space(candidate.unit)

    if vendor_unit and candidate_unit and vendor_unit == candidate_unit:
        score += 0.20
    if candidate.is_tax_included == vendor_row.get("is_tax_included"):
        score += 0.20
    if vendor_spec and candidate_spec and vendor_spec == candidate_spec:
        score += 0.25
    if vendor_name and candidate_name and vendor_name == candidate_name:
        score += 0.20
    elif vendor_name and candidate_name and (
        vendor_name in candidate_name or candidate_name in vendor_name
    ):
        score += 0.10
    return score


def _build_range_text(candidate: BudgetPriceItem) -> str:
    if candidate.price_low is None and candidate.price_high is None:
        return ""
    if candidate.price_low is not None and candidate.price_high is not None:
        return f"{candidate.price_low}-{candidate.price_high}"
    one = candidate.price_low if candidate.price_low is not None else candidate.price_high
    return str(one)


def _judge_candidates_with_deepseek(vendor_row: Dict, candidates: List[Dict]) -> Dict:
    if not candidates:
        return {
            "judgement": "不确定",
            "matched_id": None,
            "reason": "未召回到标准材料候选项。",
            "confidence": 0.0,
            "sentence": "未召回到可比对的政府标准材料，请补充规格/单位/含税口径后重试。",
        }

    payload = {
        "vendor_item": {
            "material_name": vendor_row.get("material_name"),
            "spec_model": vendor_row.get("spec_model"),
            "unit": vendor_row.get("unit"),
            "vendor_price": str(vendor_row.get("vendor_price") or ""),
            "is_tax_included": bool(vendor_row.get("is_tax_included")),
        },
        "candidates": [
            {
                "id": c["id"],
                "material_name": c["material_name"],
                "spec_model": c["spec_model"],
                "unit": c["unit"],
                "base_price": str(c["base_price"]),
                "price_range": c["price_range"],
                "is_tax_included": bool(c["is_tax_included"]),
                "retrieval_score": c["retrieval_score"],
                "rerank_score": c["rerank_score"],
            }
            for c in candidates
        ],
    }

    system_prompt = (
        "你是造价预算审核专家。请在候选标准材料中选择最匹配项，并判断与用户行是否一致。"
        "请只返回 JSON 对象，格式如下："
        "{\"judgement\":\"一致|不一致|不确定\","
        "\"matched_id\":候选id或null,"
        "\"reason\":\"简短原因\","
        "\"confidence\":0到1小数,"
        "\"sentence\":\"一句面向用户的格式化结论\"}。"
        "要求：sentence 默认不强制包含“区间命中/不命中”和“偏差%”，但在价格偏离明显或区间不命中时可以提示。"
        "规格型号、单位、是否含税优先级高于名称语义。"
    )

    try:
        response = invoke_deepseek(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
            max_tokens=800,
        )
        content = extract_text_from_response(response)
        cleaned = clean_json_string(content)
        parsed = json.loads(cleaned) if cleaned else {}
        judgement = str(parsed.get("judgement") or "不确定").strip()
        if judgement not in ("一致", "不一致", "不确定"):
            judgement = "不确定"
        matched_id = parsed.get("matched_id")
        try:
            matched_id = int(matched_id) if matched_id is not None else None
        except (TypeError, ValueError):
            matched_id = None
        confidence_raw = parsed.get("confidence", 0)
        try:
            confidence = max(0.0, min(1.0, float(confidence_raw)))
        except (TypeError, ValueError):
            confidence = 0.0
        sentence = str(
            parsed.get("sentence")
            or parsed.get("summary_sentence")
            or parsed.get("conclusion")
            or ""
        ).strip()
        return {
            "judgement": judgement,
            "matched_id": matched_id,
            "reason": str(parsed.get("reason") or ""),
            "confidence": confidence,
            "sentence": sentence,
        }
    except Exception as exc:  # pragma: no cover - external service instability
        logger.warning("DeepSeek 判断失败: %s", exc, exc_info=True)
        return {
            "judgement": "不确定",
            "matched_id": None,
            "reason": "智能判断服务暂不可用",
            "confidence": 0.0,
            "sentence": "",
        }


def _calc_deviation(vendor_price: Decimal | None, base_price: Decimal | None):
    if vendor_price is None or base_price in (None, Decimal("0")):
        return None
    deviation = ((vendor_price - base_price) / base_price) * Decimal("100")
    return round(float(deviation), 2)


def _calc_in_range(vendor_price: Decimal | None, low: Decimal | None, high: Decimal | None):
    if vendor_price is None:
        return None
    if low is not None and vendor_price < low:
        return False
    if high is not None and vendor_price > high:
        return False
    return True if (low is not None or high is not None) else None


def _get_latest_batch_key() -> Optional[Tuple[str, str]]:
    latest = (
        BudgetPriceItem.objects.order_by("-updated_at")
        .values("region", "publish_month")
        .first()
    )
    if not latest:
        return None
    region = str(latest.get("region") or "").strip()
    publish_month = str(latest.get("publish_month") or "").strip()
    if not region or not publish_month:
        return None
    return region, publish_month


def _build_default_sentence(
    vendor_row: Dict,
    selected: Optional[Dict],
    llm_result: Dict,
    deviation_rate: Optional[float],
    in_range: Optional[bool],
) -> str:
    judgement = str(llm_result.get("judgement") or "不确定").strip() or "不确定"
    reason = str(llm_result.get("reason") or "").strip()

    prefix = "未找到可靠的政府标准匹配项；"
    if selected:
        tax_label = "含税" if selected.get("is_tax_included") else "不含税"
        prefix = (
            f"建议匹配「{selected.get('material_name')}"
            f"{(' ' + selected.get('spec_model')) if selected.get('spec_model') else ''}"
            f"（{selected.get('unit') or '-'}，{tax_label}）」；"
        )

    suffix_parts = [f"结论：{judgement}"]
    if reason:
        suffix_parts.append(f"（{reason}）")

    return prefix + "".join(suffix_parts)


def _build_customer_hints(
    *,
    vendor_row: Dict,
    selected: Optional[Dict],
    llm_result: Dict,
    deviation_rate: Optional[float],
    in_range: Optional[bool],
    candidates: List[Dict],
) -> List[Dict[str, str]]:
    def add(level: str, title: str, detail: str) -> None:
        hints.append({"level": level, "title": title, "detail": detail})

    hints: List[Dict[str, str]] = []
    add("info", "标准清单", "系统默认使用最近一次上传的政府标准价格清单进行比对。")

    if not candidates:
        add(
            "warning",
            "未召回候选",
            "未找到接近的标准材料，建议补充等级/粒径/包装/单位等关键信息后重试。",
        )
        return hints

    judgement = str(llm_result.get("judgement") or "不确定").strip() or "不确定"
    reason_text = str(llm_result.get("reason") or "").strip()
    confidence = llm_result.get("confidence")
    try:
        confidence_value = float(confidence or 0.0)
    except (TypeError, ValueError):
        confidence_value = 0.0

    if reason_text in ("智能判断服务暂不可用",) or "DeepSeek" in reason_text:
        add(
            "warning",
            "智能判断不可用",
            "当前智能判断服务不可用，本次结果仅基于检索与规则提示；可稍后重试或联系管理员。",
        )

    if judgement == "不确定" or confidence_value < 0.6:
        add("warning", "置信度较低", "匹配结果置信度较低，建议人工复核规格、单位与含税口径。")

    if selected:
        vendor_spec = normalize_text_no_space(vendor_row.get("spec_model"))
        cand_spec = normalize_text_no_space(selected.get("spec_model"))
        if vendor_spec and cand_spec and vendor_spec != cand_spec:
            add("warning", "规格敏感", "候选规格与输入不完全一致，材料价格对规格高度敏感，建议重点核对。")

        vendor_unit = normalize_text_no_space(vendor_row.get("unit"))
        cand_unit = normalize_text_no_space(selected.get("unit"))
        if vendor_unit and cand_unit and vendor_unit != cand_unit:
            add("warning", "单位不一致", "单位不一致，可能需要换算后再比较报价与中准价。")

        if selected.get("is_tax_included") != vendor_row.get("is_tax_included"):
            add("warning", "含税口径不同", "含税/不含税口径不同，价格不可直接对比。")

        if in_range is False:
            add("warning", "区间未命中", "报价未落在政府区间价格内，建议复核材料规格或价格口径。")
        elif in_range is True:
            add("info", "区间命中", "报价落在政府区间价格内，可作为合理性参考。")

        if deviation_rate is not None:
            try:
                abs_dev = abs(float(deviation_rate))
            except (TypeError, ValueError):
                abs_dev = None
            if abs_dev is not None and abs_dev >= 30:
                add(
                    "warning",
                    "偏差较大",
                    f"报价相对中准价偏差约 {deviation_rate}% ，建议复核规格/单位/含税口径或是否存在品牌差异。",
                )
            elif abs_dev is not None and abs_dev >= 15:
                add(
                    "info",
                    "存在偏差",
                    f"报价相对中准价偏差约 {deviation_rate}% ，可结合市场情况与合同口径判断。",
                )

    if judgement == "一致" and confidence_value >= 0.8:
        add("info", "结论稳定", "系统认为匹配项一致，可作为审核参考；如遇异常请以业务口径为准。")

    return hints


def audit_single_item(
    *,
    material_name: str,
    spec_model: str = "",
    unit: str = "",
    vendor_price: Decimal | None = None,
    is_tax_included: bool = True,
    top_k: int = 10,
    embedding_timeout: float = 60.0,
) -> Dict[str, Any]:
    """面向前端页面的单条预算审核：召回 Top10 -> DeepSeek 给一句结论。"""

    material_name = normalize_text(material_name)
    spec_model = normalize_text(spec_model)
    unit = normalize_text(unit)

    if not material_name:
        raise ValueError("商品/材料名称不能为空。")
    if vendor_price is None:
        raise ValueError("价格不能为空。")

    if not BudgetPriceItem.objects.exists():
        raise ValueError("尚未导入政府标准价格清单，请先在后台上传标准价格表。")

    vendor_row = {
        "material_name": material_name,
        "spec_model": spec_model,
        "unit": unit,
        "vendor_price": vendor_price,
        "is_tax_included": bool(is_tax_included),
        "embedding_text": build_embedding_text(
            material_name=material_name,
            spec_model=spec_model,
            unit=unit,
            is_tax_included=bool(is_tax_included),
        ),
    }

    vector = call_siliconflow_qwen3_embedding_api(
        vendor_row["embedding_text"], timeout=embedding_timeout
    )
    manager = get_budget_milvus_manager()

    # 先多召回一些，再回表过滤“最新一批”，最后截取 Top10。
    search_limit = max(int(top_k), 1) * 8
    search_limit = max(20, min(search_limit, 100))
    hits = manager.search_candidates(vector, top_k=search_limit)

    candidate_ids = [hit["item_id"] for hit in hits]
    latest_batch = _get_latest_batch_key()
    qs = BudgetPriceItem.objects.filter(id__in=candidate_ids)
    if latest_batch is not None:
        region, publish_month = latest_batch
        qs = qs.filter(region=region, publish_month=publish_month)

    candidate_map = {item.id: item for item in qs}

    ranked_candidates: List[Dict[str, Any]] = []
    for hit in hits:
        candidate = candidate_map.get(hit["item_id"])
        if not candidate:
            continue
        rerank_score = _calc_rerank_score(vendor_row, candidate, hit["score"])
        ranked_candidates.append(
            {
                "id": candidate.id,
                "material_name": candidate.material_name,
                "spec_model": candidate.spec_model or "",
                "unit": candidate.unit or "",
                "base_price": candidate.base_price,
                "price_range": _build_range_text(candidate),
                "is_tax_included": candidate.is_tax_included,
                "price_low": candidate.price_low,
                "price_high": candidate.price_high,
                "retrieval_score": round(float(hit["score"]), 6),
                "rerank_score": round(float(rerank_score), 6),
            }
        )

    ranked_candidates.sort(
        key=lambda c: (c["rerank_score"], c["retrieval_score"]),
        reverse=True,
    )
    ranked_candidates = ranked_candidates[: max(int(top_k), 1)]

    llm_result = _judge_candidates_with_deepseek(vendor_row, ranked_candidates)

    selected = None
    selected_id = llm_result.get("matched_id")
    if selected_id is not None:
        selected = next(
            (
                candidate
                for candidate in ranked_candidates
                if candidate["id"] == selected_id
            ),
            None,
        )
    if selected is None and ranked_candidates:
        selected = ranked_candidates[0]

    deviation_rate = None
    in_range = None
    if selected is not None:
        deviation_rate = _calc_deviation(vendor_row["vendor_price"], selected["base_price"])
        in_range = _calc_in_range(
            vendor_row["vendor_price"], selected["price_low"], selected["price_high"]
        )

    sentence = str(llm_result.get("sentence") or "").strip()
    if not sentence:
        sentence = _build_default_sentence(
            vendor_row, selected, llm_result, deviation_rate, in_range
        )

    hints = _build_customer_hints(
        vendor_row=vendor_row,
        selected=selected,
        llm_result=llm_result,
        deviation_rate=deviation_rate,
        in_range=in_range,
        candidates=ranked_candidates,
    )

    def _serialize_candidate(candidate: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": candidate["id"],
            "material_name": candidate["material_name"],
            "spec_model": candidate.get("spec_model") or "",
            "unit": candidate.get("unit") or "",
            "base_price": str(candidate.get("base_price") or ""),
            "price_range": candidate.get("price_range") or "",
            "is_tax_included": bool(candidate.get("is_tax_included")),
            "retrieval_score": candidate.get("retrieval_score"),
            "rerank_score": candidate.get("rerank_score"),
        }

    matched_item = None
    if selected is not None:
        matched_item = _serialize_candidate(selected)

    return {
        "vendor_item": {
            "material_name": vendor_row["material_name"],
            "spec_model": vendor_row["spec_model"],
            "unit": vendor_row["unit"],
            "vendor_price": str(vendor_row["vendor_price"]),
            "is_tax_included": bool(vendor_row["is_tax_included"]),
        },
        "sentence": sentence,
        "judgement": llm_result.get("judgement") or "不确定",
        "confidence": llm_result.get("confidence") or 0.0,
        "reason": llm_result.get("reason") or "",
        "metrics": {
            "deviation_rate": deviation_rate,
            "in_range": in_range,
        },
        "matched_item": matched_item,
        "hints": hints,
        "candidates": [_serialize_candidate(c) for c in ranked_candidates],
    }


def match_vendor_quote_excel(
    uploaded_file,
    *,
    top_k: int = 3,
    embedding_timeout: float = 60.0,
) -> List[Dict[str, Any]]:
    """将用户报价表与标准价格表进行匹配，并调用 DeepSeek 复核。"""

    vendor_rows = parse_vendor_quote_excel(uploaded_file)
    manager = get_budget_milvus_manager()

    results: List[Dict[str, Any]] = []
    for row in vendor_rows:
        vector = call_siliconflow_qwen3_embedding_api(
            row["embedding_text"], timeout=embedding_timeout
        )
        hits = manager.search_candidates(vector, top_k=top_k)

        candidate_ids = [hit["item_id"] for hit in hits]
        candidate_map = {
            item.id: item for item in BudgetPriceItem.objects.filter(id__in=candidate_ids)
        }

        ranked_candidates: List[Dict[str, Any]] = []
        for hit in hits:
            candidate = candidate_map.get(hit["item_id"])
            if not candidate:
                continue
            rerank_score = _calc_rerank_score(row, candidate, hit["score"])
            ranked_candidates.append(
                {
                    "id": candidate.id,
                    "material_name": candidate.material_name,
                    "spec_model": candidate.spec_model or "",
                    "unit": candidate.unit or "",
                    "base_price": candidate.base_price,
                    "price_range": _build_range_text(candidate),
                    "is_tax_included": candidate.is_tax_included,
                    "price_low": candidate.price_low,
                    "price_high": candidate.price_high,
                    "retrieval_score": round(float(hit["score"]), 6),
                    "rerank_score": round(float(rerank_score), 6),
                }
            )

        ranked_candidates.sort(
            key=lambda c: (c["rerank_score"], c["retrieval_score"]),
            reverse=True,
        )
        ranked_candidates = ranked_candidates[:top_k]

        llm_result = _judge_candidates_with_deepseek(row, ranked_candidates)

        selected = None
        selected_id = llm_result.get("matched_id")
        if selected_id is not None:
            selected = next(
                (candidate for candidate in ranked_candidates if candidate["id"] == selected_id),
                None,
            )
        if selected is None and ranked_candidates:
            selected = ranked_candidates[0]

        deviation_rate = None
        in_range = None
        if selected is not None:
            deviation_rate = _calc_deviation(row["vendor_price"], selected["base_price"])
            in_range = _calc_in_range(
                row["vendor_price"], selected["price_low"], selected["price_high"]
            )

        results.append(
            {
                "row_number": row["row_number"],
                "vendor_material_name": row["material_name"],
                "vendor_spec_model": row["spec_model"],
                "vendor_unit": row["unit"],
                "vendor_price": row["vendor_price"],
                "vendor_is_tax_included": row["is_tax_included"],
                "judgement": llm_result.get("judgement") or "不确定",
                "confidence": llm_result.get("confidence"),
                "reason": llm_result.get("reason") or "",
                "matched_id": selected["id"] if selected else None,
                "matched_material_name": selected["material_name"] if selected else "",
                "matched_spec_model": selected["spec_model"] if selected else "",
                "matched_unit": selected["unit"] if selected else "",
                "matched_base_price": selected["base_price"] if selected else None,
                "matched_price_range": selected["price_range"] if selected else "",
                "matched_is_tax_included": selected["is_tax_included"] if selected else None,
                "retrieval_score": selected["retrieval_score"] if selected else None,
                "rerank_score": selected["rerank_score"] if selected else None,
                "deviation_rate": deviation_rate,
                "in_range": in_range,
                "candidates": ranked_candidates,
            }
        )

    return results

"""Vector-search driven recommendation services for indicators.

本模块封装了指标推荐/资金用途推荐的业务服务，负责串联向量化、Milvus 检索、
数据库补充信息等步骤，因此保持在 services 根目录，与 `utils` 中的工具方法区分。"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Tuple

from django.conf import settings

from indicators.models import FundUsage, Indicator
from indicators.vector_utils import get_milvus_manager
from utils.vector_api import call_begm3_api

TOP_K_INDICATORS = 200
SCORE_THRESHOLD = 0.5
RECOMMENDATION_COUNT = 10


def get_fund_usage_recommendations(user_query: str, province_id: int | None = None):
    """根据用户查询推荐资金用途."""

    user_query = (user_query or "").strip()
    if not user_query:
        return []

    query_vector = call_begm3_api(user_query)
    print("已向量化完成")
    manager = get_milvus_manager()
    search_results = manager.search_similar_indicators(
        query_vector,
        top_k=TOP_K_INDICATORS,
        province_id=province_id,
    )

    filtered_results = [
        item for item in search_results if item["score"] > SCORE_THRESHOLD
    ]

    if not filtered_results:
        return []

    indicator_ids = [item["indicator_id"] for item in filtered_results]
    mapping = dict(
        Indicator.objects.filter(id__in=indicator_ids).values_list("id", "fund_usage_id")
    )

    fund_usage_scores: Dict[int, float] = defaultdict(float)
    fund_usage_indicators: Dict[int, List[int]] = defaultdict(list)
    for item in filtered_results:
        indicator_id = item["indicator_id"]
        fund_usage_id = mapping.get(indicator_id)
        if not fund_usage_id:
            continue
        fund_usage_scores[fund_usage_id] += item["score"]
        fund_usage_indicators[fund_usage_id].append(indicator_id)

    if not fund_usage_scores:
        return []

    sorted_scores = sorted(
        fund_usage_scores.items(), key=lambda kv: kv[1], reverse=True
    )[:RECOMMENDATION_COUNT]
    selected_ids = [fid for fid, _ in sorted_scores]
    fund_usage_map = {fu.id: fu for fu in FundUsage.objects.filter(id__in=selected_ids)}

    recommendations: List[Dict[str, float]] = []
    for fund_usage_id, score in sorted_scores:
        fund_usage = fund_usage_map.get(fund_usage_id)
        if not fund_usage:
            continue
        indicator_filters = {"fund_usage_id": fund_usage_id, "is_active": True}
        if province_id:
            indicator_filters["province_id_id"] = province_id
        indicators_qs = (
            Indicator.all_objects.filter(**indicator_filters)
            .select_related("fund_usage", "province_id")
            .order_by("level_1", "level_2", "level_3")
        )
        indicator_items = [
            {
                "id": indicator.id,
                "business_code": indicator.business_code,
                "fund_usage_id": indicator.fund_usage_id,
                "province_id": indicator.province_id_id,
                "level_1": indicator.level_1,
                "level_2": indicator.level_2,
                "level_3": indicator.level_3,
                "nature": indicator.nature,
                "unit": indicator.unit,
                "explanation": indicator.explanation,
                "is_active": indicator.is_active,
                "source_tag": indicator.source_tag,
            }
            for indicator in indicators_qs
        ]
        recommendations.append(
            {
                "id": fund_usage.id,
                "name": fund_usage.name,
                "province_id": fund_usage.province_id,
                "province_name": fund_usage.province.name if fund_usage.province_id else "",
                "score": round(score, 4),
                "indicators": indicator_items,
            }
        )
    return recommendations

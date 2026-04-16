from __future__ import annotations

import logging
from typing import List

from celery import shared_task
from django.conf import settings

from indicators.models import Indicator
from indicators.vector_utils import get_milvus_manager
from utils.vector_api import call_embedding_api

logger = logging.getLogger(__name__)


def _vectorize_indicator(indicator: Indicator, manager) -> None:
    """将单条有效指标向量化并写入 Milvus。

    步骤：
    1. 调用 Indicator.combo_text() 构建向量化文本。
    2. 请求豆包嵌入服务，拿到 1024 维向量。
    3. 调用 Milvus manager upsert，写入向量。
    4. DB 中将 is_vectorized 标记为 True。
    """
    combo_text = indicator.combo_text()
    existing = manager.get_indicator_record(indicator.id)
    if existing and existing.get("combo_text") == combo_text:
        logger.info("指标 %s 内容未变更，直接复用老向量", indicator.id)
        vector = existing.get("embedding")
    else:
        vector = None

    if not vector:
        vector = call_embedding_api(combo_text)

    expected_dim = int(getattr(settings, "MILVUS_EMBED_DIM", len(vector)))
    if len(vector) != expected_dim:
        raise ValueError(
            f"指标 {indicator.id} 的向量维度 {len(vector)} 与设定 {expected_dim} 不一致"
        )

    manager.upsert_indicator(
        indicator_id=indicator.id,
        province_id=indicator.province_id_id,
        fund_usage_id=indicator.fund_usage_id,
        is_active=True,
        combo_text=combo_text,
        vector=vector,
    )
    Indicator.all_objects.filter(pk=indicator.id).update(is_vectorized=True)
    logger.info("指标 %s 向量化完成", indicator.id)


def _propagate_soft_delete(indicator: Indicator, manager) -> None:
    """将软删除状态同步到 Milvus（仅更新 is_active 标记）。

    软删除后尽量复用原有向量与元数据，避免信息丢失。
    """
    existing = manager.get_indicator_record(indicator.id)
    if existing:
        if not existing.get("is_active"):
            logger.debug("指标 %s 在 Milvus 中已是禁用状态，跳过同步", indicator.id)
            return
        province_id = existing.get("province_id", indicator.province_id_id)
        fund_usage_id = existing.get("fund_usage_id", indicator.fund_usage_id)
        combo_text = existing.get("combo_text") or indicator.combo_text()
        vector = existing.get("embedding") or [0.0] * int(
            getattr(settings, "MILVUS_EMBED_DIM", 1024)
        )
    else:
        province_id = indicator.province_id_id
        fund_usage_id = indicator.fund_usage_id
        combo_text = indicator.combo_text()
        vector = [0.0] * int(getattr(settings, "MILVUS_EMBED_DIM", 1024))

    manager.upsert_indicator(
        indicator_id=indicator.id,
        province_id=province_id,
        fund_usage_id=fund_usage_id,
        is_active=False,
        combo_text=combo_text,
        vector=vector,
    )
    logger.info("指标 %s 已在 Milvus 中标记为禁用", indicator.id)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"countdown": 60},
    max_retries=30,
)
def sync_all_unvectorized(self) -> None:
    """批量同步所有未向量化/已软删除的指标到 Milvus。

    - 第一部分：把 is_active=True 且 is_vectorized=False 的指标全部向量化。
    - 第二部分：把 is_active=False 的指标在 Milvus 中同步成禁用状态。
    - 任务失败会按 Celery 的重试策略（每 60 秒）重复执行。
    """

    manager = get_milvus_manager()

    unvectorized = list(
        Indicator.objects.filter(is_active=True, is_vectorized=False).select_related(
            "fund_usage"
        )
    )
    logger.info("准备向量化 %s 条指标", len(unvectorized))
    for indicator in unvectorized:
        _vectorize_indicator(indicator, manager)

    soft_deleted = list(
        Indicator.all_objects.filter(is_active=False).select_related("fund_usage")
    )
    logger.info("准备同步软删除 %s 条指标", len(soft_deleted))
    for indicator in soft_deleted:
        _propagate_soft_delete(indicator, manager)

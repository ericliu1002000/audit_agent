"""价格审核 Celery 任务。"""

from __future__ import annotations

import logging
from typing import Iterable

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from price_audit.models import GovernmentPriceBatch, GovernmentPriceItem
from price_audit.services.normalization import build_embedding_text
from price_audit.vector_store import get_price_audit_milvus_manager
from utils.vector_api import call_siliconflow_qwen3_embedding_api

logger = logging.getLogger(__name__)


def dispatch_vectorize_government_price_batch(
    batch_id: int,
    deleted_item_ids: Iterable[int] | None = None,
) -> str:
    """提交政府标准价批次向量化任务，并记录排队信息。"""

    deleted_ids = [int(item_id) for item_id in (deleted_item_ids or [])]
    async_result = vectorize_government_price_batch.delay(batch_id, deleted_ids)
    GovernmentPriceBatch.objects.filter(id=batch_id).update(
        vector_task_id=async_result.id,
        vector_queued_at=timezone.now(),
        vector_started_at=None,
        vectorized_at=None,
        last_error="",
        vector_status=GovernmentPriceBatch.VectorStatus.PENDING,
    )
    return async_result.id


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"countdown": 60},
    max_retries=10,
)
def vectorize_government_price_batch(
    self,
    batch_id: int,
    deleted_item_ids: list[int] | None = None,
) -> None:
    """将一个政府标准价批次异步写入 Milvus。"""

    batch = (
        GovernmentPriceBatch.objects.select_related("uploaded_by")
        .prefetch_related("items")
        .get(id=batch_id)
    )
    manager = get_price_audit_milvus_manager()
    deleted_item_ids = [int(item_id) for item_id in (deleted_item_ids or [])]
    if deleted_item_ids:
        manager.delete_items(deleted_item_ids)
    batch.vector_status = GovernmentPriceBatch.VectorStatus.PROCESSING
    batch.vector_task_id = self.request.id or batch.vector_task_id
    batch.vector_started_at = timezone.now()
    pending_items = list(batch.items.filter(is_vectorized=False).order_by("row_no"))
    batch.vector_total = len(pending_items)
    batch.vector_success = 0
    batch.vector_failed = 0
    batch.last_error = ""
    batch.save(
        update_fields=[
            "vector_status",
            "vector_task_id",
            "vector_started_at",
            "vector_total",
            "vector_success",
            "vector_failed",
            "last_error",
            "updated_at",
        ]
    )

    success_count = 0
    failed_count = 0
    last_error = ""
    expected_dim = int(getattr(settings, "MILVUS_EMBED_DIM", 1024))
    processed_count = 0
    reusable_vectors: dict[str, list[float]] = {}
    vectorized_item_ids: list[int] = []

    for item in pending_items:
        try:
            embedding_text = item.embedding_text or build_embedding_text(
                material_name=item.material_name_normalized,
                spec_model=item.spec_model_raw,
                unit=item.unit_raw,
            )
            vector = reusable_vectors.get(embedding_text)
            if not vector:
                existing = manager.get_item_record(item.id)
                if existing and existing.get("embedding_text") == embedding_text:
                    vector = existing.get("embedding")
                if not vector:
                    reusable = manager.find_reusable_vector(embedding_text)
                    if reusable and reusable.get("embedding"):
                        vector = reusable.get("embedding")
                if not vector:
                    vector = call_siliconflow_qwen3_embedding_api(embedding_text)
                reusable_vectors[embedding_text] = list(vector)
            if len(vector) != expected_dim:
                raise ValueError(
                    f"标准价 {item.id} 向量维度 {len(vector)} 与设定 {expected_dim} 不一致"
                )
            manager.upsert_item(
                item_id=item.id,
                batch_id=batch.id,
                year=batch.year,
                region_name=batch.region_name,
                unit=item.unit_normalized,
                embedding_text=embedding_text,
                vector=vector,
            )
            vectorized_item_ids.append(item.id)
            success_count += 1
        except Exception as exc:  # pragma: no cover - depends on runtime services
            failed_count += 1
            last_error = str(exc)
            logger.exception("标准价 %s 向量化失败: %s", item.id, exc)
        finally:
            processed_count += 1
            should_flush_progress = failed_count > 0 or processed_count % 10 == 0
            if should_flush_progress:
                GovernmentPriceBatch.objects.filter(id=batch.id).update(
                    vector_success=success_count,
                    vector_failed=failed_count,
                    last_error=last_error,
                )

    if vectorized_item_ids:
        GovernmentPriceItem.objects.filter(id__in=vectorized_item_ids).update(is_vectorized=True)

    batch.vector_success = success_count
    batch.vector_failed = failed_count
    batch.vectorized_at = timezone.now()
    batch.last_error = last_error
    batch.vector_status = (
        GovernmentPriceBatch.VectorStatus.ACTIVE
        if failed_count == 0
        else GovernmentPriceBatch.VectorStatus.FAILED
    )
    batch.save(
        update_fields=[
            "vector_success",
            "vector_failed",
            "vector_started_at",
            "vectorized_at",
            "last_error",
            "vector_status",
            "updated_at",
        ]
    )

from __future__ import annotations

from celery import shared_task


@shared_task
def vectorize_single_indicator(indicator_id: int) -> None:
    """Placeholder for single indicator vectorization."""
    # TODO: implement Milvus vector sync
    return None


@shared_task
def sync_all_unvectorized() -> None:
    """Placeholder for batch vectorization trigger."""
    # TODO: implement logic to queue vectorize_single_indicator tasks
    return None

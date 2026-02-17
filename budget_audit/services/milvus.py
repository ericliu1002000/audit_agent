from __future__ import annotations

import logging
from typing import Iterable, Optional

from django.conf import settings
from pymilvus import (
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    connections,
    utility,
)

logger = logging.getLogger(__name__)


def get_budget_milvus_manager() -> "BudgetMilvusManager":
    global _budget_milvus_manager
    if _budget_milvus_manager is None:
        _budget_milvus_manager = BudgetMilvusManager()
    return _budget_milvus_manager


class BudgetMilvusManager:
    """预算审核材料向量索引管理。"""

    def __init__(self):
        self.collection_name = getattr(
            settings, "BUDGET_AUDIT_MILVUS_COLLECTION", "budget_material_vector_index"
        )
        self.embedding_dim = int(getattr(settings, "MILVUS_EMBED_DIM", 1024))
        self.alias = "budget_audit_milvus"

        self._connect()
        self.ensure_collection()

    def _connect(self) -> None:
        if connections.has_connection(self.alias):
            return
        connections.connect(
            alias=self.alias,
            host=getattr(settings, "MILVUS_HOST", "127.0.0.1"),
            port=str(getattr(settings, "MILVUS_PORT", "19530")),
            user=getattr(settings, "MILVUS_USER", None),
            password=getattr(settings, "MILVUS_PASSWORD", None),
            db_name=getattr(settings, "MILVUS_DB_NAME", "default"),
        )

    def ensure_collection(self) -> None:
        if not utility.has_collection(self.collection_name, using=self.alias):
            fields = [
                FieldSchema(
                    name="item_id",
                    dtype=DataType.INT64,
                    is_primary=True,
                    auto_id=False,
                ),
                FieldSchema(name="unit", dtype=DataType.VARCHAR, max_length=64),
                FieldSchema(name="is_tax_included", dtype=DataType.BOOL),
                FieldSchema(name="embedding_text", dtype=DataType.VARCHAR, max_length=1024),
                FieldSchema(
                    name="embedding",
                    dtype=DataType.FLOAT_VECTOR,
                    dim=self.embedding_dim,
                ),
            ]
            schema = CollectionSchema(fields, description="Budget audit material vectors")
            Collection(name=self.collection_name, schema=schema, using=self.alias)

        collection = Collection(self.collection_name, using=self.alias)
        index_params = {
            "index_type": "IVF_FLAT",
            "metric_type": "IP",
            "params": {"nlist": 1024},
        }
        collection.create_index("embedding", index_params)

    def get_collection(self) -> Collection:
        return Collection(self.collection_name, using=self.alias)

    def upsert_item(
        self,
        *,
        item_id: int,
        unit: str,
        is_tax_included: bool,
        embedding_text: str,
        vector: Iterable[float],
    ) -> None:
        row = {
            "item_id": int(item_id),
            "unit": str(unit or ""),
            "is_tax_included": bool(is_tax_included),
            "embedding_text": str(embedding_text or ""),
            "embedding": list(vector),
        }
        collection = self.get_collection()
        collection.upsert(data=[row])
        collection.flush()

    def delete_items(self, item_ids: Iterable[int]) -> None:
        ids = [int(item_id) for item_id in item_ids]
        if not ids:
            return
        expr = f"item_id in [{','.join(str(x) for x in ids)}]"
        collection = self.get_collection()
        try:
            collection.delete(expr=expr)
            collection.flush()
        except Exception as exc:  # pragma: no cover - runtime dependencies
            logger.warning("Milvus 删除旧预算审核向量失败: %s", exc)

    def search_candidates(self, query_vector, top_k: int = 3):
        collection = self.get_collection()
        try:
            collection.load()
        except Exception:  # pragma: no cover
            pass

        results = collection.search(
            data=[list(query_vector)],
            anns_field="embedding",
            param={"metric_type": "IP", "params": {"nprobe": 32}},
            limit=max(int(top_k), 1),
            output_fields=["item_id", "unit", "is_tax_included", "embedding_text"],
        )
        hits = results[0] if results else []
        return [
            {
                "item_id": int(hit.entity.get("item_id")),
                "unit": hit.entity.get("unit"),
                "is_tax_included": bool(hit.entity.get("is_tax_included")),
                "embedding_text": hit.entity.get("embedding_text"),
                "score": float(hit.score),
            }
            for hit in hits
        ]


_budget_milvus_manager: Optional[BudgetMilvusManager] = None


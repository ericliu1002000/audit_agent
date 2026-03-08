"""价格审核标准价的 Milvus 访问层。"""

from __future__ import annotations

from typing import Iterable, Optional

from django.conf import settings
from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, connections, utility


def get_price_audit_milvus_manager() -> "PriceAuditMilvusManager":
    global _price_audit_milvus_manager
    if _price_audit_milvus_manager is None:
        _price_audit_milvus_manager = PriceAuditMilvusManager()
    return _price_audit_milvus_manager


class PriceAuditMilvusManager:
    """价格审核标准价向量索引管理。"""

    def __init__(self):
        self.collection_name = getattr(
            settings,
            "PRICE_AUDIT_MILVUS_COLLECTION",
            "price_audit_standard_price_vectors",
        )
        self.embedding_dim = int(getattr(settings, "MILVUS_EMBED_DIM", 1024))
        self.alias = "price_audit_milvus"
        self._connect()

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
        """确保价格审核标准价集合与索引存在。"""

        if not utility.has_collection(self.collection_name, using=self.alias):
            fields = [
                FieldSchema(name="item_id", dtype=DataType.INT64, is_primary=True, auto_id=False),
                FieldSchema(name="batch_id", dtype=DataType.INT64),
                FieldSchema(name="year", dtype=DataType.INT64),
                FieldSchema(name="region_name", dtype=DataType.VARCHAR, max_length=128),
                FieldSchema(name="unit", dtype=DataType.VARCHAR, max_length=64),
                FieldSchema(name="embedding_text", dtype=DataType.VARCHAR, max_length=1024),
                FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=self.embedding_dim),
            ]
            schema = CollectionSchema(fields, description="Price audit standard price vectors")
            Collection(name=self.collection_name, schema=schema, using=self.alias)

        collection = Collection(self.collection_name, using=self.alias)
        index_params = {
            "index_type": "IVF_FLAT",
            "metric_type": "IP",
            "params": {"nlist": 1024},
        }
        if not collection.indexes:
            collection.create_index("embedding", index_params)

    def get_collection(self) -> Collection:
        """获取 collection 对象。"""

        return Collection(self.collection_name, using=self.alias)

    def get_item_record(self, item_id: int):
        """根据 item_id 查询 Milvus 中已存在的标准价向量记录。"""

        collection = self.get_collection()
        try:
            collection.load()
        except Exception:  # pragma: no cover
            pass
        result = collection.query(
            expr=f"item_id == {int(item_id)}",
            output_fields=[
                "batch_id",
                "year",
                "region_name",
                "unit",
                "embedding_text",
                "embedding",
            ],
        )
        return result[0] if result else None

    def find_reusable_vector(self, embedding_text: str):
        """按 embedding_text 查找可直接复用的向量。"""

        if not embedding_text:
            return None

        collection = self.get_collection()
        try:
            collection.load()
        except Exception:  # pragma: no cover
            pass

        escaped_text = embedding_text.replace("\\", "\\\\").replace('"', '\\"')
        result = collection.query(
            expr=f'embedding_text == "{escaped_text}"',
            output_fields=["item_id", "embedding_text", "embedding"],
        )
        return result[0] if result else None

    def upsert_item(
        self,
        *,
        item_id: int,
        batch_id: int,
        year: int,
        region_name: str,
        unit: str,
        embedding_text: str,
        vector: Iterable[float],
    ) -> None:
        """写入或更新一条标准价向量。"""

        row = {
            "item_id": int(item_id),
            "batch_id": int(batch_id),
            "year": int(year),
            "region_name": str(region_name or ""),
            "unit": str(unit or ""),
            "embedding_text": str(embedding_text or ""),
            "embedding": list(vector),
        }
        collection = self.get_collection()
        collection.upsert(data=[row])
        collection.flush()

    def delete_items(self, item_ids: Iterable[int]) -> None:
        """按 item_id 批量删除标准价向量。"""

        ids = [int(item_id) for item_id in item_ids]
        if not ids:
            return
        expr = f"item_id in [{','.join(str(x) for x in ids)}]"
        collection = self.get_collection()
        collection.delete(expr=expr)
        collection.flush()

    def search_candidates(
        self,
        query_vector,
        *,
        batch_id: int,
        top_k: int = 10,
    ):
        """在指定批次内按向量召回候选标准价。"""

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
            expr=f"batch_id == {int(batch_id)}",
            output_fields=["item_id", "batch_id", "year", "region_name", "unit", "embedding_text"],
        )
        hits = results[0] if results else []
        return [
            {
                "item_id": int(hit.entity.get("item_id")),
                "batch_id": int(hit.entity.get("batch_id")),
                "year": int(hit.entity.get("year")),
                "region_name": hit.entity.get("region_name"),
                "unit": hit.entity.get("unit"),
                "embedding_text": hit.entity.get("embedding_text"),
                "score": float(hit.score),
            }
            for hit in hits
        ]


_price_audit_milvus_manager: Optional[PriceAuditMilvusManager] = None

from __future__ import annotations

import logging
from typing import Iterable, List, Optional

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


def get_milvus_manager() -> "MilvusIndicatorManager":
    global _milvus_manager
    if _milvus_manager is None:
        _milvus_manager = MilvusIndicatorManager()
    return _milvus_manager


class MilvusIndicatorManager:
    """负责与 Milvus 通信的简单封装."""

    def __init__(self):
        self.collection_name = getattr(settings, "MILVUS_COLLECTION", "indicator_vectors")
        self.embedding_dim = int(getattr(settings, "MILVUS_EMBED_DIM", 1024))
        self.alias = "indicator_milvus"

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
        """确保集合存在，若不存在则创建."""

        if not utility.has_collection(self.collection_name, using=self.alias):
            fields = [
                FieldSchema(
                    name="indicator_id",
                    dtype=DataType.INT64,
                    is_primary=True,
                    auto_id=False,
                ),
                FieldSchema(name="province_id", dtype=DataType.INT64),
                FieldSchema(name="fund_usage_id", dtype=DataType.INT64),
                FieldSchema(name="is_active", dtype=DataType.BOOL),
                FieldSchema(
                    name="combo_text",
                    dtype=DataType.VARCHAR,
                    max_length=2048,
                ),
                FieldSchema(
                    name="embedding",
                    dtype=DataType.FLOAT_VECTOR,
                    dim=self.embedding_dim,
                ),
            ]
            schema = CollectionSchema(fields, description="Indicator vector store")
            # 在 2.x 版本中通过构造 Collection 来创建集合
            Collection(
                name=self.collection_name,
                schema=schema,
                using=self.alias,
            )

        collection = Collection(self.collection_name, using=self.alias)
        index_params = {
            "index_type": "IVF_FLAT",
            "metric_type": "IP",
            "params": {"nlist": 1024},
        }
        collection.create_index("embedding", index_params)

    def get_collection(self) -> Collection:
        """获取集合对象."""

        return Collection(self.collection_name, using=self.alias)

    def get_indicator_record(self, indicator_id: int):
        """根据主键查询 Milvus 中的记录."""

        collection = self.get_collection()
        try:
            collection.load()
        except Exception:  # pragma: no cover - load may fail if already loaded
            pass
        result = collection.query(
            expr=f"indicator_id == {int(indicator_id)}",
            output_fields=[
                "province_id",
                "fund_usage_id",
                "is_active",
                "combo_text",
                "embedding",
            ],
        )
        return result[0] if result else None

    def upsert_indicator(
        self,
        *,
        indicator_id: int,
        province_id: int,
        fund_usage_id: int,
        is_active: bool,
        combo_text: str,
        vector: Iterable[float],
    ) -> None:
        """插入或更新指标向量."""

        row = {
            "indicator_id": int(indicator_id),
            "province_id": int(province_id),
            "fund_usage_id": int(fund_usage_id),
            "is_active": bool(is_active),
            "combo_text": str(combo_text),
            "embedding": list(vector),
        }
        collection = self.get_collection()
        try:
            # upsert_rows 接口期望按“行”传入数据
            collection.upsert(data=[row])
            collection.flush()
        except Exception as exc:  # pragma: no cover - depends on Milvus runtime
            logger.exception("Failed to upsert indicator %s into Milvus: %s", indicator_id, exc)
            raise


_milvus_manager: Optional[MilvusIndicatorManager] = None

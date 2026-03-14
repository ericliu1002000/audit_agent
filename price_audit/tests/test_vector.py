"""价格审核向量相关测试。"""

from unittest.mock import Mock
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from price_audit.models import GovernmentPriceBatch, GovernmentPriceItem
from price_audit.tasks import (
    dispatch_vectorize_government_price_batch,
    vectorize_government_price_batch,
)
from price_audit.vector_store import PriceAuditMilvusManager


class EnsureVectorCollectionsCommandTests(TestCase):
    """验证统一向量初始化命令会调用各业务 manager。"""

    @patch("api.management.commands.ensure_vector_collections.get_price_audit_milvus_manager")
    @patch("api.management.commands.ensure_vector_collections.get_milvus_manager")
    def test_ensure_vector_collections(self, indicator_getter, price_getter):
        indicator_manager = indicator_getter.return_value
        price_manager = price_getter.return_value
        indicator_manager.collection_name = "indicator_vectors"
        price_manager.collection_name = "price_vectors"

        call_command("ensure_vector_collections")

        indicator_manager.ensure_collection.assert_called_once_with()
        price_manager.ensure_collection.assert_called_once_with()


class PriceAuditMilvusManagerTests(TestCase):
    @patch("price_audit.vector_store.Collection")
    def test_get_collection_does_not_auto_ensure_collection(self, collection_cls):
        manager = PriceAuditMilvusManager.__new__(PriceAuditMilvusManager)
        manager.collection_name = "price_vectors"
        manager.alias = "price_audit_milvus"
        manager.ensure_collection = Mock()

        PriceAuditMilvusManager.get_collection(manager)

        manager.ensure_collection.assert_not_called()
        collection_cls.assert_called_once_with("price_vectors", using="price_audit_milvus")


class DispatchVectorizationTaskTests(TestCase):
    """验证批次入队后会记录 Celery 任务元数据。"""

    def test_dispatch_updates_batch_queue_metadata(self):
        batch = GovernmentPriceBatch.objects.create(
            region_name="天津",
            year=2026,
            total_rows=1,
            success_rows=1,
        )
        fake_result = Mock(id="task-123")

        with patch(
            "price_audit.tasks.vectorize_government_price_batch.delay",
            return_value=fake_result,
        ) as delay_mock:
            task_id = dispatch_vectorize_government_price_batch(batch.id)

        batch.refresh_from_db()
        self.assertEqual(task_id, "task-123")
        self.assertEqual(batch.vector_task_id, "task-123")
        self.assertEqual(batch.vector_status, GovernmentPriceBatch.VectorStatus.PENDING)
        self.assertIsNotNone(batch.vector_queued_at)
        self.assertLessEqual(batch.vector_queued_at, timezone.now())
        delay_mock.assert_called_once_with(batch.id, [])


class VectorizationReuseTests(TestCase):
    """验证标准价向量化会优先复用已存在向量。"""

    @patch("price_audit.tasks.call_siliconflow_qwen3_embedding_api")
    @patch("price_audit.tasks.get_price_audit_milvus_manager")
    def test_vectorize_reuses_existing_vector_by_embedding_text(
        self,
        manager_getter,
        embed_mock,
    ):
        batch = GovernmentPriceBatch.objects.create(
            region_name="天津",
            year=2026,
            total_rows=1,
            success_rows=1,
        )
        item = GovernmentPriceItem.objects.create(
            batch=batch,
            row_no=2,
            material_name_raw="矿渣硅酸盐水泥",
            material_name_normalized="矿渣硅酸盐水泥",
            spec_model_raw="32.5级 散装",
            spec_model_normalized="32.5级散装",
            unit_raw="t",
            unit_normalized="t",
            benchmark_price="379.42",
            embedding_text="材料名称:矿渣硅酸盐水泥 | 规格型号:32.5级 散装 | 单位:t",
            is_vectorized=False,
            raw_row_data={},
        )
        manager = manager_getter.return_value
        manager.get_item_record.return_value = None
        manager.find_reusable_vector.return_value = {
            "item_id": 999,
            "embedding_text": item.embedding_text,
            "embedding": [0.1, 0.2, 0.3, 0.4],
        }

        with patch("price_audit.tasks.settings", Mock(MILVUS_EMBED_DIM=4)):
            vectorize_government_price_batch.apply(args=[batch.id, []], throw=True)

        embed_mock.assert_not_called()
        manager.upsert_item.assert_called_once()
        item.refresh_from_db()
        self.assertTrue(item.is_vectorized)

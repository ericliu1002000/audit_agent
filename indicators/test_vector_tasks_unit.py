import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "audit_agent.settings")

import django

django.setup()

from indicators import tasks as vector_tasks


class VectorTasksUnitTests(unittest.TestCase):
    def _build_indicator(self):
        indicator = Mock()
        indicator.id = 101
        indicator.province_id_id = 31
        indicator.fund_usage_id = 5
        indicator.combo_text.return_value = "信息化建设-设备采购数量-不低于20台"
        return indicator

    def test_vectorize_indicator_reuses_existing_vector(self):
        indicator = self._build_indicator()
        manager = Mock()
        manager.get_indicator_record.return_value = {
            "combo_text": indicator.combo_text.return_value,
            "embedding": [0.1, 0.2],
        }

        with patch.object(
            vector_tasks, "settings", SimpleNamespace(MILVUS_EMBED_DIM=2)
        ), patch.object(vector_tasks, "call_begm3_api") as mock_embed, patch.object(
            vector_tasks, "Indicator"
        ) as mock_indicator_model:
            vector_tasks._vectorize_indicator(indicator, manager)

        mock_embed.assert_not_called()
        manager.upsert_indicator.assert_called_once_with(
            indicator_id=101,
            province_id=31,
            fund_usage_id=5,
            is_active=True,
            combo_text=indicator.combo_text.return_value,
            vector=[0.1, 0.2],
        )
        mock_indicator_model.all_objects.filter.assert_called_once_with(pk=101)
        mock_indicator_model.all_objects.filter.return_value.update.assert_called_once_with(
            is_vectorized=True
        )

    def test_vectorize_indicator_calls_embedding_when_no_reusable_vector(self):
        indicator = self._build_indicator()
        manager = Mock()
        manager.get_indicator_record.return_value = None

        with patch.object(
            vector_tasks, "settings", SimpleNamespace(MILVUS_EMBED_DIM=2)
        ), patch.object(
            vector_tasks, "call_begm3_api", return_value=[0.3, 0.4]
        ) as mock_embed, patch.object(vector_tasks, "Indicator"):
            vector_tasks._vectorize_indicator(indicator, manager)

        mock_embed.assert_called_once_with(indicator.combo_text.return_value)
        manager.upsert_indicator.assert_called_once_with(
            indicator_id=101,
            province_id=31,
            fund_usage_id=5,
            is_active=True,
            combo_text=indicator.combo_text.return_value,
            vector=[0.3, 0.4],
        )

    def test_vectorize_indicator_raises_on_dim_mismatch(self):
        indicator = self._build_indicator()
        manager = Mock()
        manager.get_indicator_record.return_value = None

        with patch.object(
            vector_tasks, "settings", SimpleNamespace(MILVUS_EMBED_DIM=3)
        ), patch.object(
            vector_tasks, "call_begm3_api", return_value=[0.3, 0.4]
        ), patch.object(vector_tasks, "Indicator"):
            with self.assertRaises(ValueError) as ctx:
                vector_tasks._vectorize_indicator(indicator, manager)

        self.assertIn("向量维度", str(ctx.exception))
        manager.upsert_indicator.assert_not_called()

    def test_propagate_soft_delete_skips_when_already_inactive(self):
        indicator = self._build_indicator()
        manager = Mock()
        manager.get_indicator_record.return_value = {"is_active": False}

        with patch.object(
            vector_tasks, "settings", SimpleNamespace(MILVUS_EMBED_DIM=2)
        ):
            vector_tasks._propagate_soft_delete(indicator, manager)

        manager.upsert_indicator.assert_not_called()

    def test_propagate_soft_delete_reuses_existing_vector(self):
        indicator = self._build_indicator()
        manager = Mock()
        manager.get_indicator_record.return_value = {
            "is_active": True,
            "province_id": 31,
            "fund_usage_id": 5,
            "combo_text": "旧组合文本",
            "embedding": [0.6, 0.7],
        }

        with patch.object(
            vector_tasks, "settings", SimpleNamespace(MILVUS_EMBED_DIM=2)
        ):
            vector_tasks._propagate_soft_delete(indicator, manager)

        manager.upsert_indicator.assert_called_once_with(
            indicator_id=101,
            province_id=31,
            fund_usage_id=5,
            is_active=False,
            combo_text="旧组合文本",
            vector=[0.6, 0.7],
        )


if __name__ == "__main__":
    unittest.main()

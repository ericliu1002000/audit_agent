import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "audit_agent.settings")

import django

django.setup()

from indicators.vector_utils import MilvusIndicatorManager


class IndicatorMilvusManagerUnitTests(unittest.TestCase):
    @patch("indicators.vector_utils.Collection")
    def test_get_collection_does_not_auto_ensure_collection(self, collection_cls):
        manager = MilvusIndicatorManager.__new__(MilvusIndicatorManager)
        manager.collection_name = "indicator_vectors"
        manager.alias = "indicator_milvus"
        manager.ensure_collection = Mock()

        MilvusIndicatorManager.get_collection(manager)

        manager.ensure_collection.assert_not_called()
        collection_cls.assert_called_once_with("indicator_vectors", using="indicator_milvus")

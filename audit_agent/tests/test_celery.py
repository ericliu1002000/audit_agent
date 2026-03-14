from django.test import SimpleTestCase
from unittest.mock import patch

from audit_agent.celery import bootstrap_milvus_collections_on_worker_ready


class CeleryStartupTests(SimpleTestCase):
    @patch("audit_agent.celery.call_command")
    def test_worker_ready_bootstraps_vector_collections(self, call_command_mock):
        bootstrap_milvus_collections_on_worker_ready()

        call_command_mock.assert_called_once_with("ensure_vector_collections")

    @patch("audit_agent.celery.call_command", side_effect=RuntimeError("milvus unavailable"))
    def test_worker_ready_propagates_bootstrap_failures(self, call_command_mock):
        with self.assertRaisesMessage(RuntimeError, "milvus unavailable"):
            bootstrap_milvus_collections_on_worker_ready()

        call_command_mock.assert_called_once_with("ensure_vector_collections")

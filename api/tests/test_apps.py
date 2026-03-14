"""API 应用启动测试。"""

import api

from django.test import SimpleTestCase
from unittest.mock import patch

from api.apps import ApiConfig


class ApiConfigReadyTests(SimpleTestCase):
    def _build_config(self):
        return ApiConfig("api", api)

    @patch("api.apps.call_command")
    @patch("api.apps.sys.argv", ["manage.py", "runserver"])
    def test_ready_bootstraps_vector_collections(self, call_command_mock):
        self._build_config().ready()

        call_command_mock.assert_called_once_with("ensure_vector_collections")

    @patch("api.apps.logger")
    @patch("api.apps.call_command", side_effect=RuntimeError("milvus unavailable"))
    @patch("api.apps.sys.argv", ["manage.py", "runserver"])
    def test_ready_logs_and_swallows_bootstrap_failures(self, call_command_mock, logger_mock):
        self._build_config().ready()

        call_command_mock.assert_called_once_with("ensure_vector_collections")
        logger_mock.warning.assert_called_once()

    @patch("api.apps.call_command")
    @patch("api.apps.sys.argv", ["manage.py", "ensure_vector_collections"])
    def test_ready_skips_bootstrap_for_ensure_command(self, call_command_mock):
        self._build_config().ready()

        call_command_mock.assert_not_called()

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests

from utils import vector_api


class SiliconFlowEmbeddingApiTests(unittest.TestCase):
    def _mock_settings(self, **extra):
        defaults = {
            "SILICONFLOW_API_EMBEDDING_URL": "https://api.siliconflow.cn/v1/embeddings",
            "SILICONFLOW_API_KEY": "test-key",
            "SILICONFLOW_EMBEDDING_MODEL": vector_api.SILICONFLOW_DEFAULT_EMBEDDING_MODEL,
            "MILVUS_EMBED_DIM": 4,
            "SILICONFLOW_USE_ENV_PROXY": False,
            "SILICONFLOW_HTTP_PROXY": "",
            "SILICONFLOW_HTTPS_PROXY": "",
        }
        defaults.update(extra)
        return patch.object(vector_api, "settings", SimpleNamespace(**defaults))

    @patch("utils.vector_api.requests.Session")
    def test_call_siliconflow_qwen3_embedding_api_success(self, mock_session_cls):
        response = Mock(status_code=200)
        response.json.return_value = {"data": [{"embedding": [0.1, 0.2, 0.3, 0.4]}]}
        session = Mock()
        session.post.return_value = response
        mock_session_cls.return_value = session

        with self._mock_settings():
            vector = vector_api.call_siliconflow_qwen3_embedding_api(
                "hello world", timeout=12.0
            )

        self.assertEqual(vector, [0.1, 0.2, 0.3, 0.4])
        self.assertFalse(session.trust_env)
        session.post.assert_called_once_with(
            "https://api.siliconflow.cn/v1/embeddings",
            json={
                "model": vector_api.SILICONFLOW_DEFAULT_EMBEDDING_MODEL,
                "input": "hello world",
            },
            headers={
                "Authorization": "Bearer test-key",
                "Content-Type": "application/json",
            },
            timeout=12.0,
            proxies=None,
        )
        session.close.assert_called_once_with()

    @patch("utils.vector_api.requests.Session")
    def test_call_siliconflow_qwen3_embedding_api_http_error(self, mock_session_cls):
        response = Mock(status_code=401)
        response.text = "invalid token"
        session = Mock()
        session.post.return_value = response
        mock_session_cls.return_value = session

        with self._mock_settings():
            with self.assertRaises(RuntimeError) as ctx:
                vector_api.call_siliconflow_qwen3_embedding_api("hello world")

        self.assertIn("HTTP 401", str(ctx.exception))

    @patch("utils.vector_api.requests.Session")
    def test_call_siliconflow_qwen3_embedding_api_request_exception(self, mock_session_cls):
        session = Mock()
        session.post.side_effect = requests.RequestException("network down")
        mock_session_cls.return_value = session

        with self._mock_settings():
            with self.assertRaises(RuntimeError) as ctx:
                vector_api.call_siliconflow_qwen3_embedding_api("hello world")

        self.assertIn("调用硅基流动嵌入服务失败", str(ctx.exception))

    @patch("utils.vector_api.requests.Session")
    def test_call_siliconflow_qwen3_embedding_api_dim_mismatch(self, mock_session_cls):
        response = Mock(status_code=200)
        response.json.return_value = {"data": [{"embedding": [0.1, 0.2, 0.3]}]}
        session = Mock()
        session.post.return_value = response
        mock_session_cls.return_value = session

        with self._mock_settings():
            with self.assertRaises(ValueError) as ctx:
                vector_api.call_siliconflow_qwen3_embedding_api("hello world")

        self.assertIn("维度不匹配", str(ctx.exception))

    @patch("utils.vector_api.requests.Session")
    def test_call_siliconflow_qwen3_embedding_api_uses_explicit_proxy(self, mock_session_cls):
        response = Mock(status_code=200)
        response.json.return_value = {"data": [{"embedding": [0.1, 0.2, 0.3, 0.4]}]}
        session = Mock()
        session.post.return_value = response
        mock_session_cls.return_value = session

        with self._mock_settings(
            SILICONFLOW_HTTP_PROXY="http://proxy.local:8080",
            SILICONFLOW_HTTPS_PROXY="http://proxy.local:8443",
        ):
            vector_api.call_siliconflow_qwen3_embedding_api("hello world")

        session.post.assert_called_once_with(
            "https://api.siliconflow.cn/v1/embeddings",
            json={
                "model": vector_api.SILICONFLOW_DEFAULT_EMBEDDING_MODEL,
                "input": "hello world",
            },
            headers={
                "Authorization": "Bearer test-key",
                "Content-Type": "application/json",
            },
            timeout=60.0,
            proxies={
                "http": "http://proxy.local:8080",
                "https": "http://proxy.local:8443",
            },
        )

    @patch("utils.vector_api.requests.Session")
    def test_call_siliconflow_qwen3_embedding_api_can_use_env_proxy(self, mock_session_cls):
        response = Mock(status_code=200)
        response.json.return_value = {"data": [{"embedding": [0.1, 0.2, 0.3, 0.4]}]}
        session = Mock()
        session.post.return_value = response
        mock_session_cls.return_value = session

        with self._mock_settings(SILICONFLOW_USE_ENV_PROXY=True):
            vector_api.call_siliconflow_qwen3_embedding_api("hello world")

        self.assertTrue(session.trust_env)

    def test_call_siliconflow_qwen3_embedding_api_missing_config(self):
        with self._mock_settings(SILICONFLOW_API_EMBEDDING_URL="", SILICONFLOW_API_KEY=""):
            with self.assertRaises(RuntimeError) as ctx:
                vector_api.call_siliconflow_qwen3_embedding_api("hello world")

        self.assertIn("配置未完成", str(ctx.exception))

    @patch("utils.vector_api.call_siliconflow_qwen3_embedding_api")
    def test_call_embedding_api_delegates_to_siliconflow(self, mock_call):
        mock_call.return_value = [0.9, 0.8]

        vector = vector_api.call_embedding_api("统一入口")

        self.assertEqual(vector, [0.9, 0.8])
        mock_call.assert_called_once_with("统一入口", timeout=60.0)

    @patch("utils.vector_api.call_siliconflow_qwen3_embedding_api")
    def test_call_begm3_api_is_compatibility_wrapper(self, mock_call):
        mock_call.return_value = [0.5, 0.6]

        vector = vector_api.call_begm3_api("兼容入口", timeout=15.0)

        self.assertEqual(vector, [0.5, 0.6])
        mock_call.assert_called_once_with("兼容入口", timeout=15.0)


if __name__ == "__main__":
    unittest.main()

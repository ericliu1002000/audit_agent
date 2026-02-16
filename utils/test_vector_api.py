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
        }
        defaults.update(extra)
        return patch.object(vector_api, "settings", SimpleNamespace(**defaults))

    @patch("utils.vector_api.requests.post")
    def test_call_siliconflow_qwen3_embedding_api_success(self, mock_post):
        response = Mock(status_code=200)
        response.json.return_value = {"data": [{"embedding": [0.1, 0.2, 0.3, 0.4]}]}
        mock_post.return_value = response

        with self._mock_settings():
            vector = vector_api.call_siliconflow_qwen3_embedding_api(
                "hello world", timeout=12.0
            )

        self.assertEqual(vector, [0.1, 0.2, 0.3, 0.4])
        mock_post.assert_called_once_with(
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
        )

    @patch("utils.vector_api.requests.post")
    def test_call_siliconflow_qwen3_embedding_api_http_error(self, mock_post):
        response = Mock(status_code=401)
        response.text = "invalid token"
        mock_post.return_value = response

        with self._mock_settings():
            with self.assertRaises(RuntimeError) as ctx:
                vector_api.call_siliconflow_qwen3_embedding_api("hello world")

        self.assertIn("HTTP 401", str(ctx.exception))

    @patch("utils.vector_api.requests.post")
    def test_call_siliconflow_qwen3_embedding_api_request_exception(self, mock_post):
        mock_post.side_effect = requests.RequestException("network down")

        with self._mock_settings():
            with self.assertRaises(RuntimeError) as ctx:
                vector_api.call_siliconflow_qwen3_embedding_api("hello world")

        self.assertIn("调用硅基流动嵌入服务失败", str(ctx.exception))

    @patch("utils.vector_api.requests.post")
    def test_call_siliconflow_qwen3_embedding_api_dim_mismatch(self, mock_post):
        response = Mock(status_code=200)
        response.json.return_value = {"data": [{"embedding": [0.1, 0.2, 0.3]}]}
        mock_post.return_value = response

        with self._mock_settings():
            with self.assertRaises(ValueError) as ctx:
                vector_api.call_siliconflow_qwen3_embedding_api("hello world")

        self.assertIn("维度不匹配", str(ctx.exception))

    def test_call_siliconflow_qwen3_embedding_api_missing_config(self):
        with self._mock_settings(SILICONFLOW_API_EMBEDDING_URL="", SILICONFLOW_API_KEY=""):
            with self.assertRaises(RuntimeError) as ctx:
                vector_api.call_siliconflow_qwen3_embedding_api("hello world")

        self.assertIn("配置未完成", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

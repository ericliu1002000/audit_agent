import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests

from utils import vector_api


class VolcengineEmbeddingApiTests(unittest.TestCase):
    def _mock_settings(self, **extra):
        defaults = {
            "VOLCENGINE_KEY": "test-key",
            "VOLCENGINE_VISION_MODEL_ID": "doubao-embedding-vision-251215",
            "MILVUS_EMBED_DIM": 4,
        }
        defaults.update(extra)
        return patch.object(vector_api, "settings", SimpleNamespace(**defaults))

    @patch("utils.vector_api.requests.post")
    def test_call_volcengine_embedding_api_success(self, mock_post):
        response = Mock(status_code=200)
        response.json.return_value = {"data": [{"embedding": [0.1, 0.2, 0.3, 0.4]}]}
        mock_post.return_value = response

        with self._mock_settings():
            vector = vector_api.call_volcengine_embedding_api("hello world", timeout=12.0)

        self.assertEqual(vector, [0.1, 0.2, 0.3, 0.4])
        mock_post.assert_called_once_with(
            vector_api.VOLCENGINE_EMBEDDING_URL,
            json={
                "model": "doubao-embedding-vision-251215",
                "input": [{"type": "text", "text": "hello world"}],
                "dimensions": 4,
                "encoding_format": "float",
            },
            headers={
                "Authorization": "Bearer test-key",
                "Content-Type": "application/json",
            },
            timeout=12.0,
        )

    @patch("utils.vector_api.requests.post")
    def test_call_volcengine_embedding_api_http_error(self, mock_post):
        response = Mock(status_code=401)
        response.text = "invalid token"
        mock_post.return_value = response

        with self._mock_settings():
            with self.assertRaises(RuntimeError) as ctx:
                vector_api.call_volcengine_embedding_api("hello world")

        self.assertIn("HTTP 401", str(ctx.exception))

    @patch("utils.vector_api.requests.post")
    def test_call_volcengine_embedding_api_request_exception(self, mock_post):
        mock_post.side_effect = requests.RequestException("network down")

        with self._mock_settings():
            with self.assertRaises(RuntimeError) as ctx:
                vector_api.call_volcengine_embedding_api("hello world")

        self.assertIn("调用豆包嵌入服务失败", str(ctx.exception))

    @patch("utils.vector_api.requests.post")
    def test_call_volcengine_embedding_api_dim_mismatch(self, mock_post):
        response = Mock(status_code=200)
        response.json.return_value = {"data": [{"embedding": [0.1, 0.2, 0.3]}]}
        mock_post.return_value = response

        with self._mock_settings():
            with self.assertRaises(ValueError) as ctx:
                vector_api.call_volcengine_embedding_api("hello world")

        self.assertIn("维度不匹配", str(ctx.exception))

    def test_call_volcengine_embedding_api_missing_config(self):
        with self._mock_settings(VOLCENGINE_KEY="", VOLCENGINE_VISION_MODEL_ID=""):
            with self.assertRaises(RuntimeError) as ctx:
                vector_api.call_volcengine_embedding_api("hello world")

        self.assertIn("配置未完成", str(ctx.exception))

    @patch("utils.vector_api.call_volcengine_embedding_api")
    def test_call_embedding_api_delegates_to_volcengine(self, mock_call):
        mock_call.return_value = [0.9, 0.8]

        vector = vector_api.call_embedding_api("统一入口")

        self.assertEqual(vector, [0.9, 0.8])
        mock_call.assert_called_once_with("统一入口", timeout=60.0)

    @patch("utils.vector_api.call_embedding_api")
    def test_call_begm3_api_is_compatibility_wrapper(self, mock_call):
        mock_call.return_value = [0.5, 0.6]

        vector = vector_api.call_begm3_api("兼容入口", timeout=15.0)

        self.assertEqual(vector, [0.5, 0.6])
        mock_call.assert_called_once_with("兼容入口", timeout=15.0)


if __name__ == "__main__":
    unittest.main()

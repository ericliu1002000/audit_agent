import os
import sys
import types
import unittest
from unittest.mock import Mock, patch

from utils.deepseek_client import invoke_deepseek


class InvokeDeepSeekTests(unittest.TestCase):
    @patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"}, clear=False)
    @patch("utils.deepseek_client.load_dotenv")
    def test_invoke_deepseek_uses_chat_completions_even_if_responses_exists(
        self, load_dotenv_mock
    ):
        responses_api = Mock()
        chat_create = Mock(return_value="ok")
        client = Mock()
        client.responses = responses_api
        client.chat.completions.create = chat_create

        openai_module = types.ModuleType("openai")
        openai_module.OpenAI = Mock(return_value=client)

        with patch.dict(sys.modules, {"openai": openai_module}):
            result = invoke_deepseek(
                [
                    {"role": "system", "content": "system"},
                    {"role": "user", "content": "hello"},
                ],
                response_format={"type": "json_object"},
                max_tokens=123,
            )

        self.assertEqual(result, "ok")
        responses_api.create.assert_not_called()
        chat_create.assert_called_once_with(
            model="deepseek-chat",
            temperature=0.1,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "system"},
                {"role": "user", "content": "hello"},
            ],
            max_tokens=123,
        )
        load_dotenv_mock.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()

"""LlamaIndex runtime 兼容性测试。"""

from __future__ import annotations

import os
from unittest.mock import patch

from django.test import SimpleTestCase
from pydantic import BaseModel

from utils.agent_runtime.llm import build_deepseek_llm
from utils.agent_runtime.runtime import run_function_agent


class _Output(BaseModel):
    value: str


class _Handler:
    def __init__(self, result):
        self._result = result

    def __await__(self):
        async def _wait():
            return self._result

        return _wait().__await__()


class AgentRuntimeTests(SimpleTestCase):
    """验证 FunctionAgent 运行时包装。"""

    @patch("utils.agent_runtime.runtime.build_deepseek_llm", return_value="fake-llm")
    @patch("llama_index.core.tools.FunctionTool.from_defaults", side_effect=lambda fn: fn)
    @patch("llama_index.core.agent.workflow.FunctionAgent")
    def test_run_function_agent_awaits_workflow_handler_result(
        self,
        agent_cls,
        _tool_mock,
        _llm_mock,
    ):
        """新版 workflow runtime 返回 handler 时，应在事件循环中 await 结果。"""

        agent = agent_cls.return_value
        agent.run.return_value = _Handler(_Output(value="ok"))

        result = run_function_agent(
            system_prompt="system",
            user_prompt="user",
            tools=[lambda: {"ok": True}],
            output_cls=_Output,
        )

        self.assertEqual(result.value, "ok")
        agent.run.assert_called_once_with(user_msg="user")

    @patch("utils.agent_runtime.runtime.build_deepseek_llm", return_value="fake-llm")
    @patch("llama_index.core.tools.FunctionTool.from_defaults", side_effect=lambda fn: fn)
    @patch("llama_index.core.agent.workflow.FunctionAgent")
    def test_run_function_agent_coerces_structured_response_dict(
        self,
        agent_cls,
        _tool_mock,
        _llm_mock,
    ):
        """workflow 若返回带 structured_response 的对象，也应转成目标模型。"""

        agent = agent_cls.return_value

        class _Result:
            structured_response = {"value": "ok-from-dict"}

        agent.run.return_value = _Handler(_Result())

        result = run_function_agent(
            system_prompt="system",
            user_prompt="user",
            tools=[lambda: {"ok": True}],
            output_cls=_Output,
        )

        self.assertEqual(result.value, "ok-from-dict")

    @patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"}, clear=False)
    @patch("llama_index.llms.deepseek.DeepSeek")
    def test_build_deepseek_llm_disables_async_client_reuse(self, deepseek_cls):
        """短生命周期 loop 场景下禁用 async client 复用，避免回收期事件循环报错。"""

        build_deepseek_llm()

        self.assertFalse(deepseek_cls.call_args.kwargs["reuse_client"])

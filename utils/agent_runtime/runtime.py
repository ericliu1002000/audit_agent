"""LlamaIndex FunctionAgent 运行时封装。"""

from __future__ import annotations

import asyncio
from typing import Callable, Iterable, Type

from pydantic import BaseModel

from utils.agent_runtime.llm import build_deepseek_llm


def _run_async(coro):
    """在同步上下文里安全执行协程。"""

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def run_function_agent(
    *,
    system_prompt: str,
    user_prompt: str,
    tools: Iterable[Callable],
    output_cls: Type[BaseModel],
):
    """运行一次带工具调用的 FunctionAgent。"""

    try:
        from llama_index.core.agent.workflow import FunctionAgent
        from llama_index.core.tools import FunctionTool
    except ImportError as exc:  # pragma: no cover - 依赖由运行环境决定
        raise RuntimeError(
            "未安装 LlamaIndex 依赖，请安装 llama-index 与 llama-index-llms-deepseek。"
        ) from exc

    llm = build_deepseek_llm()
    agent = FunctionAgent(
        tools=[FunctionTool.from_defaults(fn=tool) for tool in tools],
        llm=llm,
        system_prompt=system_prompt,
        output_cls=output_cls,
    )
    result = _run_async(agent.run(user_msg=user_prompt))
    if hasattr(result, "structured_response") and result.structured_response is not None:
        return result.structured_response
    if isinstance(result, output_cls):
        return result
    return output_cls.model_validate_json(str(result))

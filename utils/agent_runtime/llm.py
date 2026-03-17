"""LlamaIndex LLM 工厂。"""

from __future__ import annotations

import os


def build_deepseek_llm():
    """构造 DeepSeek 的 LlamaIndex LLM。"""

    try:
        from llama_index.llms.deepseek import DeepSeek
    except ImportError as exc:  # pragma: no cover - 依赖由运行环境决定
        raise RuntimeError(
            "未安装 LlamaIndex DeepSeek 依赖，请安装 llama-index 与 llama-index-llms-deepseek。"
        ) from exc

    api_key = (os.getenv("DEEPSEEK_API_KEY") or "").strip()
    if not api_key:
        raise ValueError("未配置 DEEPSEEK_API_KEY，无法运行价格审核智能体。")

    model = (os.getenv("DEEPSEEK_MODEL") or "deepseek-chat").strip()
    return DeepSeek(
        model=model,
        api_key=api_key,
        temperature=0.1,
        # Celery worker 中每次审核都通过 asyncio.run() 驱动一个短生命周期事件循环。
        # 关闭 async client 复用，避免 OpenAI/httpx 在 loop 结束后异步回收连接池。
        reuse_client=False,
    )

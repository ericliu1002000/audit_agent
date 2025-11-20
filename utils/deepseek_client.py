"""Common DeepSeek API client helpers."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Sequence

from dotenv import load_dotenv
from openai import OpenAI

logger = logging.getLogger(__name__)

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_TEMPERATURE = 0.1


def invoke_deepseek(
    messages: Sequence[Dict[str, str]],
    response_format: Dict[str, str] | None = None,
    **extra_params: Any,
) -> Any:
    """Invoke DeepSeek via OpenAI client with shared configuration."""

    if not messages:
        raise ValueError("messages 为空，无法调用 DeepSeek")

    load_dotenv()
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise ValueError("未配置 DEEPSEEK_API_KEY，无法调用 DeepSeek 接口。")

    client = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)

    try:
        if hasattr(client, "responses"):
            return client.responses.create(
                model=DEEPSEEK_MODEL,
                temperature=DEEPSEEK_TEMPERATURE,
                response_format=response_format or {"type": "json_object"},
                input=messages,
                **extra_params,
            )
        # 兼容旧版 openai SDK，仅支持 chat.completions 接口。
        return client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            temperature=DEEPSEEK_TEMPERATURE,
            response_format=response_format or {"type": "json_object"},
            messages=messages,
            **extra_params,
        )
    except Exception as exc:  # pragma: no cover - 网络调用异常
        logger.exception("调用 DeepSeek API 失败")
        raise ValueError(f"调用 DeepSeek API 失败: {exc}") from exc

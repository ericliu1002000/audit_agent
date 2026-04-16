"""Common DeepSeek API client helpers."""

from __future__ import annotations

import importlib.util
import logging
import os
from typing import Any, Dict, List, Sequence

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_TEMPERATURE = 0.1


def _env_proxy(name: str) -> str:
    return (os.getenv(name) or os.getenv(name.lower()) or "").strip()


def _is_socks_proxy(proxy_url: str) -> bool:
    text = (proxy_url or "").strip().lower()
    return text.startswith(("socks5://", "socks4://", "socks://"))


def _has_socksio() -> bool:
    return importlib.util.find_spec("socksio") is not None


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

    # 如果环境里配置了 SOCKS 代理但缺少 socksio，会导致 openai/httpx 在请求时直接报错。
    # 这里做一个兼容：优先使用 HTTP(S)_PROXY，避免被 ALL_PROXY(socks) 影响。
    http_proxy = _env_proxy("HTTP_PROXY")
    https_proxy = _env_proxy("HTTPS_PROXY")
    all_proxy = _env_proxy("ALL_PROXY")
    env_has_socks = any(
        _is_socks_proxy(p) for p in (http_proxy, https_proxy, all_proxy) if p
    )
    should_override_proxy = env_has_socks and not _has_socksio()

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ValueError("未安装 openai SDK，无法调用 DeepSeek 接口。") from exc

    httpx_client = None
    if should_override_proxy:
        try:
            import httpx
        except ImportError:
            httpx = None  # pragma: no cover
        if httpx is not None:
            proxies = {}
            if http_proxy and not _is_socks_proxy(http_proxy):
                proxies["http://"] = http_proxy
            if https_proxy and not _is_socks_proxy(https_proxy):
                proxies["https://"] = https_proxy

            # 若只有 SOCKS 且未安装 socksio，则给出更可读的错误提示。
            if not proxies:
                raise ValueError(
                    "检测到 SOCKS 代理配置，但缺少 socksio 依赖。请安装 httpx[socks]（或 socksio），"
                    "或将 ALL_PROXY 调整为 http(s) 代理。"
                )

            # 禁用 trust_env，避免 httpx 读取 ALL_PROXY(socks)。
            httpx_client = httpx.Client(proxies=proxies, trust_env=False, timeout=30.0)

    try:
        try:
            client = OpenAI(
                api_key=api_key,
                base_url=DEEPSEEK_BASE_URL,
                http_client=httpx_client,
            )
        except TypeError:
            # 兼容旧版 openai SDK：不支持 http_client 参数时退化为默认行为。
            if httpx_client is not None:
                httpx_client.close()
                httpx_client = None
            client = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)

        # 对 DeepSeek 固定走 Chat Completions。
        # openai 2.x 虽然暴露了 responses API，但其方法签名与本项目当前
        # 使用的 response_format/messages 组合不兼容，会导致运行时报错。
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
    finally:
        if httpx_client is not None:
            try:
                httpx_client.close()
            except Exception:  # pragma: no cover
                pass

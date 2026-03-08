from __future__ import annotations

from typing import List

import requests
from django.conf import settings

SILICONFLOW_DEFAULT_EMBEDDING_MODEL = "Qwen/Qwen3-Embedding-0.6B"


def call_begm3_api(text: str, timeout: float = 60.0) -> List[float]:
    """兼容旧函数名，实际统一走硅基流动 embedding。"""

    # 旧本地 embedding 接口保留为注释，便于将来排查或回滚配置时参考。
    # embed_url = getattr(settings, "EMBED_URL", "")
    # embed_token = getattr(settings, "EMBED_TOKEN", "")
    # expected_dim = int(getattr(settings, "MILVUS_EMBED_DIM", 1024))
    # if not embed_url or not embed_token:
    #     raise RuntimeError("嵌入服务配置未完成，请在 .env 中设置 EMBED_URL 与 EMBED_TOKEN。")
    #
    # payload = {
    #     "token": embed_token,
    #     "text": text,
    #     "require_translate": False,
    # }
    # try:
    #     response = requests.post(
    #         embed_url,
    #         json=payload,
    #         timeout=timeout,
    #         headers={"accept": "application/json"},
    #     )
    # except requests.RequestException as exc:  # pragma: no cover - network errors
    #     raise RuntimeError(f"调用嵌入服务失败: {exc}") from exc
    #
    # if response.status_code != 200:
    #     raise RuntimeError(
    #         f"嵌入服务 HTTP {response.status_code}: {response.text[:200]}"
    #     )
    #
    # data = response.json()
    # if not data.get("success"):
    #     raise RuntimeError(f"嵌入服务返回失败: {data}")
    #
    # embedding = data.get("embedding")
    # if not isinstance(embedding, list) or not embedding:
    #     raise RuntimeError(f"嵌入结果格式异常: {type(embedding)}")
    #
    # if len(embedding) != expected_dim:
    #     raise ValueError(
    #         f"嵌入维度不匹配: got {len(embedding)}, expected {expected_dim}"
    #     )
    #
    # return [float(value) for value in embedding]

    return call_siliconflow_qwen3_embedding_api(text, timeout=timeout)


def call_embedding_api(text: str, timeout: float = 60.0) -> List[float]:
    """项目统一 embedding 入口，默认使用硅基流动。"""

    return call_siliconflow_qwen3_embedding_api(text, timeout=timeout)


def call_siliconflow_qwen3_embedding_api(
    text: str, timeout: float = 60.0
) -> List[float]:
    """调用硅基流动 Qwen3 Embedding 服务并返回向量。"""

    embed_url = getattr(
        settings,
        "SILICONFLOW_API_EMBEDDING_URL",
        "https://api.siliconflow.cn/v1/embeddings",
    )
    api_key = getattr(settings, "SILICONFLOW_API_KEY", "")
    model = getattr(
        settings, "SILICONFLOW_EMBEDDING_MODEL", SILICONFLOW_DEFAULT_EMBEDDING_MODEL
    )
    expected_dim = int(getattr(settings, "MILVUS_EMBED_DIM", 1024))

    if not embed_url or not api_key:
        raise RuntimeError(
            "硅基流动嵌入服务配置未完成，请在 .env 中设置 SILICONFLOW_API_EMBEDDING_URL 与 SILICONFLOW_API_KEY。"
        )

    payload = {
        "model": model,
        "input": text,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    session = requests.Session()
    # 默认不继承系统代理，避免本地 SOCKS/HTTP 代理把后台任务卡住。
    session.trust_env = bool(getattr(settings, "SILICONFLOW_USE_ENV_PROXY", False))
    proxies = {}
    http_proxy = getattr(settings, "SILICONFLOW_HTTP_PROXY", "")
    https_proxy = getattr(settings, "SILICONFLOW_HTTPS_PROXY", "")
    if http_proxy:
        proxies["http"] = http_proxy
    if https_proxy:
        proxies["https"] = https_proxy
    try:
        response = session.post(
            embed_url,
            json=payload,
            headers=headers,
            timeout=timeout,
            proxies=proxies or None,
        )
    except requests.RequestException as exc:  # pragma: no cover - network errors
        raise RuntimeError(f"调用硅基流动嵌入服务失败: {exc}") from exc
    finally:
        session.close()

    if response.status_code != 200:
        raise RuntimeError(
            f"硅基流动嵌入服务 HTTP {response.status_code}: {response.text[:200]}"
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"硅基流动嵌入服务返回非 JSON 响应: {response.text[:200]}"
        ) from exc

    embedding = None
    records = data.get("data") if isinstance(data, dict) else None
    if isinstance(records, list) and records:
        first = records[0]
        if isinstance(first, dict):
            embedding = first.get("embedding")
    if embedding is None and isinstance(data, dict):
        embedding = data.get("embedding")

    if not isinstance(embedding, list) or not embedding:
        raise RuntimeError(f"硅基流动嵌入结果格式异常: {data}")

    if len(embedding) != expected_dim:
        raise ValueError(
            f"嵌入维度不匹配: got {len(embedding)}, expected {expected_dim}"
        )

    return [float(value) for value in embedding]

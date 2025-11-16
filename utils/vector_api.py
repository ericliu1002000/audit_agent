from __future__ import annotations

from typing import List

import requests
from django.conf import settings


def call_begm3_api(text: str, timeout: float = 60.0) -> List[float]:
    """调用嵌入服务并返回向量."""

    embed_url = getattr(settings, "EMBED_URL", "")
    embed_token = getattr(settings, "EMBED_TOKEN", "")
    expected_dim = int(getattr(settings, "MILVUS_EMBED_DIM", 1024))
    if not embed_url or not embed_token:
        raise RuntimeError("嵌入服务配置未完成，请在 .env 中设置 EMBED_URL 与 EMBED_TOKEN。")

    payload = {
        "token": embed_token,
        "text": text,
        "require_translate": False,
    }
    try:
        response = requests.post(
            embed_url,
            json=payload,
            timeout=timeout,
            headers={"accept": "application/json"},
        )
    except requests.RequestException as exc:  # pragma: no cover - network errors
        raise RuntimeError(f"调用嵌入服务失败: {exc}") from exc

    if response.status_code != 200:
        raise RuntimeError(
            f"嵌入服务 HTTP {response.status_code}: {response.text[:200]}"
        )

    data = response.json()
    if not data.get("success"):
        raise RuntimeError(f"嵌入服务返回失败: {data}")

    embedding = data.get("embedding")
    if not isinstance(embedding, list) or not embedding:
        raise RuntimeError(f"嵌入结果格式异常: {type(embedding)}")

    if len(embedding) != expected_dim:
        raise ValueError(
            f"嵌入维度不匹配: got {len(embedding)}, expected {expected_dim}"
        )

    return [float(value) for value in embedding]


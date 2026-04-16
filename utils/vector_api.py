from __future__ import annotations

from typing import List

import requests
from django.conf import settings

VOLCENGINE_EMBEDDING_URL = "https://ark.cn-beijing.volces.com/api/v3/embeddings/multimodal"


def call_begm3_api(text: str, timeout: float = 60.0) -> List[float]:
    """兼容旧函数名，实际统一走豆包 embedding。"""

    return call_embedding_api(text, timeout=timeout)


def call_embedding_api(text: str, timeout: float = 60.0) -> List[float]:
    """项目统一 embedding 入口，默认使用豆包 embedding。"""

    return call_volcengine_embedding_api(text, timeout=timeout)


def call_volcengine_embedding_api(text: str, timeout: float = 60.0) -> List[float]:
    """调用火山方舟豆包 embedding 服务并返回 dense 向量。"""

    api_key = getattr(settings, "VOLCENGINE_KEY", "")
    model = getattr(settings, "VOLCENGINE_VISION_MODEL_ID", "")
    expected_dim = int(getattr(settings, "MILVUS_EMBED_DIM", 1024))

    if not api_key or not model:
        raise RuntimeError(
            "豆包嵌入服务配置未完成，请在 .env 中设置 VOLCENGINE_KEY 与 VOLCENGINE_VISION_MODEL_ID。"
        )

    payload = {
        "model": model,
        "input": [
            {
                "type": "text",
                "text": text,
            }
        ],
        "dimensions": expected_dim,
        "encoding_format": "float",
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        response = requests.post(
            VOLCENGINE_EMBEDDING_URL,
            json=payload,
            headers=headers,
            timeout=timeout,
        )
    except requests.RequestException as exc:  # pragma: no cover - network errors
        raise RuntimeError(f"调用豆包嵌入服务失败: {exc}") from exc

    if response.status_code != 200:
        raise RuntimeError(f"豆包嵌入服务 HTTP {response.status_code}: {response.text[:200]}")

    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError(f"豆包嵌入服务返回非 JSON 响应: {response.text[:200]}") from exc

    embedding = None
    records = data.get("data") if isinstance(data, dict) else None
    if isinstance(records, list) and records:
        first = records[0]
        if isinstance(first, dict):
            embedding = first.get("embedding")
    if embedding is None and isinstance(data, dict):
        embedding = data.get("embedding")

    if not isinstance(embedding, list) or not embedding:
        raise RuntimeError(f"豆包嵌入结果格式异常: {data}")

    if len(embedding) != expected_dim:
        raise ValueError(
            f"嵌入维度不匹配: got {len(embedding)}, expected {expected_dim}"
        )

    return [float(value) for value in embedding]

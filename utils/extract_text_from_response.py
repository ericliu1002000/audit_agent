from typing import Any, List


def extract_text_from_response(response: Any) -> str:
    """
    兼容 OpenAI Responses API 的输出结构，拼接纯文本。
    """

    # Responses API: response.output -> List[Message]
    if hasattr(response, "output"):
        chunks: List[str] = []
        for item in getattr(response, "output", []):
            if getattr(item, "type", None) != "message":
                continue
            for content in getattr(item, "content", []):
                if getattr(content, "type", None) == "text":
                    text_obj = getattr(content, "text", None)
                    if text_obj and hasattr(text_obj, "value"):
                        chunks.append(text_obj.value)
        return "".join(chunks)

    # Chat Completions fallback
    if hasattr(response, "choices"):
        texts = [
            choice.message.content
            for choice in getattr(response, "choices", [])
            if getattr(choice, "message", None) is not None
        ]
        return "\n".join(filter(None, texts))

    return ""

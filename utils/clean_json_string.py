import re


def clean_json_string(text: str) -> str:
    """
    去掉 ```json ... ``` 或 ``` ... ``` 包裹，避免 json.loads 抛错。
    """

    if not text:
        return ""

    cleaned = text.strip()
    fenced_code_pattern = r"^```(?:json)?\s*(.*?)\s*```$"
    match = re.match(fenced_code_pattern, cleaned, flags=re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1)
    return cleaned

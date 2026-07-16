import json
import re


_BLOCK = re.compile(r"<MEMORY_SUGGESTIONS>\s*(.*?)\s*</MEMORY_SUGGESTIONS>", re.DOTALL | re.IGNORECASE)


def extract_memory_suggestions(text: str) -> tuple[str, list[dict[str, str]]]:
    match = _BLOCK.search(text)
    if not match:
        return text.strip(), []
    try:
        raw = json.loads(match.group(1))
    except json.JSONDecodeError:
        return _BLOCK.sub("", text).strip(), []
    suggestions = [
        {"content": str(item["content"]).strip(), "reason": str(item.get("reason", "")).strip()}
        for item in raw
        if isinstance(item, dict) and item.get("content")
    ]
    return _BLOCK.sub("", text).strip(), suggestions[:3]

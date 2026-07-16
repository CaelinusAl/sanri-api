import json
import re


def _extract(text: str, tag: str) -> tuple[str, dict | None]:
    pattern = re.compile(rf"<{tag}>\s*(.*?)\s*</{tag}>", re.DOTALL | re.IGNORECASE)
    match = pattern.search(text)
    if not match:
        return text, None
    try:
        value = json.loads(match.group(1))
    except json.JSONDecodeError:
        value = None
    return pattern.sub("", text), value if isinstance(value, dict) else None


def extract_aura_reports(text: str) -> tuple[str, dict | None, dict | None]:
    cleaned, state_update = _extract(text, "AURA_STATE_UPDATE")
    cleaned, progress = _extract(cleaned, "TODAY_PROGRESS")
    return cleaned.strip(), state_update, progress


def extract_reflection_after_action(text: str) -> tuple[str, dict | None]:
    cleaned, reflection = _extract(text, "REFLECTION_AFTER_ACTION")
    if reflection is None:
        return cleaned.strip(), None
    required = ("what_changed_today", "what_should_i_remember", "next_smallest_step")
    if not all(isinstance(reflection.get(key), str) for key in required):
        return cleaned.strip(), None
    return cleaned.strip(), {key: reflection[key].strip() for key in required}

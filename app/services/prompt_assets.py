from functools import lru_cache
from pathlib import Path

import yaml


PROMPT_ROOT = Path(__file__).resolve().parents[1]


@lru_cache
def _load_yaml(relative_path: str) -> dict:
    path = PROMPT_ROOT / relative_path
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def mode_prompt(mode: str) -> str:
    data = _load_yaml(f"modes/{mode}.yaml")
    rules = "\n".join(f"- {rule}" for rule in data.get("rules", []))
    return f"ACTIVE MODE: {data.get('name', mode)}\nPURPOSE: {data.get('purpose', '')}\nRULES:\n{rules}\nSUCCESS: {data.get('success_criterion', '')}"


def safety_prompt() -> str:
    data = _load_yaml("prompts/safety.yaml")
    return "\n".join(f"- {rule}" for rule in data.get("rules", []))


def memory_rules_prompt() -> str:
    data = _load_yaml("prompts/memory_rules.yaml")
    return "\n".join(f"- {rule}" for rule in data.get("rules", []))

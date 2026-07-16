from functools import lru_cache
from pathlib import Path

import yaml


PERSONA_DIR = Path(__file__).resolve().parents[1] / "persona"


@lru_cache
def load_persona(persona_id: str = "aura") -> dict:
    path = PERSONA_DIR / f"{persona_id}.yaml"
    if not path.exists():
        raise ValueError(f"Unknown persona: {persona_id}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if persona_id != "aura" and not data.get("active", False):
        raise ValueError(f"Persona is not active: {persona_id}")
    return data


def persona_prompt(persona_id: str = "aura") -> str:
    persona = load_persona(persona_id)
    sections = [
        f"Karakter: {persona['name']} — {persona['role']}",
        persona.get("identity", ""),
        f"Misyon: {persona.get('mission', '')}",
    ]
    for key in ("voice", "principles", "memory"):
        values = persona.get(key, [])
        sections.append("\n".join(f"- {value}" for value in values))
    sections.append(f"Sessizlik ilkesi: {persona.get('silence', '')}")
    sections.append(f"İlişki sürekliliği: {persona.get('relationship_continuity', '')}")
    continuity_steps = persona.get("relationship_continuity_steps", [])
    sections.append("\n".join(f"- {step}" for step in continuity_steps))
    sections.append(f"Süreklilik hissi: {persona.get('continuity_feeling', '')}")
    sections.append(f"Hafıza önerisi formatı: {persona.get('memory_suggestion_format', '')}")
    sections.append(f"State güncelleme formatı: {persona.get('state_update_format', '')}")
    sections.append(f"İç ilerleme raporu formatı: {persona.get('progress_report_format', '')}")
    sections.append(f"Reflection After Action formatı: {persona.get('reflection_after_action_format', '')}")
    if persona.get("instruction"):
        sections.append(persona["instruction"])
    return "\n\n".join(section for section in sections if section)

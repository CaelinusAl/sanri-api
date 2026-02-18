import json
import os
from typing import Any, Dict


def _load_city_map() -> Dict[str, Any]:
    path = os.path.join(os.path.dirname(__file__), "..", "data", "cities_tr.json")
    path = os.path.abspath(path)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


CITY_MAP = _load_city_map()


def build_city_journey(plate: str) -> Dict[str, Any]:
    plate = (plate or "").strip()
    ci = CITY_MAP.get(plate)

    if not ci:
        return {
            "module": "awakened_cities",
            "title": "Uyanmış Şehirler",
            "answer": "Plaka bulunamadı. Örnek: 34, 06, 35…",
            "sections": [
                {"label": "Nasıl Kullanılır", "text": "Sadece 2 haneli plaka yaz: 01, 34, 06 …"}
            ],
            "tags": ["awakened_cities"]
        }

    # Eğer JSON içinde özel journey_sections varsa onu aynen kullan
    if "journey_sections" in ci:
        sections = ci["journey_sections"]
        answer = sections[0]["text"] if sections else ci.get("core_message", "")
        return {
            "module": "awakened_cities",
            "title": f"{ci.get('city')} / {plate}",
            "answer": answer,
            "sections": sections,
            "tags": ["awakened_cities", plate, ci.get("city")]
        }

    # fallback (henüz yazılmamış şehirler için)
    return {
        "module": "awakened_cities",
        "title": f"{ci.get('city')} / {plate}",
        "answer": ci.get("core_message", ""),
        "sections": [
            {"label": "Arketip", "text": ci.get("archetype", "")},
            {"label": "Element", "text": ci.get("element", "")},
            {"label": "Mesaj", "text": ci.get("core_message", "")}
        ],
        "tags": ["awakened_cities", plate, ci.get("city")]
    }

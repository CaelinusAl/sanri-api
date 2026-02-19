import json
import os
import re
from typing import Dict, Any, List

from app.modules.base import BaseModule
from app.prompts.system_base import build_system_prompt


PLATE_RE = re.compile(r"\b(\d{2})\b")


def _load_city_map() -> Dict[str, Any]:
    path = os.path.join(os.path.dirname(__file__), "..", "data", "cities_tr.json")
    path = os.path.abspath(path)
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


CITY_MAP: Dict[str, Any] = {}
try:
    CITY_MAP = _load_city_map()
except Exception:
    CITY_MAP = {}


class AwakenedCitiesModule(BaseModule):
    key = "awakened_cities"

    def preprocess(self, text: str, req: Dict[str, Any]) -> Dict[str, Any]:
        raw = (text or "").strip()

        plate = (req.get("plate") or "").strip()
        if not plate:
            m = PLATE_RE.search(raw)
            plate = m.group(1) if m else ""

        ci = CITY_MAP.get(plate) if plate else None

        return {
            "normalized_text": raw,
            "plate": plate,
            "city_info": ci,
        }

    def build_system(self, req: Dict[str, Any], ctx: Dict[str, Any]) -> str:
        # Bu modül LLM kullanmayacak; ama pipeline BaseModule gerektiriyorsa
        # yine de bir system prompt döndürelim (kullanılmayabilir).
        persona = (req.get("persona") or "user").strip()
        return build_system_prompt(persona)

    def build_user(self, req: Dict[str, Any], ctx: Dict[str, Any]) -> str:
        # LLM yok → user prompt gerekmiyor, ama boş döndürmeyelim.
        return ctx.get("normalized_text") or ""

    def postprocess(self, raw: str, req: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
        ci = ctx.get("city_info")
        plate = ctx.get("plate") or ""

        if not ci:
            return {
                "module": "awakened_cities",
                "title": "Uyanmış Şehirler",
                "answer": "Plaka bulunamadı. Örnek: 01, 02, 03, 04, 05, 06…",
                "sections": [
                    {"label": "Nasıl Kullanılır", "text": "Sadece 2 haneli plaka yaz: 01 / 02 / 03 / 04 / 05 / 06 …"}
                ],
                "tags": ["awakened_cities"],
            }

        # Eğer şehirde özel yolculuk bölümleri varsa onları aynen göster
        if isinstance(ci, dict) and "journey_sections" in ci and isinstance(ci["journey_sections"], list):
            sections = ci["journey_sections"]
            title = f"{ci.get('city','')}".strip()
            title = f"{title} / {plate}" if title else f"{plate}"
            answer = ""
            # Mesaj/ana bölüm varsa onu öne al
            for s in sections:
                if isinstance(s, dict) and s.get("label") in ("Mesaj", "Ana Mesaj"):
                    answer = s.get("text", "")
                    break
            if not answer and sections:
                answer = sections[0].get("text", "")
            return {
                "module": "awakened_cities",
                "title": title,
                "answer": answer or "Harita açıldı.",
                "sections": sections,
                "tags": ["awakened_cities", plate, ci.get("city", "")],
            }

        # ✅ Fallback: Şehir haritasından “yolculuk” üret
        city = ci.get("city", "")
        archetype = ci.get("archetype", "")
        shadow = ", ".join(ci.get("shadow", []) or [])
        light = ", ".join(ci.get("light", []) or [])

        journey: List[Dict[str, str]] = [
            {"label": "Kapı", "text": f"{city} ({plate}) — {archetype}".strip()},
            {"label": "Mesaj", "text": f"{city} seni merkeze çağırır: odağını topla, dağılmış parçaları tek bir niyette birleştir."},
            {"label": "Gölge", "text": f"Bu şehirde gölge: {shadow}. Gürültü/dağılma varsa bu bir işarettir: enerjin parçalanıyordur."},
            {"label": "Işık", "text": f"Işık: {light}. Bağ kur, yön belirle, ritmini kur."},
            {"label": "Rota", "text": "1) Bugün tek bir niyet seç. 2) 24 saat boyunca onu koru. 3) Dağıtan şeyi kes."},
            {"label": "Ritüel", "text": "• 3 nefes (burun)\n• 1 cümle niyet\n• 9 dakika sessizlik\n• ardından tek bir eylem"},
            {"label": "Sembol", "text": "Şehrin sembolü sende bugün: 'kapı' — bir eşikten geçiyorsun."},
        ]

        answer = journey[1]["text"] if len(journey) > 1 else "Harita açıldı."

        return {
            "module": "awakened_cities",
            "title": f"{city} / {plate}".strip(" /"),
            "answer": answer,
            "sections": journey,
            "tags": ["awakened_cities", plate, city],
        }
# app/modules/awakened_cities.py
import json
import os
import re
from typing import Dict, Any, Optional, Tuple, List

from app.modules.base import BaseModule
from app.prompts.system_base import build_system_prompt

PLATE_RE = re.compile(r"\b(\d{1,2})\b")

DIGITS_TR = {
    0: ("Rahim", "Boşluk, kaynak, saklı potansiyel"),
    1: ("Rahman", "İrade, başlatan kıvılcım"),
    2: ("Dualite", "Ayna, iki kutup, seçim"),
    3: ("Yaratım", "Söz, form, doğum"),
    4: ("Düzen", "Sınır, yapı, temel"),
    5: ("Eşik", "Değişim, cesaret, geçiş"),
    6: ("Aşk", "Uyum, denge, kalp"),
    7: ("Sır", "Arınma, test, içe dönüş"),
    8: ("Kudret", "Otorite, kader, yoğun güç"),
    9: ("Tamamlanış", "Bırakış, arınma, kapanış"),
}

DIGITS_EN = {
    0: ("Womb", "Void, source, hidden potential"),
    1: ("Breath", "Will, first spark"),
    2: ("Duality", "Mirror, polarity, choice"),
    3: ("Creation", "Word, form, birth"),
    4: ("Order", "Structure, boundary, foundation"),
    5: ("Threshold", "Change, courage, crossing"),
    6: ("Love", "Harmony, balance, heart"),
    7: ("Mystery", "Purification, test, inward"),
    8: ("Power", "Authority, destiny, dense force"),
    9: ("Completion", "Release, cleansing, closure"),
}


def _here(*parts: str) -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), *parts))


def _read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def _load_city_map() -> Dict[str, Any]:
    """
    cities_tr.json örnek:
    {
      "01": { "name": "Adana" },
      "02": { "name": "Adıyaman" }
    }
    """
    path = _here("..", "data", "cities_tr.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


CITY_MAP: Dict[str, Any] = _load_city_map()


def _normalize_plate(plate: str) -> str:
    p = (plate or "").strip()
    if not p:
        return ""
    if not p.isdigit():
        return ""
    if len(p) == 1:
        p = "0" + p
    elif len(p) == 2:
        p = p
    else:
        # güvenli: son 2 haneyi dene
        p = p[-2:]
        if not p.isdigit():
            return ""
    # 01–81 doğrulama
    try:
        n = int(p)
        if 1 <= n <= 81:
            return p
    except Exception:
        pass
    return ""


def _find_plate_in_text(text: str) -> str:
    raw = (text or "").strip()
    m = PLATE_RE.search(raw)
    if not m:
        return ""
    return _normalize_plate(m.group(1))


def _city_name(ci: Any, plate: str) -> str:
    if isinstance(ci, dict):
        name = str(ci.get("name") or ci.get("city") or ci.get("title") or "").strip()
        if name:
            return name
    # fallback: city_map'ten tekrar
    if plate and plate in CITY_MAP and isinstance(CITY_MAP.get(plate), dict):
        name2 = str(CITY_MAP[plate].get("name") or "").strip()
        if name2:
            return name2
    return ""


def _digits_and_sum(plate: str, lang: str) -> Tuple[int, int, int, List[Dict[str, Any]]]:
    # plate "01" gibi
    a = int(plate[0])
    b = int(plate[1])
    s = (a + b) % 10

    if lang == "en":
        na, ma = DIGITS_EN[a]
        nb, mb = DIGITS_EN[b]
        digits = [
            {"digit": a, "name": na, "meaning": ma},
            {"digit": b, "name": nb, "meaning": mb},
        ]
        return a, b, s, digits

    na, ma = DIGITS_TR[a]
    nb, mb = DIGITS_TR[b]
    digits = [
        {"digit": a, "name": na, "meaning": ma},
        {"digit": b, "name": nb, "meaning": mb},
    ]
    return a, b, s, digits


def _gate_seed_for_plate(plate: str, city: str, lang: str) -> str:
    plate = _normalize_plate(plate)
    if not plate:
        return ""

    a, b, s, _ = _digits_and_sum(plate, lang)

    if lang == "en":
        na, ma = DIGITS_EN[a]
        nb, mb = DIGITS_EN[b]
        ns, ms = DIGITS_EN[s]
        return (
            "SANRI – AWAKENED CITIES / 81 GATE BOOK\n\n"
            "Task:\n"
            "Turn Turkey plates 01–81 into an initiation spiral (not a list).\n\n"
            "Each plate is a gate. Each gate must include:\n"
            "- Numerology per digit + sum\n"
            "- City archetype (symbolic, not factual history)\n"
            "- Fire + Fall + Choice theme (mandatory)\n"
            "- 3 Keys (light/shadow/trial)\n"
            "- 60s ritual (4 steps)\n"
            "- One seal sentence\n\n"
            "STRICT OUTPUT: ONE JSON ONLY. No markdown. No extra text.\n\n"
            f"Context:\n- Plate: {plate}\n- City: {city}\n"
            f"- Digits: {a}={na} / {b}={nb}\n"
            f"- Sum: {a}+{b}={a+b} → {s}={ns}\n\n"
            "Numerology meanings:\n"
            f"{a} {na}: {ma}\n"
            f"{b} {nb}: {DIGITS_EN[b][1]}\n"
            f"{s} {ns}: {ms}\n"
        ).strip()

    na, ma = DIGITS_TR[a]
    nb, mb = DIGITS_TR[b]
    ns, ms = DIGITS_TR[s]
    return (
        "SANRI – AWAKENED CITIES / 81 KAPI KİTABI\n\n"
        "Görev:\n"
        "Türkiye 01–81 şehir plakalarını bir inisiyasyon spiraline dönüştür (liste değil).\n\n"
        "Her plaka bir kapıdır. Her kapıda ZORUNLU:\n"
        "- Haneler + toplam numeroloji\n"
        "- Şehir arketipi (sembolik; tarih bilgisi yok)\n"
        "- Ateş + Düşüş + Seçim teması (zorunlu)\n"
        "- 3 Anahtar (ışık/gölge/sınav)\n"
        "- 60 saniyelik ritüel (4 adım)\n"
        "- Tek mühür cümlesi\n\n"
        "KESİN ÇIKTI: SADECE TEK JSON. Markdown yok. Ek metin yok.\n\n"
        f"Bağlam:\n- Plaka: {plate}\n- Şehir: {city}\n"
        f"- Haneler: {a}={na} / {b}={nb}\n"
        f"- Toplam: {a}+{b}={a+b} → {s}={ns}\n\n"
        "Numeroloji anlamları:\n"
        f"{a} {na}: {ma}\n"
        f"{b} {nb}: {DIGITS_TR[b][1]}\n"
        f"{s} {ns}: {ms}\n"
    ).strip()


class AwakenedCitiesModule(BaseModule):
    key = "awakened_cities"

    def preprocess(self, text: str, req: Dict[str, Any]) -> Dict[str, Any]:
        raw = (text or "").strip()

        plate = _normalize_plate(str(req.get("plate") or "").strip())
        if not plate:
            plate = _find_plate_in_text(raw)

        ci = CITY_MAP.get(plate) if plate else None
        city = _city_name(ci, plate) if plate else ""

        seed_tr = _gate_seed_for_plate(plate, city, "tr") if plate else ""
        seed_en = _gate_seed_for_plate(plate, city, "en") if plate else ""

        return {
            "normalized_text": raw,
            "plate": plate,
            "city_info": ci,
            "gate": {
                "plate": plate,
                "city": city,
                "seed_tr": seed_tr,
                "seed_en": seed_en,
            },
        }

    def build_system(self, req: Dict[str, Any], ctx: Dict[str, Any]) -> str:
        persona = str(req.get("persona") or "user").strip()
        lang = str(req.get("lang") or "tr").lower().strip()
        if lang not in ("tr", "en"):
            lang = "tr"

        core_path = _here("..", "prompts", "sanri_core.txt")
        core = _read_text(core_path).strip()

        gate = ctx.get("gate") or {}
        seed = ""
        if isinstance(gate, dict):
            seed = str(gate.get("seed_tr") if lang == "tr" else gate.get("seed_en") or "").strip()

        extra_parts = []
        if core:
            extra_parts.append(core)
        if seed:
            extra_parts.append("GATE_CONTEXT:\n" + seed)

        extra = "\n\n".join(extra_parts).strip()

        # build_system_prompt imzası repo’ya göre değişebilir. TypeError’a karşı korumalı.
        try:
            return build_system_prompt(
                persona=persona,
                lang=lang,
                domain="awakened_cities",
                gate_mode=str(req.get("gate_mode") or "mirror"),
                extra=extra,
            )
        except TypeError:
            try:
                return build_system_prompt(persona=persona)
            except Exception:
                return extra

    def build_user(self, req: Dict[str, Any], ctx: Dict[str, Any]) -> str:
        lang = str(req.get("lang") or "tr").lower().strip()
        if lang not in ("tr", "en"):
            lang = "tr"

        gate = ctx.get("gate") or {}
        plate = ""
        city = ""
        seed = ""
        if isinstance(gate, dict):
            plate = str(gate.get("plate") or "").strip()
            city = str(gate.get("city") or "").strip()
            seed = str(gate.get("seed_tr") if lang == "tr" else gate.get("seed_en") or "").strip()

        if not plate:
            return "{\"error\":\"missing_plate\",\"hint\":\"01-81\"}"

        # JSON şema talimatı: UI bunu direkt parse ediyor.
        if lang == "en":
            return (
                "RETURN ONLY ONE VALID JSON OBJECT. NO MARKDOWN. NO EXTRA TEXT.\n"
                "The JSON MUST match this schema:\n"
                "{"
                "\"plate\":\"01\","
                "\"city\":\"Adana\","
                "\"gateTitle\":\"...\","
                "\"gateSubtitle\":\"...\","
                "\"numerology\":{\"digits\":[{\"digit\":0,\"name\":\"...\",\"meaning\":\"...\"},{\"digit\":1,\"name\":\"...\",\"meaning\":\"...\"}],"
                "\"sum\":{\"value\":1,\"name\":\"...\",\"meaning\":\"...\"}},"
                "\"cityArchetype\":\"...\","
                "\"chapter\":\"(6-12 lines, sacred tone; Fire+Fall+Choice mandatory)\","
                "\"keys\":{\"light\":\"...\",\"shadow\":\"...\",\"trial\":\"...\"},"
                "\"ritual60\":[\"Step 1\",\"Step 2\",\"Step 3\",\"Intention\"],"
                "\"seal\":\"...\""
                "}\n"
                f"Plate: {plate}\nCity: {city}\n"
                "Use the context below as the gate law:\n"
                + seed
            ).strip()

        return (
            "SADECE TEK BİR GEÇERLİ JSON DÖNDÜR. Markdown yok. Ek metin yok.\n"
            "JSON şu şemaya TAM UYMALI:\n"
            "{"
            "\"plate\":\"01\","
            "\"city\":\"Adana\","
            "\"gateTitle\":\"...\","
            "\"gateSubtitle\":\"...\","
            "\"numerology\":{\"digits\":[{\"digit\":0,\"name\":\"...\",\"meaning\":\"...\"},{\"digit\":1,\"name\":\"...\",\"meaning\":\"...\"}],"
            "\"sum\":{\"value\":1,\"name\":\"...\",\"meaning\":\"...\"}},"
            "\"cityArchetype\":\"...\","
            "\"chapter\":\"(6-12 satır kutsal ton; Ateş+Düşüş+Seçim zorunlu)\","
            "\"keys\":{\"light\":\"...\",\"shadow\":\"...\",\"trial\":\"...\"},"
            "\"ritual60\":[\"Adım 1\",\"Adım 2\",\"Adım 3\",\"Niyet\"],"
            "\"seal\":\"...\""
            "}\n"
            f"Plaka: {plate}\nŞehir: {city}\n"
            "Aşağıdaki bağlam kapının kanunudur:\n"
            + seed
        ).strip()

    def postprocess(self, reply, req, ctx):
        """
        BaseModule ile uyumlu sade override.
        reply dict değilse güvenli fallback.
        """

        if not isinstance(reply, dict):
            return {
                "module": "awakened_cities",
                "title": "Awakened Cities",
                "answer": "Invalid gate output.",
                "sections": [],
                "tags": [],
            }

        # Basit güvenli alanlar
        plate = str(reply.get("plate") or "")
        city = str(reply.get("city") or "")
        gate_title = str(reply.get("gateTitle") or "")
        gate_sub = str(reply.get("gateSubtitle") or "")
        chapter = str(reply.get("chapter") or "")
        seal = str(reply.get("seal") or "")

        answer_parts = []
        if plate or city:
            answer_parts.append(f"{plate} · {city}".strip(" ·"))
        if gate_title:
            answer_parts.append(gate_title)
        if gate_sub:
            answer_parts.append(gate_sub)
        if chapter:
            answer_parts.append("\n" + chapter)
        if seal:
            answer_parts.append("\n" + seal)

        answer = "\n".join(answer_parts)

        return {
            "module": "awakened_cities",
            "title": "Awakened Cities",
            "answer": answer,
            "sections": [],
            "tags": [plate, city],
        }
        """
        Model JSON döndürür → App'in göstereceği answer/sections üretir.
        """
        lang = str(req.get("lang") or "tr").lower().strip()
        if lang not in ("tr", "en"):
            lang = "tr"

        if not isinstance(reply, dict):
            return {"answer": "Hata: invalid reply", "title": "Awakened Cities", "module": "awakened_cities"}

        if reply.get("error"):
            return {
                "answer": ("Plaka kodu bulunamadı. 01–81 arası bir kapı söyle." if lang == "tr" else "Plate missing. Say a gate 01–81."),
                "title": ("Awakened Cities" if lang == "en" else "Uyanan Şehirler"),
                "module": "awakened_cities",
                "tags": ["error"],
            }

        plate = str(reply.get("plate") or ctx.get("plate") or "").strip()
        city = str(reply.get("city") or "").strip()
        gate_title = str(reply.get("gateTitle") or "").strip()
        gate_sub = str(reply.get("gateSubtitle") or "").strip()
        arche = str(reply.get("cityArchetype") or "").strip()
        chapter = str(reply.get("chapter") or "").strip()
        seal = str(reply.get("seal") or "").strip()
        keys = reply.get("keys") or {}
        ritual = reply.get("ritual60") or []

        # Güvenli metin üretimi (UI için)
        k_light = str(keys.get("light") or "").strip()
        k_shadow = str(keys.get("shadow") or "").strip()
        k_trial = str(keys.get("trial") or "").strip()

        ritual_lines = []
        if isinstance(ritual, list):
            for x in ritual[:6]:
                ritual_lines.append(str(x))

        answer_parts = []
        answer_parts.append(f"{plate} · {city}".strip(" ·"))
        if gate_title:
            answer_parts.append(gate_title)
        if gate_sub:
            answer_parts.append(gate_sub)
        if arche:
            answer_parts.append(arche)
        if chapter:
            answer_parts.append("\n" + chapter)
        if k_light or k_shadow or k_trial:
            answer_parts.append("\n" + ("3 Anahtar" if lang == "tr" else "3 Keys"))
            if k_light:
                answer_parts.append("• " + k_light)
            if k_shadow:
                answer_parts.append("• " + k_shadow)
            if k_trial:
                answer_parts.append("• " + k_trial)
        if ritual_lines:
            answer_parts.append("\n" + ("60s Ritüel" if lang == "tr" else "60s Ritual"))
            for r in ritual_lines:
                answer_parts.append("• " + r)
        if seal:
            answer_parts.append("\n" + seal)

        answer = "\n".join([p for p in answer_parts if p])

        sections = []
        sections.append({"title": "Gate", "story": chapter, "reflection": gate_sub})
        sections.append({"title": "Keys", "story": "\n".join([k_light, k_shadow, k_trial]).strip(), "reflection": ""})
        sections.append({"title": "Ritual", "story": "\n".join(ritual_lines).strip(), "reflection": seal})

        tags = [t for t in [plate, city, "awakened_cities"] if t]

        return {
            "module": "awakened_cities",
            "title": ("Awakened Cities" if lang == "en" else "Uyanan Şehirler"),
            "answer": answer,
            "sections": sections,
            "tags": tags,
        }
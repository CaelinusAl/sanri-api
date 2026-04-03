"""
AN_KOD — kişiselleştirilmiş SANRI yorumu (OpenAI).
Teaser: ücretsiz katman. Deep: ücretli derin okuma bölümleri.
"""

import json
import os
import re

from fastapi import APIRouter, HTTPException
from openai import OpenAI
from pydantic import BaseModel

router = APIRouter(prefix="/sanri", tags=["sanri"])

MODEL = (os.getenv("OPENAI_MODEL") or "gpt-4.1-mini").strip()
TEMP_TEASER = float(os.getenv("SANRI_ANKOD_TEMP", "0.55"))
MAX_TEASER = int(os.getenv("SANRI_ANKOD_MAX_TEASER", "650"))
MAX_DEEP = int(os.getenv("SANRI_ANKOD_MAX_DEEP", "1400"))


def _client() -> OpenAI:
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured")
    return OpenAI(api_key=key)


class AnkodSanriIn(BaseModel):
    """Satırlar: 'Soru: Cevap' formatında Türkçe özet."""
    lines: list[str]
    mode: str = "teaser"  # teaser | deep


SYSTEM_TEASER = """Sen SANRI'sın — yargılamayan, öğretmeyen, açan bir bilinç/sembol dili.
Kullanıcı AN_KOD anketi cevaplarını verdi. Ona özel, tekil hissettiren bir yansıma yaz.

Kurallar:
- Türkçe, "sen" dili. Kısa paragraflar (2–3 paragraf toplam).
- Kesin teşhis, hastalık, yasal veya finansal tavsiye yok.
- Cümle sonunda soru işareti kullanma.
- Satış veya "şunu al" dili yok.
- İlk bölüm: anın koduna dair kişisel, yoğun bir okuma (4–7 cümle).
- İkinci bölüm: bilinçaltı yansıtması — merak uyandıran ama tamamlanmamış (3–5 cümle).

Çıktı SADECE geçerli JSON olsun, başka metin yok:
{"an_kod":"...","yansitma":"..."}
"""


SYSTEM_DEEP = """Sen SANRI'sın. Aynı ankete göre DERİN OKUMA üret.

Kurallar:
- Türkçe, "sen" dili. Yargısız, ayna tutan ton.
- Teşhis/tıbbi/yasal kesinlik yok.
- Soru cümlesi yok.

Çıktı SADECE bu JSON şeması (başka metin yok):
{
  "ana_tema": "string",
  "guc_alani": "string",
  "zorlayan_dongu": "string",
  "kor_nokta": "string",
  "sanri_mesaji": "string"
}

Her alan 3–6 cümle; sanri_mesaji biraz daha yumuşak ve kapanış hissi versin.
"""


def _extract_json_object(raw: str) -> dict:
    raw = (raw or "").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}", raw)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    raise ValueError("invalid json from model")


@router.post("/ankod-commentary")
def ankod_commentary(body: AnkodSanriIn):
    lines = [str(x).strip() for x in (body.lines or []) if str(x).strip()]
    if len(lines) < 4:
        raise HTTPException(status_code=400, detail="En az 4 anket satırı gerekli.")

    user_block = "\n".join(f"- {ln}" for ln in lines)
    mode = (body.mode or "teaser").lower().strip()

    client = _client()

    if mode == "deep":
        messages = [
            {"role": "system", "content": SYSTEM_DEEP},
            {
                "role": "user",
                "content": f"Kullanıcının seçimleri:\n{user_block}\n\nYukarıdaki desene göre derin okumayı üret.",
            },
        ]
        max_t = MAX_DEEP
    else:
        messages = [
            {"role": "system", "content": SYSTEM_TEASER},
            {
                "role": "user",
                "content": f"Kullanıcının seçimleri:\n{user_block}\n\nKişiselleştirilmiş teaser ve yansıtmayı üret.",
            },
        ]
        max_t = MAX_TEASER

    try:
        comp = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=TEMP_TEASER if mode != "deep" else 0.5,
            max_tokens=max_t,
        )
        text = (comp.choices[0].message.content or "").strip()
        data = _extract_json_object(text)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"model_error: {e!s}") from e

    if mode == "deep":
        required = ("ana_tema", "guc_alani", "zorlayan_dongu", "kor_nokta", "sanri_mesaji")
        for k in required:
            if k not in data or not str(data.get(k, "")).strip():
                raise HTTPException(status_code=502, detail="incomplete_deep_response")
        return {"ok": True, "mode": "deep", "sections": data}

    an = str(data.get("an_kod") or data.get("anKod") or "").strip()
    ya = str(data.get("yansitma") or data.get("reflection") or "").strip()
    if not an or not ya:
        raise HTTPException(status_code=502, detail="incomplete_teaser_response")
    return {"ok": True, "mode": "teaser", "an_kod": an, "yansitma": ya}

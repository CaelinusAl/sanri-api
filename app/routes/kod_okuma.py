"""
SANRI Kod Okuma Sistemi — Üst Bilinç Kodlama (SANRI ile Çöz).
"""

from __future__ import annotations

import os
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.db import get_db
from app.prompts.kod_okuma_ust_bilinç import (
    KOD_OKUMA_UST_BILINC_SYSTEM,
    KOD_OKUMA_UST_BILINC_VERSION,
    build_kod_okuma_user_message,
)
from app.routes.auth import get_current_user
from app.services.ai_service import get_client, generate_kod_okuma_json
from sqlalchemy.orm import Session

router = APIRouter(prefix="/kod-okuma", tags=["kod-okuma"])

MODEL = (os.getenv("OPENAI_MODEL") or "gpt-4.1-mini").strip()
MAX_USER_CHARS = 600


class KodAyrimiModel(BaseModel):
    baslik: str = ""
    kirilimlar: List[str] = Field(default_factory=list)


class ParcaOkumaModel(BaseModel):
    parca_adi: str = ""
    okuma_satirlari: List[str] = Field(default_factory=list)


class UstBilinçPayload(BaseModel):
    kod_ayrimi: KodAyrimiModel
    parca_okumasi: List[ParcaOkumaModel]
    ust_bilinç_katmani: str = ""
    sanri_sorusu: str = ""


class UstBilinçRequest(BaseModel):
    message: str = ""
    lesson_title: str = ""
    module_title: str = ""


def _coerce_payload(raw: dict) -> dict:
    """Model bazen alanları eksik veya farklı şekilde döndürür; normalize et."""
    if not isinstance(raw, dict):
        raw = {}

    ka = raw.get("kod_ayrimi")
    if isinstance(ka, str):
        ka = {"baslik": ka, "kirilimlar": []}
    elif not isinstance(ka, dict):
        ka = {}
    kir = ka.get("kirilimlar")
    if isinstance(kir, str):
        kir = [kir]
    elif not isinstance(kir, list):
        kir = []
    ka_out = {
        "baslik": str(ka.get("baslik") or "").strip() or "—",
        "kirilimlar": [str(x).strip() for x in kir if str(x).strip()],
    }

    po = raw.get("parca_okumasi")
    items: list[dict] = []
    if isinstance(po, list):
        for it in po:
            if isinstance(it, str):
                items.append({"parca_adi": "", "okuma_satirlari": [it]})
                continue
            if not isinstance(it, dict):
                continue
            lines = it.get("okuma_satirlari")
            if isinstance(lines, str):
                lines = [lines]
            elif not isinstance(lines, list):
                lines = []
            items.append(
                {
                    "parca_adi": str(it.get("parca_adi") or it.get("etiket") or "").strip(),
                    "okuma_satirlari": [str(x).strip() for x in lines if str(x).strip()],
                }
            )
    elif isinstance(po, str) and po.strip():
        items.append({"parca_adi": "", "okuma_satirlari": [po.strip()]})

    ust = (
        raw.get("ust_bilinç_katmani")
        or raw.get("ust_bilin_katmani")
        or raw.get("ust_bilinç")
        or ""
    )
    return {
        "kod_ayrimi": ka_out,
        "parca_okumasi": items,
        "ust_bilinç_katmani": str(ust).strip(),
        "sanri_sorusu": str(raw.get("sanri_sorusu") or "").strip(),
    }


@router.post("/ust-bilinç")
def kod_ust_bilinç(
    body: UstBilinçRequest,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ = db  # ileride kullanım logu için
    _ = user

    text = (body.message or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="EMPTY_MESSAGE")
    if len(text) > MAX_USER_CHARS:
        text = text[:MAX_USER_CHARS]

    user_msg = build_kod_okuma_user_message(
        text,
        lesson_title=(body.lesson_title or "").strip(),
        module_title=(body.module_title or "").strip(),
    )

    try:
        client = get_client()
        raw = generate_kod_okuma_json(
            client=client,
            model=MODEL,
            system_prompt=KOD_OKUMA_UST_BILINC_SYSTEM,
            user_input=user_msg,
        )
    except Exception as e:
        print("KOD_OKUMA_UBK ERROR =", repr(e))
        raise HTTPException(
            status_code=502,
            detail="Üst bilinç okuması şu an tamamlanamadı. Kısa bir metinle tekrar dene.",
        )

    coerced = _coerce_payload(raw if isinstance(raw, dict) else {})
    try:
        validated = UstBilinçPayload.model_validate(coerced)
        out = validated.model_dump()
    except Exception:
        out = coerced

    return {
        "ok": True,
        "prompt_version": KOD_OKUMA_UST_BILINC_VERSION,
        "data": out,
    }

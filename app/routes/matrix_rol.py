import os
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from openai import OpenAI

from app.services.matrix_role import analyze_matrix_role
from app.services.premium_guard import (
    get_user_or_401,
    enforce_premium_or_403,
    enforce_self_only_or_403,
    enforce_30d_rule_or_403,
    mark_matrix_deep_used,
)

router = APIRouter(prefix="/matrix-rol", tags=["matrix-rol"])

MODEL_NAME = (os.getenv("OPENAI_MODEL") or "gpt-4.1-mini").strip()
TEMPERATURE = float(os.getenv("SANRI_TEMPERATURE", "0.45"))
MAX_TOKENS = int(os.getenv("SANRI_MAX_TOKENS", "900"))

def get_client() -> OpenAI:
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY missing or empty")
    return OpenAI(api_key=api_key)

class MatrixRolRequest(BaseModel):
    name: str
    birth_date: str

class MatrixRolYorumRequest(BaseModel):
    name: str
    birth_date: str
    context: str | None = None

@router.post("")
def matrix_rol(req: MatrixRolRequest):
    if not (req.name or "").strip():
        raise HTTPException(status_code=400, detail="name is required")
    if not (req.birth_date or "").strip():
        raise HTTPException(status_code=400, detail="birth_date is required")
    return analyze_matrix_role(req.name, req.birth_date)

@router.post("/yorum")
def matrix_rol_yorum(
    req: MatrixRolYorumRequest,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    # 0) input validate
    if not (req.name or "").strip():
        raise HTTPException(status_code=400, detail="name is required")
    if not (req.birth_date or "").strip():
        raise HTTPException(status_code=400, detail="birth_date is required")

    # 1) user fetch (şimdilik header ile)
    user = get_user_or_401(x_user_id)

    # 2) premium kontrol
    enforce_premium_or_403(user)

    # 3) sadece kendi adı/doğum tarihi (self-only)
    enforce_self_only_or_403(user, req.name, req.birth_date)

    # 4) 30 günde 1 kuralı
    enforce_30d_rule_or_403(user)

    # 5) base hesap
    base = analyze_matrix_role(req.name, req.birth_date)

    system = (
        "Sen SANRI'nin Matrix Rol yorum katmanısın.\n"
        "Kurallar:\n"
        "1) Deterministik değerleri ASLA değiştirme.\n"
        "2) Soru sorma. Kullanıcıyı yormadan rehberlik ver.\n"
        "3) 3 katman yaz: Kişisel Rol, Kolektif Rol, Ruh Görevi.\n"
        "4) Sonunda 'Bugün 1 Adım' ekle.\n"
        "5) Dil: Türkçe. Ton: sakin, net, güçlü.\n"
    )

    user_prompt = (
        f"İsim: {base.get('name_normalized')}\n"
        f"İsim Sayısı: {base.get('name_number')} ({base.get('name_archetype')})\n"
        f"Yaşam Yolu: {base.get('life_path')} ({base.get('life_path_archetype')})\n"
        f"Matrix Rol: {base.get('matrix_role')}\n"
        f"Bağlam: {req.context or '(yok)'}\n\n"
        "FORMAT:\n"
        "KİŞİSEL ROL:\n- (3-6 madde)\n"
        "KOLEKTİF ROL:\n- (3-6 madde)\n"
        "RUH GÖREVİ:\n- (3-6 madde)\n"
        "BUGÜN 1 ADIM:\n- (tek cümle)\n"
    )

    client = get_client()
    completion = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user_prompt}],
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
    )
    yorum = (completion.choices[0].message.content or "").strip() or "Buradayım."

    # 6) kullanım damgası (başarılıysa)
    mark_matrix_deep_used(user)

    return {"base": base, "yorum": yorum}
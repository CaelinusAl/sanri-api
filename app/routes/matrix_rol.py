import os
from fastapi import Depends
from app.db import get_db
from sqlalchemy.orm import Session
from app.services.user_repo import get_or_create_user
from app.services.premium_guard_db import ensure_premium, ensure_self_only, ensure_30_days
from datetime import datetime
from app.models.user_profile import UserProfile
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
    db: Session = Depends(get_db),
):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Missing X-User-Id")

    if not (req.name or "").strip():
        raise HTTPException(status_code=400, detail="name is required")
    if not (req.birth_date or "").strip():
        raise HTTPException(status_code=400, detail="birth_date is required")

    user = get_or_create_user(db, x_user_id)

    # premium + self-only + 30 gün
    ensure_premium(user)
    ensure_self_only(user, req.name, req.birth_date)
    ensure_30_days(user)

    # ilk kullanımda profili kilitle
    if not user.name and not user.birth_date:
        user.name = req.name.strip()
        user.birth_date = req.birth_date.strip()

    base = analyze_matrix_role(req.name, req.birth_date)

    # LLM yorumu
    client = get_client()
    completion = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user_prompt}],
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
    )
    yorum = (completion.choices[0].message.content or "").strip() or "Buradayım."

    # ✅ başarılıysa sayaç bas
    user.last_matrix_deep_analysis = datetime.utcnow()
    db.add(user)

    # ✅ profil hafıza güncelle (kısa özet)
    data = {
        "name_normalized": base.get("name_normalized"),
        "name_number": base.get("name_number"),
        "life_path": base.get("life_path"),
        "matrix_role": base.get("matrix_role"),
        "last_context": (req.context or "").strip(),
    }
    prof = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    if not prof:
        prof = UserProfile(user_id=user.id, data=data)
    else:
        prof.data = {**(prof.data or {}), **data}
    db.add(prof)

    db.commit()

    return {"base": base, "yorum": yorum}
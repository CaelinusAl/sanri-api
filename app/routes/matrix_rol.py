import os
from datetime import datetime
from fastapi import APIRouter, HTTPException, Header, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from openai import OpenAI

from app.db import get_db
from app.services.matrix_role import analyze_matrix_role
from app.services.user_repo import get_or_create_user
from app.services.premium_guard_db import ensure_premium, ensure_self_only, ensure_30_days
from app.models.user_profile import UserProfile

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

    base = analyze_matrix_role(req.name, req.birth_date)

    # ✅ Free teaser (merak açılımı)
    teaser = (
        f"Çekirdek Rol: {base.get('matrix_role')}\n\n"
        f"Gölge İpucu: Bu rolün gölgesi, kontrolü elden bırakmamak ve her şeyi tek başına taşımaktır.\n\n"
        f"Bugün 1 Adım: 1 şeyi tamamla, 1 şeyi bırak."
    )

    return {**base, "teaser": teaser}

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

    # 1) user
    user = get_or_create_user(db, x_user_id)

    # 2) premium + self-only + 30 gün
    ensure_premium(user)
    ensure_self_only(user, req.name, req.birth_date)
    ensure_30_days(user)

    # 3) ilk kullanımda profili kilitle
    if not user.name and not user.birth_date:
        user.name = req.name.strip()
        user.birth_date = req.birth_date.strip()

    # 4) deterministik base
    base = analyze_matrix_role(req.name, req.birth_date)

    # 5) LLM yorum promptu
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

    # 6) LLM call
    client = get_client()
    completion = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user_prompt}],
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
    )
    yorum = (completion.choices[0].message.content or "").strip() or "Buradayım."

    # 7) başarılıysa sayaç bas + profil hafıza güncelle
    user.last_matrix_deep_analysis = datetime.utcnow()
    db.add(user)

    profile_data = {
        "name_normalized": base.get("name_normalized"),
        "name_number": base.get("name_number"),
        "life_path": base.get("life_path"),
        "matrix_role": base.get("matrix_role"),
        "last_context": (req.context or "").strip(),
        "last_deep_at": user.last_matrix_deep_analysis.isoformat(),
    }

    prof = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    if not prof:
        prof = UserProfile(user_id=user.id, data=profile_data)
    else:
        prof.data = {**(prof.data or {}), **profile_data}
    db.add(prof)

    db.commit()

    return {"base": base, "yorum": yorum}
import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from openai import OpenAI

from app.services.matrix_role import analyze_matrix_role

router = APIRouter(prefix="/matrix-rol", tags=["matrix-rol"])

MODEL_NAME = (os.getenv("OPENAI_MODEL") or "gpt-4.1-mini").strip()
TEMPERATURE = float(os.getenv("SANRI_TEMPERATURE", "0.45")) # yorum daha net olsun
MAX_TOKENS = int(os.getenv("SANRI_MAX_TOKENS", "900"))

def get_client() -> OpenAI:
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY missing or empty")
    return OpenAI(api_key=api_key)

class MatrixRolYorumRequest(BaseModel):
    name: str
    birth_date: str
    context: str | None = None # kullanıcı ek not

class MatrixRolYorumResponse(BaseModel):
    base: dict
    yorum: str

@router.post("/yorum", response_model=MatrixRolYorumResponse)
def matrix_rol_yorum(req: MatrixRolYorumRequest):
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="name is required")
    if not req.birth_date.strip():
        raise HTTPException(status_code=400, detail="birth_date is required")

    base = analyze_matrix_role(req.name, req.birth_date)

    # ✅ LLM sadece yorumlar, deterministik değerleri değiştirmez
    system = (
        "Sen SANRI’nin Matrix Rol yorum katmanısın.\n"
        "Kurallar:\n"
        "1) Deterministik değerleri ASLA değiştirme.\n"
        "2) Soru sorma. Kullanıcıyı yormadan 'rehberlik' ver.\n"
        "3) 4 bölüm yaz: Öz, Gölge, Işık, Bugün 1 Adım.\n"
        "4) Ton: sakin, net, yargısız.\n"
    )

    user = (
        f"İsim: {base.get('name_normalized')}\n"
        f"İsim Sayısı: {base.get('name_number')} ({base.get('name_archetype')})\n"
        f"Yaşam Yolu: {base.get('life_path')} ({base.get('life_path_archetype')})\n"
        f"Matrix Rol: {base.get('matrix_role')}\n"
        f"Kullanıcı bağlamı: {req.context or '(yok)'}\n\n"
        "Şimdi 4 bölüm halinde yorum yaz."
    )

    client = get_client()
    completion = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
    )

    yorum = (completion.choices[0].message.content or "").strip() or "Buradayım."

    return {"base": base, "yorum": yorum}
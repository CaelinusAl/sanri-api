# app/main.py
import os
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.bilinc_alani import router as bilinc_router
from app.routes.auth import router as auth_router
from app.routes.subscription import router as subscription_router
from app.db import engine
from app.models import Base

load_dotenv()


def _split_origins(v: str) -> List[str]:
    """
    ENV örnek:
    SANRI_ALLOWED_ORIGINS=https://asksanri.com,https://www.asksanri.com,https://asksanri-frontend.vercel.app
    """
    if not v:
        return []
    return [x.strip().rstrip("/") for x in v.split(",") if x.strip()]


def _default_origin_regex() -> str:
    # Vercel preview + prod: https://*.vercel.app
    # İstersen kendi domain patternini de ekleriz.
    return r"^https:\/\/.*\.vercel\.app$"


# ✅ 1) App TEK KERE oluşturulur
app = FastAPI(title="SANRI API")

# ✅ 2) CORS TEK KERE eklenir (kritik)
allowed_origins = _split_origins(os.getenv("SANRI_ALLOWED_ORIGINS", ""))

# Eğer regex env verilmezse vercel preview'ları default regex ile aç
origin_regex_env = os.getenv("SANRI_ALLOWED_ORIGIN_REGEX", "").strip()
origin_regex: Optional[str] = origin_regex_env or _default_origin_regex()

# Eğer allow_origins boş ise bile regex çalışır; production domainlerini ENV ile eklemek en doğru yaklaşım.
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=origin_regex,
    allow_credentials=True, # cookie/auth varsa gerekli
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ Health check
@app.get("/health")
def health():
    return {"ok": True}

# ✅ DB init
@app.on_event("startup")
def _startup():
    Base.metadata.create_all(bind=engine)

# ✅ Routers
app.include_router(bilinc_router)
app.include_router(auth_router)
app.include_router(subscription_router)
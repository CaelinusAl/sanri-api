# app/main.py
import os
from dotenv import load_dotenv

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.admin import router as admin_router
from app.routes.bilinc_alani import router as bilinc_router
from app.routes.auth import router as auth_router
from app.routes.subscription import router as subscription_router
from app.db import engine
from app.models import Base

load_dotenv()


def _split_origins(v: str) -> list[str]:
    if not v:
        return []
    out: list[str] = []
    for x in v.split(","):
        x = x.strip()
        if not x:
            continue
        out.append(x.rstrip("/"))
    return out


# ✅ 1) App önce
app = FastAPI(title="SANRI API")


# ✅ 2) CORS hemen sonra (TEK KEZ)
allowed_origins = _split_origins(os.getenv("SANRI_ALLOWED_ORIGINS", ""))
origin_regex = (os.getenv("SANRI_ALLOWED_ORIGIN_REGEX", "").strip() or None)

# Güvenlik: env boş kalırsa minimum güvenli fallback
if not allowed_origins:
    allowed_origins = [
        "https://asksanri.com",
        "https://www.asksanri.com",
        "https://asksanri-frontend.vercel.app",
    ]

# Eğer regex boşsa vercel preview’ları da açalım
if not origin_regex:
    origin_regex = r"^https:\/\/.*\.vercel\.app$"

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=origin_regex,
    allow_credentials=True,
    allow_methods=["*"], # OPTIONS dahil
    allow_headers=["*"], # Content-Type dahil
)


# ✅ health
@app.get("/health")
def health():
    return {"ok": True}


# ✅ startup (db tablolar)
@app.on_event("startup")
def _startup():
    Base.metadata.create_all(bind=engine)


# ✅ router’lar
app.include_router(bilinc_router)
app.include_router(auth_router)
app.include_router(subscription_router)
app.include_router(admin_router)
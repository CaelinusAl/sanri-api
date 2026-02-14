# app/main.py
import os
from dotenv import load_dotenv

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.bilinc_alani import router as bilinc_router
from app.routes.auth import router as auth_router
from app.routes.subscription import router as subscription_router
from app.db import engine
from app.models import Base

load_dotenv()


def _split_origins(v: str) -> list[str]:
    if not v:
        return []
    return [x.strip().rstrip("/") for x in v.split(",") if x.strip()]


# ✅ 1) App ÖNCE tanımlanır
app = FastAPI(title="SANRI API")


# ✅ 2) CORS tek sefer eklenir (preflight dahil)
allowed_origins = _split_origins(os.getenv("SANRI_ALLOWED_ORIGINS", ""))
origin_regex = os.getenv("SANRI_ALLOWED_ORIGIN_REGEX", "").strip() or None

# fallback: env boşsa minimum güvenli liste
if not allowed_origins:
    allowed_origins = [
        "https://asksanri.com",
        "https://www.asksanri.com",
        "http://localhost:5173",
    ]

# vercel preview allow (env yoksa da çalışsın)
if not origin_regex:
    origin_regex = r"^https:\/\/.*\.vercel\.app$"

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
app.include_router(auth_router, prefix="/api")
app.include_router(subscription_router, prefix="/api")

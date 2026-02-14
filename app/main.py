# app/main.py
import os
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.bilinc_alani import router as bilinc_router
from app.routes.auth import router as auth_router
from app.routes.subscription import router as subscription_router
from app.routes.gates import router as gates_router  # varsa

from app.db import engine
from app.models import Base

load_dotenv()

def _split_origins(v: str) -> list[str]:
    if not v:
        return []
    return [x.strip().rstrip("/") for x in v.split(",") if x.strip()]

app = FastAPI(title="SANRI API")

# ✅ CORS (tek yerde, tek middleware)
allowed_origins = _split_origins(os.getenv("SANRI_ALLOWED_ORIGINS", ""))
origin_regex = os.getenv("SANRI_ALLOWED_ORIGIN_REGEX", "").strip() or None

# Güvenlik için: prod domainleri yoksa otomatik ekle
defaults = [
    "https://asksanri.com",
    "https://www.asksanri.com",
    "https://asksanri-frontend.vercel.app",
]
for d in defaults:
    if d not in allowed_origins:
        allowed_origins.append(d)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=origin_regex,   # örn: ^https:\/\/.*\.vercel\.app$
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"ok": True}

@app.on_event("startup")
def _startup():
    Base.metadata.create_all(bind=engine)

# ✅ routerlar (prefixleri kendi dosyalarında)
app.include_router(bilinc_router)
app.include_router(auth_router)
app.include_router(subscription_router)
app.include_router(gates_router)  
# app/main.py
from dotenv import load_dotenv
load_dotenv()

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.admin import router as admin_router
from app.routes.bilinc_alani import router as bilinc_router
from app.routes.auth import router as auth_router
from app.routes.subscription import router as subscription_router
from app.routes.awakenmis_sehirler import router as awakened_cities_router
from app.routes.matrix_rol import router as matrix_rol_router
from app.routes.events import router as events_router
from app.routes.world_events_admin import router as world_events_admin_router
from app.routes.world_events_public import router as world_events_public_router
from app.routes.sanri_voice import router as sanri_voice_router
from app.db import engine
from app.models.base import Base



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


app = FastAPI(title="SANRI API")


@app.get("/")
def root():
    return {"status": "ok", "service": "SANR AP"}


@app.get("/health")
def health():
    return {"ok": True}


@app.on_event("startup")
def _startup():
    import app.models  # tek satır yeter
    Base.metadata.create_all(bind=engine)
# --------------------
# CORS (FXED)
# --------------------
allowed_origins = _split_origins(os.getenv("SANR_ALLOWED_ORGNS", ""))
origin_regex = os.getenv("SANR_ALLOWED_ORGN_REGEX", "").strip() or None

# Local dev
local_dev_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8081",
    "http://127.0.0.1:8081",
]

# Defaults (if env bosa)
if not allowed_origins:
    allowed_origins = [
        "https://asksanri.com",
        "https://www.asksanri.com",
        "https://asksanri-frontend.vercel.app",
        "https://api.asksanri.com",
    ]

# Her durumda local dev ekle + tekrarlar engelle
allowed_origins = list(dict.fromkeys([*allowed_origins, *local_dev_origins]))

# Vercel preview deploylara izin veren regex (env bosa default)
if not origin_regex:
    origin_regex = r"^https:\/\/.*\.vercel\.app$"

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins, #  dinamik liste
    allow_origin_regex=r"^https:\/\/.*\.vercel\.app$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------
# ROUTERS
# --------------------
app.include_router(bilinc_router)
app.include_router(auth_router)
app.include_router(subscription_router)
app.include_router(admin_router)
app.include_router(awakened_cities_router)
app.include_router(matrix_rol_router)
app.include_router(events_router)
app.include_router(world_events_admin_router)
app.include_router(world_events_public_router)
app.include_router(sanri_voice_router)


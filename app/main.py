# app/main.py
from dotenv import load_dotenv
load_dotenv()

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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
from app.routes.content import router as content_router
from app.routes.daily_stream import router as stream_router
from app.routes.rituals import router as rituals_router
from app.routes.consciousness import router as consciousness_router
from app.routes.system_feed import router as system_feed_router
from app.routes.world_events import router as world_events_router
from app.routes.ritual_feed import router as ritual_feed_router
from app.routes.me import router as me_router
from app.routes.memory_profile import router as memory_router
from app.routes.insights import router as insights_router
from app.routes.profile import router as profile_router
from app.routes.memory import router as memory_router
from app.routes.activity import router as activity_router
from app.services.feed_scheduler import start_scheduler
from app.routes.memory_state import router as memory_state_router
from app.routes.device import router as device_router
from app.routes.push import router as push_router
from app.routes.dream import router as dream_router
from app.routes import global_signal




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


app = FastAPI()

@app.on_event("startup")
def start_background_jobs():
    start_scheduler()
      
@app.get("/")
def root():
    return {"status": "ok", "service": "SANRI API"}

@app.get("/health")
def health():
    return {"status": "ok"}

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
app.include_router(content_router)
app.include_router(stream_router)
app.include_router(rituals_router)
app.include_router(consciousness_router)
app.include_router(system_feed_router)
app.include_router(world_events_router)
app.include_router(ritual_feed_router)
app.include_router(me_router)
app.include_router(memory_router)
app.include_router(insights_router)
app.include_router(profile_router)
app.include_router(memory_router)
app.include_router(activity_router)
app.include_router(memory_state_router)
app.include_router(device_router)
app.include_router(push_router)
app.include_router(dream_router)
app.include_router(global_signal.router)
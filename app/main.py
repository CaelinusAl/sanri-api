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




from app.db import engine
from app.models import Base


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
    return {"status": "ok", "service": "SANRI API"}


# ----- CORS -----
allowed_origins = _split_origins(os.getenv("SANRI_ALLOWED_ORIGINS", ""))
origin_regex = os.getenv("SANRI_ALLOWED_ORIGIN_REGEX", "").strip() or None

# ✅ Local dev origins
local_dev_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

# Eğer env ile origin tanımlanmadıysa default liste
if not allowed_origins:
    allowed_origins = [
        "https://asksanri.com",
        "https://www.asksanri.com",
        "https://asksanri-frontend.vercel.app",
    ]

# ✅ Her durumda local dev originlerini ekle (tekrarları engelle)
allowed_origins = list(dict.fromkeys([*allowed_origins, *local_dev_origins]))

# Vercel preview deploylara izin veren regex
if not origin_regex:
    origin_regex = r"^https:\/\/.*\.vercel\.app$"

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8081",
        "http://127.0.0.1:8081",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://asksanri.com",
        "https://www.asksanri.com",
        "https://asksanri-frontend.vercel.app",
        "https://api.asksanri.com",
    ],
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


# ----- ROUTERS -----
app.include_router(bilinc_router)
app.include_router(auth_router)
app.include_router(subscription_router)
app.include_router(admin_router)
app.include_router(awakened_cities_router)
app.include_router(matrix_rol_router)



# app/main.py
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from dotenv import load_dotenv

from app.routes.bilinc_alani import router as bilinc_router
from app.routes.auth import router as auth_router
from app.routes.subscription import router as subscription_router

load_dotenv()

app = FastAPI(title="SANRI API")

@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")

def _split_origins(v: str) -> list[str]:
    if not v:
        return []
    return [x.strip().rstrip("/") for x in v.split(",") if x.strip()]

allowed_origins = _split_origins(os.getenv("SANRI_ALLOWED_ORIGINS", ""))
origin_regex = os.getenv("SANRI_ALLOWED_ORIGIN_REGEX", "").strip() or None

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"ok": True}

app.include_router(bilinc_router)
app.include_router(auth_router)
app.include_router(subscription_router)
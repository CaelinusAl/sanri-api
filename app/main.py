# app/main.py
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from dotenv import load_dotenv

from app.routes.bilinc_alani import router as bilinc_router
from app.routes.auth import router as auth_router
from app.routes.subscription import router as subscription_router

load_dotenv()

app = FastAPI(title="SANRI API")

# ✅ CORS (Vercel + custom domains + localhost)
allowed_origins = [
    "https://asksanri.com",
    "https://www.asksanri.com",
    "https://asksanri.vercel.app",
    "http://localhost:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"^https:\/\/.*\.vercel\.app$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ Static mount (panel + prompts)
STATIC_DIR = Path(__file__).resolve().parent / "static"  # app/static
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
def root():
    # Panel varsa oraya, yoksa health’e
    panel = STATIC_DIR / "panel.html"
    if panel.exists():
        return RedirectResponse(url="/static/panel.html")
    return {"status": "ok"}

@app.get("/health")
def health():
    return {"status": "ok"}

# ✅ API routers
app.include_router(bilinc_router)          # /bilinc-alani/ask
app.include_router(auth_router)            # /api/auth/*
app.include_router(subscription_router)    # /api/subscription/*
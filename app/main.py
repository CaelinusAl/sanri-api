# app/main.py
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from app.routes.bilinc_alani import router as bilinc_router
from app.routes.sanri_voice import router as voice_router

load_dotenv()

app = FastAPI(title="SANRI API")

# 🔥 CORS – EN ÜSTE
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🔥 STATIC (panel + prompts)
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# 🔥 ROUTERS
app.include_router(bilinc_router)
app.include_router(voice_router)

# 🔥 ROOT → PANEL
@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/static/panel.html")

@app.get("/health")
def health():
    return {"status": "ok"}
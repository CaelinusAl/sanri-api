# app/main.py
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from dotenv import load_dotenv

from app.routes.bilinc_alani import router as bilinc_router

load_dotenv()

app = FastAPI()

# ✅ CORS — NET ve SAĞLAM
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://asksanri.com",
        "https://www.asksanri.com",
        "https://asksanri.vercel.app",
        "https://asksanri-frontend.vercel.app",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ Static
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
def root():
    return RedirectResponse(url="/static/panel.html")

@app.get("/health")
def health():
    return {"status": "ok"}

# ✅ Bilinç Alanı
app.include_router(bilinc_router)
# app/main.py
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from dotenv import load_dotenv

from app.routes.bilinc_alani import router as bilinc_router

load_dotenv()

app = FastAPI(title="SANRI API")

# ✅ CORS: Panel başka domain'e gitse bile çalışsın
# (wildcard + credentials birlikte sorun çıkarır, o yüzden credentials=False)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ Static mount (panel + prompts)
STATIC_DIR = Path(__file__).resolve().parent / "static"  # app/static
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
def root():
    return RedirectResponse(url="/static/panel.html")

@app.get("/health")
def health():
    return {"status": "ok"}

# ✅ Only one router for now (ayağa kalkınca diğerlerini ekleriz)
app.include_router(bilinc_router)
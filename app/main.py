# app/main.py
from pathlib import Path
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from fastapi.responses import RedirectResponse

from app.routes.bilinc_alani import router as bilinc_router
from app.routes.sanri_voice import router as voice_router
# from app.routes.content import router as content_router
load_dotenv()

app = FastAPI(title="SANRI API")
@app.get("/")
def root():
    return RedirectResponse(url="/static/panel.html")

# CORS (şimdilik serbest)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static mount (panel + prompts)
STATIC_DIR = Path(__file__).resolve().parent / "static"   # app/static
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Routers
app.include_router(bilinc_router)
app.include_router(voice_router)
# app.include_router(content_router)



@app.get("/health")
def health():
    return {"status": "ok"}
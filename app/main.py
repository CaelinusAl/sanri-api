[15:09, 07.02.2026] Celine River: # app/routes/bilinc_alani.py
import os
import traceback
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from openai import OpenAI

from app.prompts.system_base import build_system_prompt

router = APIRouter(prefix="/bilinc-alani", tags=["bilinc-alani"])

# Model
MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()

# =======================
# Schemas
# =======================

class AskRequest(BaseModel):
    message: Optional[str] = None
    question: Optional[str] = None
    session_id: Optional[str] = "default"
    mode: Optional[str] = "user"  # user | test | cocuk

    def text(self) -> str:
        return (self.message or self.question or "").strip()

class AskResponse(BaseModel…
[15:10, 07.02.2026] Celine River: git add app/routes/bilinc_alani.py
git commit -m "fix: robust LLM error handling and logging"
git push
[15:14, 07.02.2026] Celine River: # app/main.py
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from dotenv import load_dotenv

from app.routes.bilinc_alani import router as bilinc_router

# -------------------------------------------------
# ENV
# -------------------------------------------------
load_dotenv()

app = FastAPI(title="SANRI API")

# -------------------------------------------------
# CORS (Frontend + Local)
# -------------------------------------------------
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

# -------------------------------------------------
# Static (panel + prompts)
# -------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app.mount(
    "/static",
    StaticFiles(directory=STATIC_DIR),
    name="static",
)

# -------------------------------------------------
# Root
# -------------------------------------------------
@app.get("/")
def root():
    return RedirectResponse("/static/panel.html")

@app.get("/health")
def health():
    return {"status": "ok"}

# -------------------------------------------------
# Routes
# -------------------------------------------------
app.include_router(bilinc_router)
from pathlib import Path
import os
import traceback

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError

from dotenv import load_dotenv
load_dotenv()

from app.routes.bilinc_alani import router as bilinc_router
from app.routes.matrix_alani import router as matrix_router
from app.routes.rituel_alani import router as rituel_router
from app.routes.sanri_voice import router as voice_router
from app.routes.membership import router as membership_router
from pydantic import BaseModel   
from typing import Optional

class AskPayload(BaseModel):
    question: str
    mode: Optional[str] = "ayna_sade"

app = FastAPI(title="SANRI API")

# ROUTERS
app.include_router(bilinc_router)
app.include_router(matrix_router)
app.include_router(rituel_router)
app.include_router(voice_router)

app = FastAPI(title="SANRI API")
from fastapi.middleware.cors import CORSMiddleware

origins = [
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://127.0.0.1:3000",
    "http://localhost:3000",
    "https://asksanri.com",
    "https://www.asksanri.com",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],  # x-sanri-token dahil
)

# ---------- CORS ----------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://asksanri.com",
        "https://www.asksanri.com",
        "https://caelinusal.com",
        "https://www.caelinusal.com",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path.cwd() / "app" / "static"
# Eğer yanlış klasörden çalıştırırsan fallback dene
if not STATIC_DIR.exists():
    STATIC_DIR = Path.cwd() / "static"

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ---------- GLOBAL EXCEPTION HANDLERS ----------
@app.exception_handler(Exception)
async def all_exception_handler(request: Request, exc: Exception):
    print("\n=== EXCEPTION ===")
    print("PATH:", request.url.path)
    print("METHOD:", request.method)
    print("ERROR:", repr(exc))
    traceback.print_exc()
    return JSONResponse(status_code=500, content={"detail": str(exc)})

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    print("\n=== 422 VALIDATION ===")
    print("PATH:", request.url.path)
    print("METHOD:", request.method)
    print("BODY ERRORS:", exc.errors())
    return JSONResponse(status_code=422, content={"detail": exc.errors()})

# ---------- ROUTERS ----------
app.include_router(bilinc_router)
app.include_router(voice_router)
app.include_router(membership_router)

# ---------- HEALTH ----------
@app.get("/health")
def health():
    return {"status": "ok"}

# ---------- ASK (minimum working endpoint) ----------
class AskPayload(BaseModel):
    question: str
    mode: str | None = "ayna_sade"

@app.post("/ask")
def ask(payload: AskPayload):
    q = payload.question.strip()
    mode = payload.mode or "ayna_sade"

    if mode == "ayna_eylem":
        answer = "1) Hedef.\n2) Engel.\n3) 10 dk adım."
    elif mode == "ayna_derin":
        answer = "His + ihtiyaç. Soru: 'Hangi eski rol çalışıyor?'"
    else:
        answer = "Seni duydum. Şu an en çok neye ihtiyacın var?"

    return {"mode": mode, "answer": answer}

# ---------- ROOT ----------
@app.get("/")
def root():
    # app/static/index.html varsa onu aç
    return RedirectResponse(url="/static/index.html")
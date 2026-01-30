import traceback
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from app.routes.bilinc_alani import router as bilinc_router
from app.routes.sanri_voice import router as voice_router
from app.routes.membership import router as membership_router

app = FastAPI(title="SANRI API")

# ---------- CORS ----------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://asksanri.com",
        "https://www.asksanri.com",
        "https://caelinusal.com",
        "https://www.caelinusal.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
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

# ---------- STATIC (panel.html burada) ----------
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# ---------- ROUTERS ----------
app.include_router(bilinc_router)
app.include_router(voice_router)
app.include_router(membership_router)

# ---------- HEALTH ----------
@app.get("/health")
def health():
    return {"status": "ok"}

# ---------- ASK ----------
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

# ---------- ROOT (panel) ----------
@app.get("/")
def root():
    return RedirectResponse(url="/static/index.html")
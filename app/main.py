# app/main.py
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from app.routes.bilinc_alani import router as bilinc_router
from app.routes.auth import router as auth_router
from app.routes.subscription import router as subscription_router
from app.db import engine
from app.models import Base

load_dotenv()

# ✅ 1) app önce tanımlanır
app = FastAPI(title="SANRI API")
@app.get("/health")
def health():
    return {"ok": True}

# ✅ 2) sonra event decorator gelir
@app.on_event("startup")
def _startup():
    Base.metadata.create_all(bind=engine)

# ✅ CORS
allowed_origins = [
    "https://asksanri.com",
    "https://www.asksanri.com",
    "https://asksanri-frontend.vercel.app",
    "http://localhost:5173",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ routers
app.include_router(bilinc_router)
app.include_router(auth_router)
app.include_router(subscription_router)

# (opsiyonel) static
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

@app.get("/")
def root():
    return {"ok": True, "service": "sanri-api"}

@app.get("/docs", include_in_schema=False)
def docs_redirect():
    return RedirectResponse(url="/docs")
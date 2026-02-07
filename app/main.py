# app/main.py
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from dotenv import load_dotenv

# Routers
from app.routes.bilinc_alani import router as bilinc_router
from app.routes.auth import router as auth_router
from app.routes.membership import router as membership_router

load_dotenv()

app = FastAPI(title="SANRI API")

# ✅ CORS: custom domain + all Vercel preview domains
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://asksanri.com",
        "https://www.asksanri.com",
        "https://asksanri.vercel.app",
        "http://localhost:5173",
    ],
    # allows any https://*.vercel.app (preview + prod)
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
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


# ✅ API routers
# Bilinc routes (whatever prefix is defined inside bilinc_alani.py)
app.include_router(bilinc_router)

# Auth & subscription routes (frontend calls /api/...)
app.include_router(auth_router, prefix="/api")
app.include_router(membership_router, prefix="/api")
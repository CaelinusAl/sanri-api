# app/main.py

import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, JSONResponse
from dotenv import load_dotenv

from app.routes.bilinc_alani import router as bilinc_router

# --------------------------------------------------
# ENV
# --------------------------------------------------
load_dotenv()

# --------------------------------------------------
# APP
# --------------------------------------------------
app = FastAPI(
    title="SANRI API",
    version="1.0.0",
)

# --------------------------------------------------
# CORS
# --------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://asksanri.com",
        "https://www.asksanri.com",
        "http://localhost:5173",
    ],
    allow_origin_regex=r"^https:\/\/.*\.vercel\.app$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------
# STATIC FILES (panel.html, js, css)
# --------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# --------------------------------------------------
# ROUTES
# --------------------------------------------------
@app.get("/", include_in_schema=False)
def root():
    # Panel varsa oraya, yoksa health
    panel = STATIC_DIR / "panel.html"
    if panel.exists():
        return RedirectResponse(url="/static/panel.html")
    return JSONResponse({"status": "ok", "service": "sanri-api"})

@app.get("/health", include_in_schema=False)
def health():
    return {"status": "ok"}

# --------------------------------------------------
# API ROUTERS
# --------------------------------------------------
app.include_router(bilinc_router)

# --------------------------------------------------
# FALLBACK
# --------------------------------------------------
@app.exception_handler(404)
def not_found(, _):
    return JSONResponse(
        status_code=404,
        content={"detail": "Not Found"},
    )
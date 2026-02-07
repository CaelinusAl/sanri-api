# app/main.py
import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, JSONResponse
from dotenv import load_dotenv

from app.routes.bilinc_alani import router as bilinc_router

load_dotenv()

app = FastAPI(title="SANRI API")

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

BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"

@app.get("/")
def root():
    return JSONResponse({"status": "sanri-api online"})

@app.get("/health")
def health():
    return {"status": "ok"}

app.include_router(bilinc_router)
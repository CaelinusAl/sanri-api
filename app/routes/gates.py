# app/routes/gates.py
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/gates", tags=["gates"])

BASE_DIR = Path(__file__).resolve().parents[1] # app/
PROMPS_DIR = BASE_DIR / "static" / "promps" # sende "promps" diye duruyor

def _load(name: str):
    p = PROMPS_DIR / name
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {p}")
    return json.loads(p.read_text(encoding="utf-8"))

@router.get("/v2")
def gates_v2():
    return _load("gates_v2.json")
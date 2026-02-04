from fastapi import APIRouter
from pathlib import Path
import json

router = APIRouter(prefix="/content", tags=["content"])

BASE_DIR = Path(_file_).resolve().parents[1] / "content"

@router.get("/book/{name}")
def get_book(name: str):
    path = BASE_DIR / "book" / f"{name}.json"
    if not path.exists():
        return {"error": "Book not found"}
    return json.loads(path.read_text(encoding="utf-8"))

@router.get("/ritual/{name}")
def get_ritual(name: str):
    path = BASE_DIR / "rituals" / f"{name}.json"
    if not path.exists():
        return {"error": "Ritual not found"}
    return json.loads(path.read_text(encoding="utf-8"))
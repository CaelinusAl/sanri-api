from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pathlib import Path
import json

router = APIRouter(prefix="/api/gates", tags=["gates"])

BASE_DIR = Path(__file__).resolve().parent.parent
PROMPTS_DIR = BASE_DIR / "static" / "prompts"


def _load_json(name: str):
    file_path = PROMPTS_DIR / name
    if not file_path.exists():
        return JSONResponse(
            {"detail": f"File not found: {name}"},
            status_code=404,
        )
    return json.loads(file_path.read_text(encoding="utf-8"))


@router.get("/v1")
def gates_v1():
    return _load_json("gates_v1.json")


@router.get("/v2")
def gates_v2():
    return _load_json("gates_v2.json")

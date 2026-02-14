from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pathlib import Path
import json

router = APIRouter(prefix="/api/gates", tags=["gates"])

BASE_DIR = Path(_file_).resolve().parent.parent

GATES_V2_PATH = BASE_DIR / "static" / "prompts" / "gates_v2.json"

def load_json(name: str):
    file_path = PROMPTS_DIR / name
    
    if not file_path.exists():
        return JSONResponse(
            {"detail": f"File not found: {file_path}"},
            status_code=404
        )
    
    return json.loads(file_path.read_text(encoding="utf-8"))

@router.get("/v1")
def gates_v1():
    return load_json("gates_v1.json")

@router.get("/gates/v2")
def get_gates_v2():
    if not GATES_V2_PATH.exists():
        return {"detail": f"File not found: {GATES_V2_PATH}"}
    return json.loads(GATES_V2_PATH.read_text(encoding="utf-8"))
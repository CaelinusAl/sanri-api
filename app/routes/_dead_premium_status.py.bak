import os
import json
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/content", tags=["content"])

RITUALS_DIR = os.path.join(os.path.dirname(__file__), "..", "content", "rituals")
RITUALS_DIR = os.path.abspath(RITUALS_DIR)

def _safe_load_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        raise HTTPException(status_code=500, detail={"code": "RITUAL_JSON_READ_FAILED"})

@router.get("/ritual-packs")
def ritual_packs():
    if not os.path.isdir(RITUALS_DIR):
        return {"items": []}

    items = []
    for fn in os.listdir(RITUALS_DIR):
        if not fn.endswith(".json"):
            continue
        path = os.path.join(RITUALS_DIR, fn)
        obj = _safe_load_json(path)
        items.append({
            "ritual_pack_id": obj.get("ritual_pack_id") or fn.replace(".json", ""),
            "mode": obj.get("mode") or "read_only",
            "description": obj.get("description") or "",
            "ritual_count": len(obj.get("rituals") or []),
        })

    # sabit sıralama
    items.sort(key=lambda x: x["ritual_pack_id"])
    return {"items": items}

@router.get("/ritual-pack/{ritual_pack_id}")
def ritual_pack_detail(ritual_pack_id: str):
    fn = f"{ritual_pack_id}.json"
    path = os.path.join(RITUALS_DIR, fn)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail={"code": "RITUAL_PACK_NOT_FOUND"})
    return _safe_load_json(path)
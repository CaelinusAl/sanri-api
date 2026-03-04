import os
import json
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/rituals", tags=["rituals"])

BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "content", "rituals")


def read_pack(pack_id: str):
    path = os.path.join(BASE_DIR, pack_id + ".json")

    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="RITUAL_PACK_NOT_FOUND")

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@router.get("/packs")
def list_packs():
    items = []

    for f in os.listdir(BASE_DIR):
        if not f.endswith(".json"):
            continue

        path = os.path.join(BASE_DIR, f)

        try:
            with open(path, "r", encoding="utf-8") as fp:
                obj = json.load(fp)

            items.append(
                {
                    "ritual_pack_id": obj.get("ritual_pack_id"),
                    "description": obj.get("description"),
                    "count": len(obj.get("rituals", [])),
                }
            )

        except Exception:
            continue

    return {"items": items}


@router.get("/packs/{pack_id}")
def get_pack(pack_id: str):
    return read_pack(pack_id)
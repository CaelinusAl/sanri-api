import json, os
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/awakened-content", tags=["awakened-content"])

_DATA = None

def _load():
    global _DATA
    if _DATA is not None:
        return _DATA
    p = Path(__file__).resolve().parent.parent / "static" / "data" / "awakened_content.json"
    if not p.exists():
        _DATA = {}
        return _DATA
    with open(p, encoding="utf-8") as f:
        _DATA = json.load(f)
    return _DATA


@router.get("/list")
def list_cities():
    data = _load()
    out = []
    for code in sorted(data.keys()):
        entry = data[code]
        out.append({
            "code": code,
            "city": entry.get("city", ""),
            "title": entry.get("base", {}).get("tr", {}).get("title", ""),
        })
    return out


@router.get("/{code}")
def get_city_content(
    code: str,
    lang: str = Query("tr", regex="^(tr|en)$"),
    layer: str = Query("base", regex="^(base|deepC|history|numerology|symbols|ritual|lab|all)$"),
):
    data = _load()
    padded = code.zfill(2)
    entry = data.get(padded)
    if not entry:
        raise HTTPException(404, detail="CITY_NOT_FOUND")

    city_name = entry.get("city", "")
    layers = ["base", "deepC", "history", "numerology", "symbols", "ritual", "lab"]

    if layer == "all":
        result = {"code": padded, "city": city_name, "layers": {}}
        for l in layers:
            block = entry.get(l, {}).get(lang)
            if block and (block.get("story") or block.get("title")):
                result["layers"][l] = block
        return result

    block = entry.get(layer, {}).get(lang)
    if not block:
        raise HTTPException(404, detail="LAYER_NOT_FOUND")

    return {
        "code": padded,
        "city": city_name,
        "layer": layer,
        "lang": lang,
        "title": block.get("title", ""),
        "story": block.get("story", ""),
        "reflection": block.get("reflection", ""),
    }

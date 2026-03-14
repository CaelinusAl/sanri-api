import os
import json
import tempfile
from fastapi import APIRouter, HTTPException, UploadFile, File, Form

router = APIRouter(prefix="/content", tags=["content"])


def get_rituals_dir():
    """
    app/routes/rituals.py -> app/content/rituals
    Railway / Render path farklarını otomatik çözer
    """
    return os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "content", "rituals")
    )


def safe_read_json(path):
    """
    JSON bozuksa server crash olmasın
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


# ---------------------------------------------------------
# LIST ALL RITUAL PACKS
# ---------------------------------------------------------
@router.get("/ritual-packs")
def ritual_packs():
    base_dir = get_rituals_dir()

    if not os.path.isdir(base_dir):
        return {
            "items": [],
            "warning": "RITUALS_DIR_MISSING",
            "dir": base_dir
        }

    items = []

    try:
        files = os.listdir(base_dir)
    except Exception:
        return {
            "items": [],
            "warning": "RITUALS_DIR_LIST_FAILED",
            "dir": base_dir
        }

    for fn in files:
        if not fn.endswith(".json"):
            continue

        path = os.path.join(base_dir, fn)
        data = safe_read_json(path)

        if not isinstance(data, dict):
            continue

        pack_id = str(data.get("ritual_pack_id") or fn.replace(".json", "")).strip()
        description = str(data.get("description") or "").strip()
        rituals = data.get("rituals") or []
        ritual_count = len(rituals) if isinstance(rituals, list) else 0

        items.append(
            {
                "ritual_pack_id": pack_id,
                "description": description,
                "ritual_count": ritual_count,
            }
        )

    items.sort(key=lambda x: x["ritual_pack_id"])

    return {"items": items}


# ---------------------------------------------------------
# SINGLE RITUAL PACK
# ---------------------------------------------------------
@router.get("/ritual-pack/{pack_id}")
def ritual_pack_detail(pack_id: str):
    base_dir = get_rituals_dir()

    if not os.path.isdir(base_dir):
        raise HTTPException(
            status_code=404,
            detail={
                "code": "RITUALS_DIR_MISSING",
                "dir": base_dir
            },
        )

    pack_id = (pack_id or "").strip()
    path = os.path.join(base_dir, pack_id + ".json")

    if not os.path.isfile(path):
        raise HTTPException(
            status_code=404,
            detail={
                "code": "RITUAL_PACK_NOT_FOUND",
                "pack_id": pack_id
            },
        )

    data = safe_read_json(path)

    if not isinstance(data, dict):
        raise HTTPException(
            status_code=500,
            detail={
                "code": "RITUAL_JSON_READ_FAILED",
                "pack_id": pack_id
            },
        )

    return data


# ---------------------------------------------------------
# VOICE RITUAL ENGINE (v1 mock)
# ---------------------------------------------------------
@router.post("/rituel/voice")
async def rituel_voice(
    file: UploadFile = File(...),
    lang: str = Form("tr"),
    ritual_pack_id: str = Form("")
):
    temp_path = None

    try:
        suffix = os.path.splitext(file.filename or "rituel.m4a")[1] or ".m4a"

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            temp_path = tmp.name

        # v1 mock transcript
        if lang == "tr":
            transcript = "Bugün içimde bir ağırlık var."
            reply = (
                "Dur. Nefesini izle. "
                "Bu ağırlık senden geçiyor, ama sen onun kendisi değilsin. "
                "Bir katman çözülüyor."
            )
        else:
            transcript = "There is a heaviness inside me today."
            reply = (
                "Pause. Watch your breath. "
                "This weight is passing through you, but it is not what you are. "
                "A layer is dissolving."
            )

        return {
            "ok": True,
            "transcript": transcript,
            "reply": reply,
            "ritual_pack_id": ritual_pack_id,
            "lang": lang,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)
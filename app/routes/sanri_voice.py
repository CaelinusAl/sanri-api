import os
import tempfile
from fastapi import APIRouter, UploadFile, File, HTTPException
from openai import OpenAI

router = APIRouter(prefix="/api/voice", tags=["voice"])

def get_client() -> OpenAI:
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY missing")
    return OpenAI(api_key=api_key)

@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...), lang: str | None = None):
    # file: audio/m4a veya wav
    client = get_client()

    suffix = ".m4a"
    if file.filename and "." in file.filename:
        suffix = "." + file.filename.split(".")[-1].lower()

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp_path = tmp.name
        content = await file.read()
        tmp.write(content)

    try:
        with open(tmp_path, "rb") as f:
            result = client.audio.transcriptions.create(
                model=os.getenv("OPENAI_WHISPER_MODEL", "gpt-4o-mini-transcribe"),
                file=f,
                language=lang if lang in ("tr", "en") else None,
            )
        text = (getattr(result, "text", None) or "").strip()
        return {"text": text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TRANSCRIBE_ERROR: {e}")
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass
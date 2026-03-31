import os
import tempfile
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from openai import OpenAI
from app.services.ritual_engine import detect_intent, build_ritual

router = APIRouter(prefix="/content", tags=["ritual-engine"])


def _get_openai() -> OpenAI:
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY missing")
    return OpenAI(api_key=api_key)


def _transcribe_audio(file_path: str, lang: str) -> str:
    client = _get_openai()
    with open(file_path, "rb") as f:
        result = client.audio.transcriptions.create(
            model=os.getenv("OPENAI_WHISPER_MODEL", "gpt-4o-mini-transcribe"),
            file=f,
            language=lang if lang in ("tr", "en") else None,
        )
    return (getattr(result, "text", None) or "").strip()


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

        transcript = _transcribe_audio(temp_path, lang)

        if not transcript:
            raise HTTPException(
                status_code=400,
                detail="Ses dosyasindan metin cikarilmadi. Lutfen tekrar deneyin."
            )

        intent = detect_intent(transcript)
        ritual = build_ritual(intent=intent, transcript=transcript, lang=lang)

        return {
            **ritual,
            "transcript": transcript,
            "ritual_pack_id": ritual_pack_id,
            "lang": lang,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if temp_path:
            try:
                os.remove(temp_path)
            except Exception:
                pass

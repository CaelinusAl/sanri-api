from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import Response
from app.openai_client import get_client

router = APIRouter(prefix="/sanri_voice", tags=["sanri_voice"])

def synth(text: str, voice: str = "alloy") -> bytes:
    client = get_client()
    audio = client.audio.speech.create(
        model="gpt-4o-mini-tts",
        voice=voice,
        input=text
    )
    return audio.read()

@router.post("/speak")
def sanri_speak(payload: dict = Body(...)):
    text = payload.get("text")
    voice = payload.get("voice", "alloy")

    if not text:
        raise HTTPException(status_code=400, detail="text is required")

    audio_bytes = synth(text, voice)
    return Response(content=audio_bytes, media_type="audio/mpeg")
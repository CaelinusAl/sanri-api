import os
import requests
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

router = APIRouter()

ELEVEN_API_KEY = os.getenv("ELEVEN_API_KEY", "").strip()
ELEVEN_VOICE_ID = os.getenv("ELEVEN_VOICE_ID", "").strip()

class VoiceReq(BaseModel):
    text: str

@router.post("/voice/eleven")
def voice_eleven(req: VoiceReq):
    if not ELEVEN_API_KEY or not ELEVEN_VOICE_ID:
        raise HTTPException(status_code=500, detail="ELEVEN_API_KEY veya ELEVEN_VOICE_ID eksik")

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVEN_VOICE_ID}"
    headers = {
        "xi-api-key": ELEVEN_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "text": req.text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
  "stability": 0.65,
  "similarity_boost": 0.85,
  "style": 0.35,
  "use_speaker_boost": True
}
    }

    r = requests.post(url, json=payload, headers=headers)
    if r.status_code != 200:
        raise HTTPException(status_code=500, detail=f"ElevenLabs hata: {r.status_code} {r.text}")

    return Response(content=r.content, media_type="audio/mpeg")
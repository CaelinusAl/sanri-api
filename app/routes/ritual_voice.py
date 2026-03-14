from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from app.services.ritual_engine import detect_intent, build_ritual

router = APIRouter(prefix="/content", tags=["ritual-engine"])


@router.post("/rituel/voice")
async def rituel_voice(
    file: UploadFile = File(...),
    lang: str = Form("tr"),
    ritual_pack_id: str = Form("")
):
    try:
        # V1 mock transcript
        transcript = "İçimde bir ağırlık var ve bırakmak istiyorum."

        intent = detect_intent(transcript)
        ritual = build_ritual(intent=intent, transcript=transcript, lang=lang)

        return {
            **ritual,
            "transcript": transcript,
            "ritual_pack_id": ritual_pack_id,
            "lang": lang,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/ask", tags=["ask"])

class AskRequest(BaseModel):
    question: str
    mode: str | None = "ayna_sade"

@router.post("")
def ask(req: AskRequest):
    q = req.question.strip()

    if not q:
        return {"answer": "Sorunu duyamadım. Bir cümle yeter."}

    if req.mode == "ayna_sade":
        return {
            "answer": f"Ayna: Şu an söylediğin şey seni hangi duyguda tutuyor?\n\nSorun: {q}"
        }

    return {
        "answer": f"Seni duyuyorum.\n\nSorun: {q}"
    }
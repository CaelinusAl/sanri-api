from fastapi import APIRouter, Header, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.routes.bilinc_alani import AskRequest
from app.services.sanri_orchestrator import process_sanri

router = APIRouter(prefix="/bilinc-alani", tags=["bilinc-alani"])


@router.post("/ask")
def ask(
    req: AskRequest,
    x_user_id: str = Header(None),
    db: Session = Depends(get_db),
):
    result = process_sanri(
        user_id=int(x_user_id),
        message=req.message,
        db=db,
    )

    return result
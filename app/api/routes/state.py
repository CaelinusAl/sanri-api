from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import get_current_user_id
from app.db import get_db
from app.schemas.v1 import AuraStateResponse, AuraStateUpdate
from app.services.aura_state_service import get_or_create_state, update_state


router = APIRouter(prefix="/v1/aura", tags=["v1-aura"])


@router.get("/state", response_model=AuraStateResponse)
def get_state(user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
    return get_or_create_state(db, user_id)


@router.patch("/state", response_model=AuraStateResponse)
def patch_state(payload: AuraStateUpdate, user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
    return update_state(db, user_id, payload)

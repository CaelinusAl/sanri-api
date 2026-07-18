from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.legacy_identity import reject_unsafe_legacy_identity
from app.db import get_db

router = APIRouter(prefix="/device", tags=["device"])


class DeviceRegisterIn(BaseModel):
    user_id: int
    device_token: str
    platform: str | None = None
    lang: str | None = "tr"


@router.post("/register")
def register_device(payload: DeviceRegisterIn, db: Session = Depends(get_db)):
    del payload, db
    reject_unsafe_legacy_identity()

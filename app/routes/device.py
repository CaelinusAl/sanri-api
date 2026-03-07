# app/routes/device.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from fastapi import Depends

from app.db import get_db

router = APIRouter(prefix="/device", tags=["device"])


class DeviceRegisterIn(BaseModel):
    user_id: int
    device_token: str
    platform: str | None = None
    lang: str | None = "tr"


@router.post("/register")
def register_device(payload: DeviceRegisterIn, db: Session = Depends(get_db)):
    try:
        db.execute(
            """
            UPDATE users
            SET device_token = :token,
                platform = :platform,
                lang = :lang
            WHERE id = :uid
            """,
            {
                "token": payload.device_token,
                "platform": payload.platform,
                "lang": payload.lang or "tr",
                "uid": payload.user_id,
            },
        )
        db.commit()
        return {"ok": True}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
# app/services/memory.py

import uuid
from typing import List, Dict
from sqlalchemy.orm import Session

from app.models.memory import Memory


# ---------------------------------------------------
# SAVE MEMORY
# ---------------------------------------------------

def save_memory(db: Session, user_id: int, message: str, response: str):
    """
    Kullanıcı mesajını ve Sanrı cevabını hafızaya kaydeder
    """

    try:

        row = Memory(
            id=str(uuid.uuid4()),
            user_id=user_id,
            message=message,
            response=response
        )

        db.add(row)
        db.commit()

    except Exception:
        db.rollback()


# ---------------------------------------------------
# GET USER MEMORY
# ---------------------------------------------------

def get_user_memory(db: Session, user_id: int, limit: int = 12) -> List[Dict]:
    """
    Kullanıcının son konuşmalarını getirir
    """

    try:

        rows = (
            db.query(Memory)
            .filter(Memory.user_id == user_id)
            .order_by(Memory.created_at.desc())
            .limit(limit)
            .all()
        )

        rows.reverse()

        result = []

        for r in rows:
            result.append(
                {
                    "message": r.message or "",
                    "response": r.response or ""
                }
            )

        return result

    except Exception:
        return []
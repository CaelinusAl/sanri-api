# app/services/memory.py

from typing import List, Dict
from sqlalchemy.orm import Session

from app.models.memory import Memory


# ---------------------------------------------------
# SAVE MEMORY
# ---------------------------------------------------

def save_memory(db: Session, user_id, message: str, response: str):
    """
    Kullanıcı mesajını ve Sanrı cevabını hafızaya kaydeder
    """

    try:

        row = Memory(
            user_id=str(user_id),
            type="auto",
            input_text=message,
            output_text=response,
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
                    "message": r.input_text or "",
                    "response": r.output_text or ""
                }
            )

        return result

    except Exception:
        return []
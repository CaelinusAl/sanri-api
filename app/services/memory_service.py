from sqlalchemy.orm import Session
from sqlalchemy import text


def load_memory(db: Session, user_id: int, limit: int = 8) -> str:
    try:
        rows = db.execute(
            text("""
                SELECT type, content
                FROM user_memory
                WHERE user_id = :uid
                ORDER BY created_at DESC
                LIMIT :limit
            """),
            {"uid": user_id, "limit": limit},
        ).mappings().all()

        rows = list(reversed(rows))

        memory_lines = []
        for row in rows:
            content = str(row.get("content") or "").strip()
            kind = str(row.get("type") or "memory").strip()
            if content:
                memory_lines.append(f"{kind}: {content[:700]}")

        return "\n".join(memory_lines).strip() or "No prior memory."
    except Exception as e:
        print("SANRI MEMORY LOAD ERROR =", repr(e))
        return "No prior memory."


def save_memory(
    db: Session,
    user_id: int,
    user_message: str,
    ai_message: str,
) -> None:
    try:
        db.execute(
            text("""
                INSERT INTO user_memory (user_id, type, content)
                VALUES (:uid, :type, :content)
            """),
            {
                "uid": user_id,
                "type": "user",
                "content": user_message[:4000],
            },
        )

        db.execute(
            text("""
                INSERT INTO user_memory (user_id, type, content)
                VALUES (:uid, :type, :content)
            """),
            {
                "uid": user_id,
                "type": "ai",
                "content": ai_message[:4000],
            },
        )

        db.commit()
    except Exception as e:
        db.rollback()
        print("SANRI MEMORY SAVE ERROR =", repr(e))
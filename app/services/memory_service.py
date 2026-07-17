import re
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.v1 import V1Memory


def list_memory(db: Session, user_id: str, limit: int = 20) -> list[V1Memory]:
    return list(
        db.scalars(
            select(V1Memory)
            .where(V1Memory.user_id == UUID(user_id))
            .order_by(V1Memory.created_at.desc())
            .limit(limit)
        )
    )


def memory_context(db: Session, user_id: str, limit: int = 10) -> list[str]:
    return []


def retrieve_relevant_memories(
    db: Session,
    user_id: str,
    query: str,
    *,
    active_project_id: str | None = None,
    category: str | None = None,
    query_embedding: list[float] | None = None,
    limit: int = 10,
    min_confidence: float = 0.5,
) -> list[V1Memory]:
    """Retrieve only approved, live memories relevant to the current request.

    A populated embedding uses pgvector ordering. Local SQLite/dev environments
    use a bounded keyword-overlap fallback instead of dumping recent memories.
    """
    words = {word for word in re.findall(r"\w+", query.casefold()) if len(word) > 2}
    if not words and not query_embedding:
        return []

    owner_id = UUID(user_id)
    statement = select(V1Memory).where(
        V1Memory.user_id == owner_id,
        V1Memory.approval_status == "approved",
        V1Memory.deleted_at.is_(None),
        V1Memory.confidence >= min_confidence,
    )
    if active_project_id:
        project_id = UUID(active_project_id)
        statement = statement.where(or_(V1Memory.project_id.is_(None), V1Memory.project_id == project_id))
    else:
        statement = statement.where(V1Memory.project_id.is_(None))
    if category:
        statement = statement.where(V1Memory.category == category)

    if query_embedding:
        statement = (
            statement.where(V1Memory.embedding.is_not(None))
            .order_by(V1Memory.embedding.cosine_distance(query_embedding))
            .limit(limit)
        )
        return list(db.scalars(statement))

    keyword_filters = [V1Memory.content.ilike(f"%{word}%") for word in words]
    rows = list(db.scalars(statement.where(or_(*keyword_filters)).limit(limit * 3)))
    scored = sorted(
        rows,
        key=lambda row: (
            sum(word in row.content.casefold() for word in words),
            row.confidence,
            row.created_at,
        ),
        reverse=True,
    )
    return scored[:limit]


def create_memory(
    db: Session,
    user_id: str,
    content: str,
    memory_type: str,
    *,
    source: str = "manual",
    category: str | None = None,
    confidence: float = 1.0,
    conversation_id: str | None = None,
    project_id: str | None = None,
) -> V1Memory:
    row = V1Memory(
        user_id=UUID(user_id),
        content=content,
        memory_type=memory_type,
        source=source,
        category=category,
        confidence=confidence,
        approval_status="approved",
        conversation_id=UUID(conversation_id) if conversation_id else None,
        project_id=UUID(project_id) if project_id else None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
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
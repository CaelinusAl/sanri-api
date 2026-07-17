from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.v1 import V1AuraState, V1Conversation, V1Memory, V1Project
from app.schemas.v1 import MemoryResponse, ProjectResponse
from app.services.memory_service import retrieve_relevant_memories
from app.services.aura_engine import AuraEngine


MIGRATION = (
    Path(__file__).parents[1]
    / "migrations"
    / "versions"
    / "20260717_0002_sprint2_memory_schema.py"
)
FOUNDATION_SQL = (
    Path(__file__).parents[1]
    / "migrations"
    / "versions"
    / "20260716_0001_v1_foundation.sql"
)


def test_phase1_models_include_memory_metadata_and_session_state():
    assert {
        "source",
        "category",
        "confidence",
        "approval_status",
        "conversation_id",
        "project_id",
        "updated_at",
        "deleted_at",
    }.issubset(V1Memory.__table__.columns.keys())
    assert {"active_mode", "detected_intent", "active_project_id", "next_smallest_action"}.issubset(
        V1AuraState.__table__.columns.keys()
    )
    assert {"active_mode", "detected_intent", "project_id", "close_summary", "closed_at"}.issubset(
        V1Conversation.__table__.columns.keys()
    )
    assert {"status", "last_checkpoint", "created_at"}.issubset(V1Project.__table__.columns.keys())


def test_approval_status_contract_is_closed():
    with pytest.raises(ValidationError):
        MemoryResponse(
            id=uuid4(),
            content="x",
            memory_type="explicit",
            source="manual",
            category=None,
            confidence=1,
            approval_status="pending",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            deleted_at=None,
        )


def test_project_response_exposes_structured_checkpoint():
    response = ProjectResponse(
        id=uuid4(),
        user_id=uuid4(),
        name="Memory Engine",
        status="active",
        current_sprint="Sprint 2",
        next_step="Retrieval testlerini yaz",
        last_checkpoint={"summary": "Schema tamamlandı", "next_action": "Testleri çalıştır"},
        notes=[],
        decisions=[],
        manifestos=[],
        risks=[],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    assert response.last_checkpoint["next_action"] == "Testleri çalıştır"


def test_retrieval_without_query_does_not_dump_memory():
    class UnexpectedDatabase:
        def scalars(self, _statement):
            raise AssertionError("Database must not be queried without a relevance query")

    assert retrieve_relevant_memories(UnexpectedDatabase(), str(uuid4()), "") == []


def test_retrieval_statement_requires_owner_approval_and_live_rows():
    class CaptureDatabase:
        def __init__(self):
            self.statement = None

        def scalars(self, statement):
            self.statement = statement
            return []

    db = CaptureDatabase()
    assert retrieve_relevant_memories(db, str(uuid4()), "kitap projesi") == []
    statement = str(db.statement)
    assert "v1_memories.user_id" in statement
    assert "v1_memories.approval_status" in statement
    assert "v1_memories.deleted_at" in statement


def test_migration_is_additive_and_reversible():
    text = MIGRATION.read_text(encoding="utf-8")
    assert "add column if not exists" in text
    assert "drop column if exists" in text
    assert "approval_status in ('proposed', 'approved', 'rejected')" in text
    assert "confidence >= 0 and confidence <= 1" in text


def test_foundation_user_ownership_and_rls_are_present():
    text = FOUNDATION_SQL.read_text(encoding="utf-8")
    assert "user_id uuid not null" in text
    assert "enable row level security" in text
    assert 'auth.uid() = user_id' in text


def test_aura_engine_retrieves_only_relevant_context(monkeypatch):
    class Memory:
        content = "Kullanıcı aşk romanı yazıyor."

    calls = {}

    def fake_retrieve(_db, user_id, query, **kwargs):
        calls.update(user_id=user_id, query=query, kwargs=kwargs)
        return [Memory()]

    monkeypatch.setattr("app.services.aura_engine.retrieve_relevant_memories", fake_retrieve)
    monkeypatch.setattr("app.services.aura_engine.state_context", lambda *_args: "")
    monkeypatch.setattr(
        "app.services.aura_engine.build_prompt",
        lambda **kwargs: kwargs["memories"][0],
    )

    prompt = AuraEngine().build_system_prompt(
        object(),
        user_id=str(uuid4()),
        mode="aura",
        language="tr",
        memory_consent=True,
        user_message="Aşk romanı projemize devam edelim.",
    )

    assert prompt.startswith("Kullanıcı aşk romanı yazıyor.")
    assert calls["query"] == "Aşk romanı projemize devam edelim."

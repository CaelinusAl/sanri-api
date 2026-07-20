"""Sprint 3 Wave B — /v1/memories route-level auth, ownership, consent, soft-delete."""

import inspect
from datetime import datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes import memories as memories_route
from app.core.config import Settings, get_settings
from app.core.security import get_current_user_id
from app.db import Base, get_db
from app.main import app
from app.models.v1 import V1Conversation, V1Memory, V1Project
from app.services.memory_service import create_memory, retrieve_relevant_memories


JWT_SECRET = "test-sprint3-memory-jwt-secret"
OWNER_ID = str(uuid4())
OTHER_ID = str(uuid4())


def _token(sub: str) -> str:
    return jwt.encode(
        {"sub": sub, "aud": "authenticated"},
        JWT_SECRET,
        algorithm="HS256",
    )


def _auth(sub: str = OWNER_ID) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(sub)}"}


@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", JWT_SECRET)
    monkeypatch.setenv("SUPABASE_JWT_AUDIENCE", "authenticated")
    get_settings.cache_clear()
    yield Settings(supabase_jwt_secret=JWT_SECRET, supabase_jwt_audience="authenticated")
    get_settings.cache_clear()


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[V1Project.__table__, V1Conversation.__table__, V1Memory.__table__],
    )
    SessionLocal = sessionmaker(bind=engine, future=True, autoflush=False, autocommit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(settings, db_session):
    def _db():
        yield db_session

    app.dependency_overrides[get_db] = _db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _seed_foreign_conversation(db_session) -> str:
    row = V1Conversation(user_id=uuid4(), title="foreign")
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return str(row.id)


def _seed_foreign_project(db_session) -> str:
    row = V1Project(user_id=uuid4(), name="foreign-project")
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return str(row.id)


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/v1/memories"),
        ("get", "/v1/memories/search"),
        ("post", "/v1/memories"),
        ("patch", f"/v1/memories/{uuid4()}"),
        ("delete", f"/v1/memories/{uuid4()}"),
    ],
)
def test_memories_endpoints_require_jwt(client, method, path):
    request = getattr(client, method)
    kwargs = {}
    if method == "post":
        kwargs["json"] = {"content": "x", "consent": True}
    if method == "patch":
        kwargs["json"] = {"content": "x", "approval_status": "approved", "consent": True}

    bare = request(path, **kwargs)
    assert bare.status_code == 401
    assert bare.json()["error"]["code"] == "auth_required"

    x_user_only = request(path, headers={"X-User-Id": OWNER_ID}, **kwargs)
    assert x_user_only.status_code == 401
    # X-User-Id must not satisfy get_current_user_id
    assert x_user_only.json()["error"]["code"] == "auth_required"


def test_x_user_id_does_not_authorize_even_with_junk_bearer(client):
    response = client.get(
        "/v1/memories",
        headers={"Authorization": "Bearer not-a-jwt", "X-User-Id": OWNER_ID},
    )
    assert response.status_code == 401


def test_foreign_conversation_and_project_rejected_on_save(client, db_session):
    foreign_conversation = _seed_foreign_conversation(db_session)
    foreign_project = _seed_foreign_project(db_session)

    conv = client.post(
        "/v1/memories",
        headers=_auth(),
        json={"content": "own memory", "consent": True, "conversation_id": foreign_conversation},
    )
    assert conv.status_code == 404
    assert conv.json()["error"]["code"] == "conversation_not_found"

    proj = client.post(
        "/v1/memories",
        headers=_auth(),
        json={"content": "own memory", "consent": True, "project_id": foreign_project},
    )
    assert proj.status_code == 404
    assert proj.json()["error"]["code"] == "project_not_found"


def test_list_and_search_never_return_other_users_memories(client, db_session):
    create_memory(db_session, OWNER_ID, "owner kitap notu", "explicit", approval_status="approved")
    create_memory(db_session, OTHER_ID, "other gizli not", "explicit", approval_status="approved")

    listed = client.get("/v1/memories", headers=_auth(OWNER_ID))
    assert listed.status_code == 200
    contents = {item["content"] for item in listed.json()}
    assert "owner kitap notu" in contents
    assert "other gizli not" not in contents

    searched = client.get("/v1/memories/search", headers=_auth(OWNER_ID), params={"q": "not"})
    assert searched.status_code == 200
    search_contents = {item["content"] for item in searched.json()}
    assert "owner kitap notu" in search_contents
    assert "other gizli not" not in search_contents


def test_create_memory_service_defaults_to_proposed(db_session):
    row = create_memory(db_session, OWNER_ID, "review me", "explicit")
    assert row.approval_status == "proposed"


def test_proposed_visible_to_owner_but_excluded_from_retrieval(client, db_session):
    proposed = create_memory(
        db_session,
        OWNER_ID,
        "kitap taslagi proposed",
        "explicit",
        approval_status="proposed",
    )
    approved = create_memory(
        db_session,
        OWNER_ID,
        "kitap taslagi approved",
        "explicit",
        approval_status="approved",
    )

    listed = client.get("/v1/memories", headers=_auth(OWNER_ID))
    assert listed.status_code == 200
    by_id = {item["id"]: item for item in listed.json()}
    assert by_id[str(proposed.id)]["approval_status"] == "proposed"
    assert by_id[str(approved.id)]["approval_status"] == "approved"

    hits = retrieve_relevant_memories(db_session, OWNER_ID, "kitap taslagi")
    hit_ids = {str(row.id) for row in hits}
    assert str(approved.id) in hit_ids
    assert str(proposed.id) not in hit_ids


def test_approve_requires_explicit_consent(client, db_session):
    row = create_memory(db_session, OWNER_ID, "needs consent", "explicit", approval_status="proposed")

    denied = client.patch(
        f"/v1/memories/{row.id}",
        headers=_auth(OWNER_ID),
        json={"content": "needs consent", "approval_status": "approved", "consent": False},
    )
    assert denied.status_code == 400
    assert denied.json()["error"]["code"] == "memory_consent_required"
    db_session.refresh(row)
    assert row.approval_status == "proposed"

    approved = client.patch(
        f"/v1/memories/{row.id}",
        headers=_auth(OWNER_ID),
        json={"content": "needs consent", "approval_status": "approved", "consent": True},
    )
    assert approved.status_code == 200
    assert approved.json()["approval_status"] == "approved"


def test_only_approved_live_owner_memories_are_retrieved(db_session):
    owner_approved = create_memory(
        db_session, OWNER_ID, "roman yazmak approved", "explicit", approval_status="approved"
    )
    create_memory(db_session, OWNER_ID, "roman yazmak proposed", "explicit", approval_status="proposed")
    create_memory(db_session, OTHER_ID, "roman yazmak other", "explicit", approval_status="approved")
    deleted = create_memory(
        db_session, OWNER_ID, "roman yazmak deleted", "explicit", approval_status="approved"
    )
    from datetime import datetime, timezone

    deleted.deleted_at = datetime.now(timezone.utc)
    db_session.commit()

    hits = retrieve_relevant_memories(db_session, OWNER_ID, "roman yazmak")
    assert [str(row.id) for row in hits] == [str(owner_approved.id)]


def test_jwt_subject_is_the_only_owner_scope(client, db_session, settings):
    """Valid JWT for OWNER cannot list OTHER's memories; dependency remains get_current_user_id."""
    create_memory(db_session, OTHER_ID, "secret", "explicit", approval_status="approved")
    response = client.get("/v1/memories", headers=_auth(OWNER_ID))
    assert response.status_code == 200
    assert response.json() == []
    assert get_current_user_id.__name__ == "get_current_user_id"
    assert settings.supabase_jwt_secret == JWT_SECRET


def test_delete_soft_deletes_owner_memory(client, db_session):
    row = create_memory(
        db_session, OWNER_ID, "silinecek kitap notu", "explicit", approval_status="approved"
    )

    deleted = client.delete(f"/v1/memories/{row.id}", headers=_auth(OWNER_ID))
    assert deleted.status_code == 204

    db_session.expire_all()
    persisted = db_session.get(V1Memory, row.id)
    assert persisted is not None
    assert persisted.deleted_at is not None
    assert isinstance(persisted.deleted_at, datetime)

    listed = client.get("/v1/memories", headers=_auth(OWNER_ID))
    assert listed.status_code == 200
    assert all(item["id"] != str(row.id) for item in listed.json())

    searched = client.get(
        "/v1/memories/search",
        headers=_auth(OWNER_ID),
        params={"q": "silinecek"},
    )
    assert searched.status_code == 200
    assert all(item["id"] != str(row.id) for item in searched.json())

    hits = retrieve_relevant_memories(db_session, OWNER_ID, "silinecek kitap")
    assert all(str(hit.id) != str(row.id) for hit in hits)


def test_delete_is_owner_scoped_and_repeat_is_404(client, db_session):
    row = create_memory(
        db_session, OWNER_ID, "owner only delete", "explicit", approval_status="approved"
    )

    foreign = client.delete(f"/v1/memories/{row.id}", headers=_auth(OTHER_ID))
    assert foreign.status_code == 404
    assert foreign.json()["error"]["code"] == "memory_not_found"
    db_session.refresh(row)
    assert row.deleted_at is None

    first = client.delete(f"/v1/memories/{row.id}", headers=_auth(OWNER_ID))
    assert first.status_code == 204
    second = client.delete(f"/v1/memories/{row.id}", headers=_auth(OWNER_ID))
    assert second.status_code == 404
    assert second.json()["error"]["code"] == "memory_not_found"

    db_session.expire_all()
    assert db_session.get(V1Memory, row.id) is not None


def test_v1_memory_delete_route_has_no_hard_delete_sql():
    source = inspect.getsource(memories_route.delete_memory)
    module_source = inspect.getsource(memories_route)
    assert "deleted_at" in source
    assert "delete(V1Memory)" not in module_source
    assert "from sqlalchemy import delete" not in module_source
    # Live rows only; already soft-deleted memories are not-found.
    assert "deleted_at.is_(None)" in source

"""PMP-01A.3.5 Recovery UI — thin-client API/UI integration evidence.

Security contracts stay in Recovery Service. This suite only proves the UI/HTTP
surface calls the server and does not invent policy.
"""

from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.application.assertion_store import DurableSignedAssertionStore
from app.application.recovery_link_store import DurableRecoveryLinkStore
from app.application.recovery_service import (
    InMemoryAuditWriter,
    RecoveryService,
    RecoveryStore,
)
from app.core.config import Settings, get_settings
from app.db import Base
from app.main import app
from app.models.recovery_assertion import V1RecoveryAssertion
from app.models.recovery_link import V1RecoveryLink
from app.schemas.recovery import CreateRecoveryLinkRequest, RevokeRecoveryLinkRequest


JWT_SECRET = "test-recovery-ui-jwt-secret"
REVIEWER_ROLE = "recovery_reviewer"
ASSERTION_SECRET = "test-recovery-ui-assertion-signing-secret"
CONSOLE = Path(__file__).parents[1] / "app" / "static" / "recovery-reviewer.html"


def _token(*, sub: str | None = None, role: str | None = REVIEWER_ROLE) -> str:
    payload = {
        "sub": sub or str(uuid4()),
        "aud": "authenticated",
        "app_metadata": {"role": role} if role else {},
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", JWT_SECRET)
    monkeypatch.setenv("SUPABASE_JWT_AUDIENCE", "authenticated")
    monkeypatch.setenv("RECOVERY_REVIEWER_ROLE", REVIEWER_ROLE)
    get_settings.cache_clear()
    yield Settings(
        supabase_jwt_secret=JWT_SECRET,
        supabase_jwt_audience="authenticated",
        recovery_reviewer_role=REVIEWER_ROLE,
        recovery_assertion_signing_secret=ASSERTION_SECRET,
    )
    get_settings.cache_clear()


@pytest.fixture
def service():
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[V1RecoveryAssertion.__table__, V1RecoveryLink.__table__],
    )
    SessionLocal = sessionmaker(bind=engine, future=True, autoflush=False, autocommit=False)
    session = SessionLocal()
    svc = RecoveryService(
        RecoveryStore(),
        InMemoryAuditWriter(),
        assertion_store=DurableSignedAssertionStore(session, signing_secret=ASSERTION_SECRET),
        link_store=DurableRecoveryLinkStore(session),
        db_session=session,
    )
    try:
        yield svc
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(settings, service):
    from app.api.routes import recovery as recovery_routes

    app.dependency_overrides[recovery_routes.get_recovery_service] = lambda: service
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _auth(role: str | None = REVIEWER_ROLE, sub: str | None = None) -> dict:
    return {"Authorization": f"Bearer {_token(sub=sub, role=role)}"}


def _approved_case_via_http(client) -> tuple[str, str]:
    r1, r2 = str(uuid4()), str(uuid4())
    created = client.post(
        "/v1/recovery/cases",
        headers=_auth(sub=r1),
        json={
            "operation_key": f"ui-create-{uuid4().hex[:10]}",
            "subject_user_id": str(uuid4()),
            "claimed_legacy_identity_ref": f"legacy-ui-{uuid4().hex[:8]}",
        },
    )
    assert created.status_code == 201
    case_id = created.json()["case"]["case_id"]
    assert (
        client.post(
            f"/v1/recovery/cases/{case_id}/evidence",
            headers=_auth(sub=r1),
            json={
                "operation_key": f"ui-ev-{uuid4().hex[:10]}",
                "evidence_hash": "evidence-hash-ui-aaaaaaaa",
                "evidence_type": "support_ticket",
            },
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/v1/recovery/cases/{case_id}/assertions",
            headers=_auth(sub=r1),
            json={
                "operation_key": f"ui-a1-{uuid4().hex[:10]}",
                "decision": "APPROVE",
                "rationale": "EVIDENCE_MATCH",
            },
        ).status_code
        == 200
    )
    a2 = client.post(
        f"/v1/recovery/cases/{case_id}/assertions",
        headers=_auth(sub=r2),
        json={
            "operation_key": f"ui-a2-{uuid4().hex[:10]}",
            "decision": "APPROVE",
            "rationale": "SECOND_EYE_OK",
        },
    )
    assert a2.status_code == 200
    assert a2.json()["case"]["state"] == "APPROVED"
    return case_id, r1


def test_console_is_thin_client_and_uses_required_endpoints(client):
    assert CONSOLE.is_file()
    text = CONSOLE.read_text(encoding="utf-8")
    assert "/v1/recovery/link/create" in text
    assert "/v1/recovery/link/revoke" in text
    assert "/v1/recovery/cases/" in text
    lowered = text.casefold()
    for needle in (
        "has_approval_quorum",
        "evaluatequorum",
        "cancreatelink",
        "iseligible",
        "token_hash",
        "rollout",
        "automatic linking",
    ):
        assert needle not in lowered

    res = client.get("/v1/recovery/console")
    assert res.status_code == 200
    assert "text/html" in res.headers.get("content-type", "")
    assert "Recovery Reviewer Console" in res.text


def test_link_schemas_forbid_client_authority_fields():
    with pytest.raises(ValidationError):
        CreateRecoveryLinkRequest(
            case_id=uuid4(),
            operation_key="link-create-0001",
            raw_token="should-fail",
        )
    with pytest.raises(ValidationError):
        RevokeRecoveryLinkRequest(
            case_id=uuid4(),
            operation_key="link-revoke-0001",
            reason="ok",
            reviewer_id=str(uuid4()),
        )


def test_read_only_case_status(client):
    case_id, actor = _approved_case_via_http(client)
    res = client.get(f"/v1/recovery/cases/{case_id}", headers=_auth(sub=actor))
    assert res.status_code == 200
    body = res.json()
    assert body["case_id"] == case_id
    assert body["state"] == "APPROVED"
    assert client.get(f"/v1/recovery/cases/{case_id}").status_code == 401


def test_http_link_create_and_idempotent_replay(client):
    case_id, actor = _approved_case_via_http(client)
    body = {"case_id": case_id, "operation_key": "http-link-create-0001"}
    r1 = client.post("/v1/recovery/link/create", headers=_auth(sub=actor), json=body)
    assert r1.status_code == 201
    payload = r1.json()
    assert payload["case"]["state"] == "LINK_CREATED"
    assert payload["raw_token"]
    assert payload["replayed"] is False
    assert "token_hash" not in payload
    assert "token_hash" not in payload["link"]

    r2 = client.post("/v1/recovery/link/create", headers=_auth(sub=actor), json=body)
    assert r2.status_code == 201
    assert r2.json()["replayed"] is True
    assert r2.json()["raw_token"] is None
    assert r2.json()["link"]["link_id"] == payload["link"]["link_id"]


def test_http_link_create_requires_reviewer_role(client):
    case_id, actor = _approved_case_via_http(client)
    assert (
        client.post(
            "/v1/recovery/link/create",
            json={"case_id": case_id, "operation_key": "http-link-unauth-0001"},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/v1/recovery/link/create",
            headers=_auth(role="user", sub=actor),
            json={"case_id": case_id, "operation_key": "http-link-nonrev-0001"},
        ).status_code
        == 403
    )


def test_http_link_create_without_quorum_fails_closed(client):
    opener = str(uuid4())
    created = client.post(
        "/v1/recovery/cases",
        headers=_auth(sub=opener),
        json={
            "operation_key": "http-noq-create-0001",
            "subject_user_id": str(uuid4()),
            "claimed_legacy_identity_ref": "legacy-http-noq",
        },
    )
    case_id = created.json()["case"]["case_id"]
    client.post(
        f"/v1/recovery/cases/{case_id}/evidence",
        headers=_auth(sub=opener),
        json={
            "operation_key": "http-noq-ev-0001",
            "evidence_hash": "evidence-hash-http-noq000",
            "evidence_type": "ticket",
        },
    )
    denied = client.post(
        "/v1/recovery/link/create",
        headers=_auth(sub=opener),
        json={"case_id": case_id, "operation_key": "http-noq-link-0001"},
    )
    assert denied.status_code == 409
    err = denied.json().get("detail") or denied.json().get("error") or {}
    assert err["code"] == "illegal_transition"


def test_http_link_revoke_requires_reason_and_is_idempotent(client):
    case_id, actor = _approved_case_via_http(client)
    created = client.post(
        "/v1/recovery/link/create",
        headers=_auth(sub=actor),
        json={"case_id": case_id, "operation_key": "http-rev-create-0001"},
    )
    assert created.status_code == 201
    link_id = created.json()["link"]["link_id"]

    assert (
        client.post(
            "/v1/recovery/link/revoke",
            headers=_auth(sub=actor),
            json={"case_id": case_id, "operation_key": "http-rev-0001", "reason": ""},
        ).status_code
        == 422
    )

    rev = client.post(
        "/v1/recovery/link/revoke",
        headers=_auth(sub=actor),
        json={
            "case_id": case_id,
            "operation_key": "http-rev-0001",
            "reason": "support_requested",
            "link_id": link_id,
        },
    )
    assert rev.status_code == 200
    assert rev.json()["case"]["state"] == "REVOKED"
    assert rev.json()["link"]["revoked_at"] is not None
    assert rev.json()["replayed"] is False

    again = client.post(
        "/v1/recovery/link/revoke",
        headers=_auth(sub=actor),
        json={
            "case_id": case_id,
            "operation_key": "http-rev-0001",
            "reason": "support_requested",
            "link_id": link_id,
        },
    )
    assert again.status_code == 200
    assert again.json()["replayed"] is True


def test_no_rollout_or_identity_migration_side_effects(client):
    case_id, actor = _approved_case_via_http(client)
    res = client.post(
        "/v1/recovery/link/create",
        headers=_auth(sub=actor),
        json={"case_id": case_id, "operation_key": "http-nogoal-0001"},
    )
    assert res.status_code == 201
    body = res.json()
    assert "rollout" not in body
    assert "identity_link" not in body
    assert "migration" not in body
    paths = {getattr(r, "path", "") for r in app.routes}
    recovery_paths = {p for p in paths if "/v1/recovery" in p}
    assert any(p.endswith("/link/create") for p in recovery_paths)
    assert any(p.endswith("/link/revoke") for p in recovery_paths)
    assert not any("rollout" in p for p in recovery_paths)
    assert not any("automatic" in p for p in recovery_paths)

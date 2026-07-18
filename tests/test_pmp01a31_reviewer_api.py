"""PMP-01A.3.1 Reviewer API — negative security evidence package."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from pydantic import ValidationError

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.application.assertion_store import DurableSignedAssertionStore
from app.application.recovery_service import (
    InMemoryAuditWriter,
    RecoveryService,
    RecoveryStore,
)
from app.core.config import Settings
from app.core.security import get_current_recovery_reviewer
from app.db import Base
from app.domain.recovery import RecoveryCaseState, RecoveryError
from app.main import app
from app.models.recovery_assertion import V1RecoveryAssertion
from app.schemas.recovery import CreateAssertionRequest


JWT_SECRET = "test-recovery-jwt-secret"
REVIEWER_ROLE = "recovery_reviewer"
ASSERTION_SECRET = "test-recovery-assertion-signing-secret"


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
    from app.core.config import get_settings

    get_settings.cache_clear()
    yield Settings(
        supabase_jwt_secret=JWT_SECRET,
        supabase_jwt_audience="authenticated",
        recovery_reviewer_role=REVIEWER_ROLE,
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
    Base.metadata.create_all(bind=engine, tables=[V1RecoveryAssertion.__table__])
    SessionLocal = sessionmaker(bind=engine, future=True, autoflush=False, autocommit=False)
    session = SessionLocal()
    assertion_store = DurableSignedAssertionStore(session, signing_secret=ASSERTION_SECRET)
    svc = RecoveryService(
        RecoveryStore(),
        InMemoryAuditWriter(),
        assertion_store=assertion_store,
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

    def _svc():
        return service

    app.dependency_overrides[recovery_routes.get_recovery_service] = _svc
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _auth(role: str | None = REVIEWER_ROLE, sub: str | None = None) -> dict:
    return {"Authorization": f"Bearer {_token(sub=sub, role=role)}"}


def test_client_cannot_supply_reviewer_id_in_assertion_body():
    with pytest.raises(ValidationError):
        CreateAssertionRequest(
            operation_key="op-key-12345678",
            decision="APPROVE",
            rationale="ok",
            reviewer_id=str(uuid4()),
        )


def test_unauthenticated_and_non_reviewer_rejected(client):
    body = {
        "operation_key": "create-case-0001",
        "subject_user_id": str(uuid4()),
        "claimed_legacy_identity_ref": "legacy-1",
    }
    assert client.post("/v1/recovery/cases", json=body).status_code == 401
    assert client.post("/v1/recovery/cases", json=body, headers=_auth(role=None)).status_code == 403
    assert client.post("/v1/recovery/cases", json=body, headers=_auth(role="user")).status_code == 403


def test_reviewer_identity_comes_only_from_jwt(settings):
    reviewer = uuid4()
    claims = {
        "sub": str(reviewer),
        "app_metadata": {"role": REVIEWER_ROLE},
    }
    assert get_current_recovery_reviewer(claims, settings) == reviewer


def test_create_case_idempotent_and_no_rollout_side_effects(client, service):
    subject = str(uuid4())
    body = {
        "operation_key": "create-case-idem-01",
        "subject_user_id": subject,
        "claimed_legacy_identity_ref": "legacy-idem-1",
    }
    r1 = client.post("/v1/recovery/cases", json=body, headers=_auth())
    r2 = client.post("/v1/recovery/cases", json=body, headers=_auth())
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["case"]["case_id"] == r2.json()["case"]["case_id"]
    assert r2.json()["replayed"] is True
    assert r1.json()["case"]["state"] == "EVIDENCE_PENDING"
    # Non-goals: no automatic linking / rollout fields
    assert "link" not in r1.json()
    assert "rollout" not in r1.json()


def test_happy_path_four_eyes_quorum(client):
    r1_id = str(uuid4())
    r2_id = str(uuid4())
    create = client.post(
        "/v1/recovery/cases",
        json={
            "operation_key": "hp-create-0001",
            "subject_user_id": str(uuid4()),
            "claimed_legacy_identity_ref": "legacy-hp-1",
        },
        headers=_auth(sub=r1_id),
    )
    case_id = create.json()["case"]["case_id"]
    client.post(
        f"/v1/recovery/cases/{case_id}/evidence",
        json={
            "operation_key": "hp-evidence-0001",
            "evidence_hash": "hash-aaaaaaaaaaaaaaaa",
            "evidence_type": "support_ticket",
        },
        headers=_auth(sub=r1_id),
    )
    a1 = client.post(
        f"/v1/recovery/cases/{case_id}/assertions",
        json={
            "operation_key": "hp-assert-0001",
            "decision": "APPROVE",
            "rationale": "evidence matches subject",
        },
        headers=_auth(sub=r1_id),
    )
    assert a1.json()["case"]["state"] == "AWAITING_SECOND_APPROVAL"
    a2 = client.post(
        f"/v1/recovery/cases/{case_id}/assertions",
        json={
            "operation_key": "hp-assert-0002",
            "decision": "APPROVE",
            "rationale": "second eye confirms",
        },
        headers=_auth(sub=r2_id),
    )
    assert a2.json()["case"]["state"] == "APPROVED"
    # A.3.1 must not create identity links
    assert a2.json()["case"]["state"] != "LINK_CREATED"


def test_four_eyes_conflict_same_reviewer(client, service):
    reviewer = str(uuid4())
    create = client.post(
        "/v1/recovery/cases",
        json={
            "operation_key": "fe-create-0001",
            "subject_user_id": str(uuid4()),
            "claimed_legacy_identity_ref": "legacy-fe-1",
        },
        headers=_auth(sub=reviewer),
    )
    case_id = create.json()["case"]["case_id"]
    client.post(
        f"/v1/recovery/cases/{case_id}/evidence",
        json={
            "operation_key": "fe-evidence-0001",
            "evidence_hash": "hash-bbbbbbbbbbbbbbbb",
            "evidence_type": "email_proof",
        },
        headers=_auth(sub=reviewer),
    )
    client.post(
        f"/v1/recovery/cases/{case_id}/assertions",
        json={
            "operation_key": "fe-assert-0001",
            "decision": "APPROVE",
            "rationale": "first",
        },
        headers=_auth(sub=reviewer),
    )
    conflict = client.post(
        f"/v1/recovery/cases/{case_id}/assertions",
        json={
            "operation_key": "fe-assert-0002",
            "decision": "APPROVE",
            "rationale": "same person second eye",
        },
        headers=_auth(sub=reviewer),
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "four_eyes_conflict"
    from uuid import UUID

    case = service.get_case(UUID(case_id))
    assert case.state == RecoveryCaseState.AWAITING_SECOND_APPROVAL
    assert len(case.assertions) == 1
    assert any(a.action == "four_eyes_conflict" for a in service.audit.records)


def test_terminal_case_immutable(client):
    reviewer = str(uuid4())
    create = client.post(
        "/v1/recovery/cases",
        json={
            "operation_key": "term-create-0001",
            "subject_user_id": str(uuid4()),
            "claimed_legacy_identity_ref": "legacy-term-1",
        },
        headers=_auth(sub=reviewer),
    )
    case_id = create.json()["case"]["case_id"]
    cancel = client.post(
        f"/v1/recovery/cases/{case_id}/cancel",
        json={"operation_key": "term-cancel-0001", "reason": "withdrawn"},
        headers=_auth(sub=reviewer),
    )
    assert cancel.json()["case"]["state"] == "CANCELLED"
    blocked = client.post(
        f"/v1/recovery/cases/{case_id}/evidence",
        json={
            "operation_key": "term-evidence-0001",
            "evidence_hash": "hash-cccccccccccccccc",
            "evidence_type": "x",
        },
        headers=_auth(sub=reviewer),
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "terminal_case_immutable"


def test_audit_failure_rolls_back_mutation(service):
    failing = InMemoryAuditWriter(fail=True)
    svc = RecoveryService(
        RecoveryStore(),
        failing,
        assertion_store=service.assertion_store,
        db_session=service.db_session,
    )
    with pytest.raises(RecoveryError) as err:
        svc.create_case(
            reviewer_id=uuid4(),
            operation_key="audit-fail-0001",
            subject_user_id=uuid4(),
            claimed_legacy_identity_ref="legacy-audit-fail",
        )
    assert err.value.code == "audit_failed"
    assert svc.store.cases == {}
    assert svc.store.operations == {}


def test_assertion_audit_failure_does_not_commit(service):
    store = RecoveryStore()
    audit = InMemoryAuditWriter(fail=False)
    svc = RecoveryService(
        store,
        audit,
        assertion_store=service.assertion_store,
        db_session=service.db_session,
    )
    case, _ = svc.create_case(
        reviewer_id=uuid4(),
        operation_key="af-create-0001",
        subject_user_id=uuid4(),
        claimed_legacy_identity_ref="legacy-af-1",
    )
    svc.submit_evidence(
        case_id=case.case_id,
        reviewer_id=uuid4(),
        operation_key="af-evidence-0001",
        evidence_hash="hash-dddddddddddddddd",
        evidence_type="ticket",
    )
    audit.fail = True
    with pytest.raises(RecoveryError) as err:
        svc.create_assertion(
            case_id=case.case_id,
            reviewer_id=uuid4(),
            operation_key="af-assert-0001",
            decision="APPROVE",
            rationale="should roll back",
        )
    assert err.value.code == "audit_failed"
    refreshed = svc.get_case(case.case_id)
    assert refreshed.state == RecoveryCaseState.READY_FOR_REVIEW
    assert refreshed.assertions == []
    assert service.assertion_store.list_for_case(case.case_id) == []


def test_illegal_transition_rejected(service):
    case, _ = service.create_case(
        reviewer_id=uuid4(),
        operation_key="il-create-0001",
        subject_user_id=uuid4(),
        claimed_legacy_identity_ref="legacy-il-1",
    )
    with pytest.raises(RecoveryError) as err:
        service.create_assertion(
            case_id=case.case_id,
            reviewer_id=uuid4(),
            operation_key="il-assert-0001",
            decision="APPROVE",
            rationale="too early",
        )
    assert err.value.code == "illegal_transition"


def test_assertion_without_store_fails_closed():
    svc = RecoveryService(RecoveryStore(), InMemoryAuditWriter())
    case, _ = svc.create_case(
        reviewer_id=uuid4(),
        operation_key="ns-create-0001",
        subject_user_id=uuid4(),
        claimed_legacy_identity_ref="legacy-ns-1",
    )
    svc.submit_evidence(
        case_id=case.case_id,
        reviewer_id=uuid4(),
        operation_key="ns-evidence-0001",
        evidence_hash="hash-nnnnnnnnnnnnnnnn",
        evidence_type="ticket",
    )
    with pytest.raises(RecoveryError) as err:
        svc.create_assertion(
            case_id=case.case_id,
            reviewer_id=uuid4(),
            operation_key="ns-assert-0001",
            decision="APPROVE",
            rationale="no store",
        )
    assert err.value.code == "assertion_store_required"


def test_expired_case_becomes_terminal(service):
    case, _ = service.create_case(
        reviewer_id=uuid4(),
        operation_key="ex-create-0001",
        subject_user_id=uuid4(),
        claimed_legacy_identity_ref="legacy-ex-1",
    )
    case.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    refreshed = service.get_case(case.case_id)
    assert refreshed.state == RecoveryCaseState.EXPIRED
    with pytest.raises(RecoveryError) as err:
        service.submit_evidence(
            case_id=case.case_id,
            reviewer_id=uuid4(),
            operation_key="ex-evidence-0001",
            evidence_hash="hash-eeeeeeeeeeeeeeee",
            evidence_type="x",
        )
    assert err.value.code == "terminal_case_immutable"


def test_duplicate_open_case_rejected(service):
    subject = uuid4()
    service.create_case(
        reviewer_id=uuid4(),
        operation_key="dup-create-0001",
        subject_user_id=subject,
        claimed_legacy_identity_ref="legacy-dup-1",
    )
    with pytest.raises(RecoveryError) as err:
        service.create_case(
            reviewer_id=uuid4(),
            operation_key="dup-create-0002",
            subject_user_id=subject,
            claimed_legacy_identity_ref="legacy-dup-2",
        )
    assert err.value.code == "duplicate_open_case"


def test_endpoints_do_not_expose_link_or_rollout_controls(client):
    # Recovery link UI paths are allowed; automatic identity linking / rollout are not.
    paths = {getattr(r, "path", "") for r in app.routes}
    recovery_paths = {p for p in paths if "/v1/recovery" in p}
    assert recovery_paths
    assert not any("rollout" in p for p in recovery_paths)
    assert not any("automatic" in p for p in recovery_paths)
    assert not any("identity" in p for p in recovery_paths)

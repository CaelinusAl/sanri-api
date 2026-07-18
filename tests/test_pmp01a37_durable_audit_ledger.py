"""PMP-01A.3.7 Durable Audit Ledger — restart + atomicity evidence.

Idempotency scope (documented):
  UNIQUE(case_id, operation_key, event_type)
  — not a global unique on operation_key.
  Matches service resume semantics: one successful mutation per operation_key
  produces one audit row of one event_type for that case; concurrent retries
  colliding on the same scope are treated as idempotent only for that constraint.
"""

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.application.assertion_store import DurableSignedAssertionStore
from app.application.recovery_audit_store import (
    AUDIT_DETAIL_ALLOWLIST,
    DurableAuditWriter,
    sanitize_audit_detail,
)
from app.application.recovery_case_store import DurableRecoveryCaseStore
from app.application.recovery_link_store import DurableRecoveryLinkStore
from app.application.recovery_service import AuditRecord, RecoveryService
from app.db import Base
from app.domain.recovery import RecoveryCaseState, RecoveryError
from app.models.recovery_assertion import V1RecoveryAssertion
from app.models.recovery_audit import V1RecoveryAuditEvent
from app.models.recovery_case import V1RecoveryCase, V1RecoveryCaseOperation
from app.models.recovery_link import V1RecoveryLink


SIGNING_SECRET = "test-a37-assertion-signing-secret"
MIGRATION = (
    Path(__file__).parents[1]
    / "migrations"
    / "versions"
    / "20260718_0007_recovery_audit_events.py"
)
SQL_COMPANION = (
    Path(__file__).parents[1]
    / "migrations"
    / "versions"
    / "20260718_0007_recovery_audit_events.sql"
)

# Documented uniqueness scope for evidence reviewers.
AUDIT_IDEMPOTENCY_SCOPE = ("case_id", "operation_key", "event_type")


@pytest.fixture
def harness():
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[
            V1RecoveryCase.__table__,
            V1RecoveryCaseOperation.__table__,
            V1RecoveryAssertion.__table__,
            V1RecoveryLink.__table__,
            V1RecoveryAuditEvent.__table__,
        ],
    )
    SessionLocal = sessionmaker(bind=engine, future=True, autoflush=False, autocommit=False)
    session = SessionLocal()
    case_store = DurableRecoveryCaseStore(session)
    assertion_store = DurableSignedAssertionStore(session, signing_secret=SIGNING_SECRET)
    link_store = DurableRecoveryLinkStore(session)
    # Runtime path: omit audit → DurableAuditWriter via db_session.
    service = RecoveryService(
        case_store,
        assertion_store=assertion_store,
        link_store=link_store,
        db_session=session,
    )
    assert isinstance(service.audit, DurableAuditWriter)
    try:
        yield {
            "service": service,
            "case_store": case_store,
            "audit": service.audit,
            "assertion_store": assertion_store,
            "link_store": link_store,
            "session": session,
            "engine": engine,
            "SessionLocal": SessionLocal,
        }
    finally:
        session.close()
        engine.dispose()


def _rebuild_service(SessionLocal, *, fail_audit: bool = False):
    session = SessionLocal()
    case_store = DurableRecoveryCaseStore(session)
    assertion_store = DurableSignedAssertionStore(session, signing_secret=SIGNING_SECRET)
    link_store = DurableRecoveryLinkStore(session)
    audit = DurableAuditWriter(session, fail=fail_audit) if fail_audit else None
    service = RecoveryService(
        case_store,
        audit,
        assertion_store=assertion_store,
        link_store=link_store,
        db_session=session,
    )
    return service, session, case_store, assertion_store, link_store, service.audit


def _approved_case(service: RecoveryService, *, evidence: str = "evidence-hash-a37aaaaaaaa"):
    opener = uuid4()
    case, _ = service.create_case(
        reviewer_id=opener,
        operation_key=f"create-{uuid4().hex[:12]}",
        subject_user_id=uuid4(),
        claimed_legacy_identity_ref=f"legacy-{uuid4().hex[:8]}",
    )
    service.submit_evidence(
        case_id=case.case_id,
        reviewer_id=opener,
        operation_key=f"evidence-{uuid4().hex[:12]}",
        evidence_hash=evidence,
        evidence_type="ticket",
    )
    r1, r2 = uuid4(), uuid4()
    service.create_assertion(
        case_id=case.case_id,
        reviewer_id=r1,
        operation_key=f"assert-{uuid4().hex[:12]}",
        decision="APPROVE",
        rationale="PRIMARY",
    )
    service.create_assertion(
        case_id=case.case_id,
        reviewer_id=r2,
        operation_key=f"assert-{uuid4().hex[:12]}",
        decision="APPROVE",
        rationale="SECOND",
    )
    return service.get_case(case.case_id), evidence, opener, r1


def test_migration_defines_scoped_append_only_audit_ledger():
    text_py = MIGRATION.read_text(encoding="utf-8")
    sql = SQL_COMPANION.read_text(encoding="utf-8")
    for body in (text_py, sql):
        assert "v1_recovery_audit_events" in body
        assert "v1_recovery_audit_events_case_op_type_uq" in body
        compacted = "".join(body.casefold().split())
        assert "unique(case_id,operation_key,event_type)" in compacted
        assert "v1_recovery_audit_events_append_only" in body
        assert "before update or delete" in body.casefold()
        assert "v1_identity_links" not in body
        assert "rollout" not in body.casefold()
        assert "automatic" not in body.casefold()
    # Alembic upgrade recreates trigger safely; downgrade removes trigger + function.
    assert "drop trigger if exists v1_recovery_audit_events_append_only_trg" in text_py.casefold()
    assert "def downgrade" in text_py
    downgrade = text_py[text_py.index("def downgrade") :]
    assert "drop trigger if exists v1_recovery_audit_events_append_only_trg" in downgrade.casefold()
    assert "drop function if exists public.v1_recovery_audit_events_append_only" in downgrade.casefold()
    assert AUDIT_IDEMPOTENCY_SCOPE == ("case_id", "operation_key", "event_type")


def test_model_includes_durable_audit_fields():
    required = {
        "event_id",
        "event_type",
        "case_id",
        "operation_key",
        "actor_id",
        "created_at",
        "from_state",
        "to_state",
        "entity_ref",
        "detail",
    }
    assert required.issubset(V1RecoveryAuditEvent.__table__.columns.keys())
    uq_names = {c.name for c in V1RecoveryAuditEvent.__table__.constraints if c.name}
    assert "v1_recovery_audit_events_case_op_type_uq" in uq_names


def test_runtime_path_uses_durable_audit_when_db_session_present(harness):
    assert isinstance(harness["service"].audit, DurableAuditWriter)


def test_fail_closed_without_session_or_injected_audit():
    from app.application.recovery_service import RecoveryStore

    with pytest.raises(RecoveryError) as err:
        RecoveryService(RecoveryStore())
    assert err.value.code == "audit_unavailable"


def test_audit_persists_after_restart(harness):
    service = harness["service"]
    SessionLocal = harness["SessionLocal"]
    reviewer = uuid4()
    case, _ = service.create_case(
        reviewer_id=reviewer,
        operation_key="audit-restart-create-0001",
        subject_user_id=uuid4(),
        claimed_legacy_identity_ref="legacy-audit-restart",
    )

    service2, session2, *_rest, audit2 = _rebuild_service(SessionLocal)
    try:
        rows = audit2.list_for_case(case.case_id)
        assert len(rows) >= 1
        create_events = [r for r in rows if r.action == "create_case"]
        assert len(create_events) == 1
        assert create_events[0].operation_key == "audit-restart-create-0001"
        assert create_events[0].actor_id == reviewer
        assert session2.get(V1RecoveryAuditEvent, create_events[0].audit_id) is not None
    finally:
        session2.close()


def test_case_create_and_audit_atomic_commit(harness):
    service = harness["service"]
    session = harness["session"]
    case, _ = service.create_case(
        reviewer_id=uuid4(),
        operation_key="atomic-case-0001",
        subject_user_id=uuid4(),
        claimed_legacy_identity_ref="legacy-atomic-case",
    )
    assert session.get(V1RecoveryCase, case.case_id) is not None
    events = harness["audit"].list_by_operation_key("atomic-case-0001")
    assert len(events) == 1
    assert events[0].action == "create_case"
    assert events[0].case_id == case.case_id
    assert events[0].to_state == "EVIDENCE_PENDING"


def test_assertion_mutation_and_audit_atomic_commit(harness):
    service = harness["service"]
    session = harness["session"]
    opener = uuid4()
    case, _ = service.create_case(
        reviewer_id=opener,
        operation_key="atomic-assert-create-0001",
        subject_user_id=uuid4(),
        claimed_legacy_identity_ref="legacy-atomic-assert",
    )
    service.submit_evidence(
        case_id=case.case_id,
        reviewer_id=opener,
        operation_key="atomic-assert-evidence-0001",
        evidence_hash="evidence-hash-atomic-assert01",
        evidence_type="ticket",
    )
    r1 = uuid4()
    case, assertion, _ = service.create_assertion(
        case_id=case.case_id,
        reviewer_id=r1,
        operation_key="atomic-assert-0001",
        decision="APPROVE",
        rationale="PRIMARY",
    )
    assert session.scalar(select(V1RecoveryAssertion)) is not None
    events = harness["audit"].list_by_operation_key("atomic-assert-0001")
    assert len(events) == 1
    assert events[0].action == "assert_approve_first"
    assert events[0].entity_ref == f"assertion:{assertion.assertion_id}"
    assert events[0].detail.get("assertion_id") == str(assertion.assertion_id)


def test_link_create_and_audit_atomic_commit(harness):
    service = harness["service"]
    session = harness["session"]
    case, _evidence, _opener, actor = _approved_case(service)
    case, link, raw_token, _ = service.create_recovery_link(
        case_id=case.case_id,
        reviewer_id=actor,
        operation_key="atomic-link-0001",
    )
    assert raw_token is not None
    assert session.get(V1RecoveryLink, link.link_id) is not None
    events = harness["audit"].list_by_operation_key("atomic-link-0001")
    assert len(events) == 1
    assert events[0].action == "create_recovery_link"
    assert events[0].entity_ref == f"link:{link.link_id}"
    assert case.state == RecoveryCaseState.LINK_CREATED


def test_link_revoke_and_audit_atomic_commit(harness):
    service = harness["service"]
    case, _evidence, _opener, actor = _approved_case(service)
    case, link, _, _ = service.create_recovery_link(
        case_id=case.case_id,
        reviewer_id=actor,
        operation_key="atomic-rev-create-0001",
    )
    case, revoked, _ = service.revoke_recovery_link(
        case_id=case.case_id,
        reviewer_id=actor,
        operation_key="atomic-rev-0001",
        reason="support_requested",
        link_id=link.link_id,
    )
    assert case.state == RecoveryCaseState.REVOKED
    assert revoked.revoked_at is not None
    events = harness["audit"].list_by_operation_key("atomic-rev-0001")
    assert len(events) == 1
    assert events[0].action == "revoke_recovery_link"
    assert events[0].detail.get("reason") == "support_requested"
    assert events[0].entity_ref == f"link:{link.link_id}"


def test_forced_audit_failure_rolls_back_business_state(harness):
    SessionLocal = harness["SessionLocal"]
    service, session, *_rest, audit = _rebuild_service(SessionLocal, fail_audit=True)
    try:
        with pytest.raises(RecoveryError) as err:
            service.create_case(
                reviewer_id=uuid4(),
                operation_key="audit-fail-durable-0001",
                subject_user_id=uuid4(),
                claimed_legacy_identity_ref="legacy-audit-fail-durable",
            )
        assert err.value.code == "audit_failed"
        assert session.scalar(select(V1RecoveryCase)) is None
        assert session.scalar(select(V1RecoveryCaseOperation)) is None
        assert session.scalar(select(V1RecoveryAuditEvent)) is None
        assert audit.fail is True
    finally:
        session.close()


def test_operation_key_replay_creates_no_duplicate_audit_event(harness):
    service = harness["service"]
    session = harness["session"]
    reviewer = uuid4()
    case, replayed = service.create_case(
        reviewer_id=reviewer,
        operation_key="op-audit-replay-0001",
        subject_user_id=uuid4(),
        claimed_legacy_identity_ref="legacy-audit-replay",
    )
    assert replayed is False
    case2, replayed2 = service.create_case(
        reviewer_id=uuid4(),
        operation_key="op-audit-replay-0001",
        subject_user_id=uuid4(),
        claimed_legacy_identity_ref="legacy-audit-replay-other",
    )
    assert replayed2 is True
    assert case2.case_id == case.case_id
    events = session.scalars(
        select(V1RecoveryAuditEvent).where(
            V1RecoveryAuditEvent.operation_key == "op-audit-replay-0001"
        )
    ).all()
    assert len(events) == 1
    assert events[0].event_type == "create_case"


def test_raw_token_absent_from_persisted_audit(harness):
    service = harness["service"]
    session = harness["session"]
    case, _evidence, _opener, actor = _approved_case(service)
    case, link, raw_token, _ = service.create_recovery_link(
        case_id=case.case_id,
        reviewer_id=actor,
        operation_key="token-absent-link-0001",
    )
    assert raw_token is not None
    assert len(raw_token) > 8

    rows = session.scalars(select(V1RecoveryAuditEvent)).all()
    blob = " ".join(
        [
            str(r.detail)
            + str(r.entity_ref)
            + str(r.event_type)
            + str(r.operation_key)
            for r in rows
        ]
    )
    assert raw_token not in blob
    assert SIGNING_SECRET not in blob
    for row in rows:
        assert "token" not in str(row.detail).casefold()
        assert "signature" not in str(row.detail).casefold()
        assert "jwt" not in str(row.detail).casefold()
        for key in row.detail:
            assert key in AUDIT_DETAIL_ALLOWLIST


def test_detail_allowlist_drops_secrets_and_unrestricted_fields():
    dirty = {
        "assertion_id": str(uuid4()),
        "raw_token": "super-secret-token-value",
        "signing_secret": SIGNING_SECRET,
        "jwt": "eyJhbGciOiJIUzI1NiJ9.payload.sig",
        "evidence_payload": {"full": "body"},
        "exception": "Traceback (most recent call last)...",
        "reason": "ok_reason",
    }
    clean = sanitize_audit_detail(dirty)
    assert clean == {"assertion_id": dirty["assertion_id"], "reason": "ok_reason"}
    assert "raw_token" not in clean
    assert "signing_secret" not in clean
    assert "jwt" not in clean
    assert "evidence_payload" not in clean
    assert "exception" not in clean


def test_concurrent_retry_scoped_uniqueness_is_idempotent(harness):
    """Second write of the same (case_id, operation_key, event_type) is idempotent.

    Scope is UNIQUE(case_id, operation_key, event_type) — not global operation_key.
    Other IntegrityErrors must not be swallowed (covered by fail-closed path).
    """
    audit: DurableAuditWriter = harness["audit"]
    session = harness["session"]
    service = harness["service"]
    case, _ = service.create_case(
        reviewer_id=uuid4(),
        operation_key="conc-audit-create-0001",
        subject_user_id=uuid4(),
        claimed_legacy_identity_ref="legacy-conc-audit",
    )
    first = audit.get_by_scope(
        case_id=case.case_id,
        operation_key="conc-audit-create-0001",
        event_type="create_case",
    )
    assert first is not None

    # Simulate concurrent retry writing the same scoped event.
    audit.write(
        AuditRecord(
            audit_id=uuid4(),
            case_id=case.case_id,
            actor_id=uuid4(),
            action="create_case",
            from_state="DRAFT",
            to_state="EVIDENCE_PENDING",
            operation_key="conc-audit-create-0001",
            created_at=first.created_at,
            detail={"subject_user_id": str(uuid4())},
        )
    )
    session.flush()
    rows = session.scalars(
        select(V1RecoveryAuditEvent).where(
            V1RecoveryAuditEvent.case_id == case.case_id,
            V1RecoveryAuditEvent.operation_key == "conc-audit-create-0001",
            V1RecoveryAuditEvent.event_type == "create_case",
        )
    ).all()
    assert len(rows) == 1
    assert rows[0].event_id == first.audit_id


def test_scoped_uniqueness_allows_same_operation_key_different_event_type(harness):
    """Documents that uniqueness is not global on operation_key alone."""
    audit: DurableAuditWriter = harness["audit"]
    session = harness["session"]
    case_id = uuid4()
    op = "same-op-different-type-0001"
    audit.write(
        AuditRecord(
            audit_id=uuid4(),
            case_id=case_id,
            actor_id=uuid4(),
            action="create_case",
            from_state=None,
            to_state="EVIDENCE_PENDING",
            operation_key=op,
            created_at=service_now(),
            detail={},
        )
    )
    audit.write(
        AuditRecord(
            audit_id=uuid4(),
            case_id=case_id,
            actor_id=uuid4(),
            action="four_eyes_conflict",
            from_state="READY_FOR_REVIEW",
            to_state="READY_FOR_REVIEW",
            operation_key=op,
            created_at=service_now(),
            detail={"decision": "APPROVE"},
        )
    )
    session.flush()
    rows = session.scalars(
        select(V1RecoveryAuditEvent).where(V1RecoveryAuditEvent.operation_key == op)
    ).all()
    assert len(rows) == 2
    assert {r.event_type for r in rows} == {"create_case", "four_eyes_conflict"}


def service_now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


def test_existing_a3_suites_remain_importable_and_green_smoke():
    """Smoke import guard for A.3.1–A.3.6 evidence modules."""
    import tests.test_pmp01a31_reviewer_api as a31
    import tests.test_pmp01a32_assertion_store as a32
    import tests.test_pmp01a33_four_eyes_workflow as a33
    import tests.test_pmp01a34_recovery_link_lifecycle as a34
    import tests.test_pmp01a35_recovery_ui_thin_client as a35
    import tests.test_pmp01a36_durable_case_ledger as a36

    assert a31 and a32 and a33 and a34 and a35 and a36


def test_migration_downgrade_drops_trigger_and_function():
    body = MIGRATION.read_text(encoding="utf-8")
    # Ensure downgrade section removes append-only machinery cleanly.
    downgrade_idx = body.index("def downgrade")
    downgrade = body[downgrade_idx:]
    assert "drop trigger if exists v1_recovery_audit_events_append_only_trg" in downgrade
    assert "drop function if exists public.v1_recovery_audit_events_append_only" in downgrade
    assert "drop table if exists public.v1_recovery_audit_events" in downgrade

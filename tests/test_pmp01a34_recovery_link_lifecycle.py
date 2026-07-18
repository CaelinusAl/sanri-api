"""PMP-01A.3.4 Recovery Link Lifecycle — negative evidence package."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.application.assertion_store import DurableSignedAssertionStore
from app.application.recovery_link_store import DurableRecoveryLinkStore
from app.application.recovery_service import (
    InMemoryAuditWriter,
    RecoveryService,
    RecoveryStore,
)
from app.db import Base
from app.domain.recovery import RecoveryCaseState, RecoveryError
from app.domain.recovery_link import hash_recovery_token
from app.models.recovery_assertion import V1RecoveryAssertion
from app.models.recovery_link import V1RecoveryLink


SIGNING_SECRET = "test-a34-assertion-signing-secret"
MIGRATION = (
    Path(__file__).parents[1]
    / "migrations"
    / "versions"
    / "20260718_0005_recovery_links.py"
)


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
        tables=[V1RecoveryAssertion.__table__, V1RecoveryLink.__table__],
    )
    SessionLocal = sessionmaker(bind=engine, future=True, autoflush=False, autocommit=False)
    session = SessionLocal()
    case_store = RecoveryStore()
    audit = InMemoryAuditWriter()
    assertion_store = DurableSignedAssertionStore(session, signing_secret=SIGNING_SECRET)
    link_store = DurableRecoveryLinkStore(session)
    service = RecoveryService(
        case_store,
        audit,
        assertion_store=assertion_store,
        link_store=link_store,
        db_session=session,
    )
    try:
        yield {
            "service": service,
            "case_store": case_store,
            "audit": audit,
            "assertion_store": assertion_store,
            "link_store": link_store,
            "session": session,
            "engine": engine,
            "SessionLocal": SessionLocal,
        }
    finally:
        session.close()
        engine.dispose()


def _approved_case(service: RecoveryService, *, evidence: str = "evidence-hash-a34aaaaaaaa"):
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
        evidence_type="support_ticket",
    )
    r1, r2 = uuid4(), uuid4()
    service.create_assertion(
        case_id=case.case_id,
        reviewer_id=r1,
        operation_key=f"assert-{uuid4().hex[:12]}",
        decision="APPROVE",
        rationale="EVIDENCE_MATCH",
    )
    service.create_assertion(
        case_id=case.case_id,
        reviewer_id=r2,
        operation_key=f"assert-{uuid4().hex[:12]}",
        decision="APPROVE",
        rationale="SECOND_EYE_OK",
    )
    case = service.get_case(case.case_id)
    assert case.state == RecoveryCaseState.APPROVED
    return case, evidence, r1


def test_migration_defines_link_store_without_identity_or_rollout():
    text = MIGRATION.read_text(encoding="utf-8")
    assert "v1_recovery_links" in text
    assert "token_hash" in text
    assert "revoked_at" in text
    assert "revoked_by" in text
    assert "raw_token" not in text
    assert "v1_identity_links" not in text
    assert "rollout" not in text.casefold()
    assert "automatic" not in text.casefold()


def test_model_stores_hash_not_raw_token():
    cols = set(V1RecoveryLink.__table__.columns.keys())
    assert "token_hash" in cols
    assert "token" not in cols
    assert "raw_token" not in cols
    assert "revoked_at" in cols
    assert "revoked_by" in cols
    assert "used_at" in cols


def test_create_requires_quorum(harness):
    service = harness["service"]
    opener = uuid4()
    case, _ = service.create_case(
        reviewer_id=opener,
        operation_key="noq-create-0001",
        subject_user_id=uuid4(),
        claimed_legacy_identity_ref="legacy-noq",
    )
    service.submit_evidence(
        case_id=case.case_id,
        reviewer_id=opener,
        operation_key="noq-evidence-0001",
        evidence_hash="evidence-hash-noquorum000",
        evidence_type="ticket",
    )
    service.create_assertion(
        case_id=case.case_id,
        reviewer_id=uuid4(),
        operation_key="noq-assert-0001",
        decision="APPROVE",
        rationale="ONLY_ONE",
    )
    with pytest.raises(RecoveryError) as err:
        service.create_recovery_link(
            case_id=case.case_id,
            reviewer_id=opener,
            operation_key="noq-link-0001",
        )
    assert err.value.code == "illegal_transition"
    assert harness["session"].scalar(select(V1RecoveryLink)) is None


def test_happy_path_create_returns_raw_token_once(harness):
    service = harness["service"]
    link_store = harness["link_store"]
    case, evidence, actor = _approved_case(service)

    case, link, raw_token, replayed = service.create_recovery_link(
        case_id=case.case_id,
        reviewer_id=actor,
        operation_key="link-create-0001",
    )
    assert replayed is False
    assert case.state == RecoveryCaseState.LINK_CREATED
    assert raw_token
    assert link.token_hash == hash_recovery_token(raw_token)
    assert link.evidence_reference_hash == evidence
    assert link.is_active(datetime.now(timezone.utc))

    row = harness["session"].scalar(select(V1RecoveryLink))
    assert row is not None
    assert row.token_hash == link.token_hash
    assert raw_token not in (row.token_hash, str(row.link_id), row.operation_key)

    case2, link2, raw_again, replayed2 = service.create_recovery_link(
        case_id=case.case_id,
        reviewer_id=actor,
        operation_key="link-create-0001",
    )
    assert replayed2 is True
    assert raw_again is None
    assert link2.link_id == link.link_id
    assert case2.state == RecoveryCaseState.LINK_CREATED
    assert len(link_store.list_for_case(case.case_id)) == 1


def test_terminal_case_cannot_create_link(harness):
    service = harness["service"]
    case, _evidence, actor = _approved_case(service)
    service.cancel_case(
        case_id=case.case_id,
        reviewer_id=actor,
        operation_key="term-cancel-0001",
        reason="abandon",
    )
    with pytest.raises(RecoveryError) as err:
        service.create_recovery_link(
            case_id=case.case_id,
            reviewer_id=actor,
            operation_key="term-link-0001",
        )
    assert err.value.code == "terminal_case_immutable"
    assert harness["session"].scalar(select(V1RecoveryLink)) is None


def test_expired_assertions_cannot_create_link(harness):
    service = harness["service"]
    assertion_store = harness["assertion_store"]
    case, evidence, actor = _approved_case(service)

    after_ttl = datetime.now(timezone.utc) + timedelta(hours=25)
    assert (
        assertion_store.has_approval_quorum(
            case_id=case.case_id,
            evidence_reference_hash=evidence,
            now=after_ttl,
        )
        is False
    )

    # Force clock forward for quorum check by expiring assertion rows.
    for row in harness["session"].scalars(select(V1RecoveryAssertion)).all():
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    harness["session"].flush()

    with pytest.raises(RecoveryError) as err:
        service.create_recovery_link(
            case_id=case.case_id,
            reviewer_id=actor,
            operation_key="exp-link-0001",
        )
    assert err.value.code == "assertion_expired"
    assert harness["session"].scalar(select(V1RecoveryLink)) is None
    refreshed = service.get_case(case.case_id)
    assert refreshed.state == RecoveryCaseState.EXPIRED


def test_only_one_active_link_per_case(harness):
    service = harness["service"]
    case, _evidence, actor = _approved_case(service)
    service.create_recovery_link(
        case_id=case.case_id,
        reviewer_id=actor,
        operation_key="one-link-0001",
    )
    # Force case back to APPROVED to probe store/service active-link guard.
    case_rec = harness["case_store"].cases[case.case_id]
    case_rec.state = RecoveryCaseState.APPROVED

    with pytest.raises(RecoveryError) as err:
        service.create_recovery_link(
            case_id=case.case_id,
            reviewer_id=actor,
            operation_key="one-link-0002",
        )
    assert err.value.code == "active_link_exists"
    assert len(harness["link_store"].list_for_case(case.case_id)) == 1


def test_revoke_requires_reason(harness):
    service = harness["service"]
    case, _evidence, actor = _approved_case(service)
    service.create_recovery_link(
        case_id=case.case_id,
        reviewer_id=actor,
        operation_key="rev-reason-link-0001",
    )
    with pytest.raises(RecoveryError) as err:
        service.revoke_recovery_link(
            case_id=case.case_id,
            reviewer_id=actor,
            operation_key="rev-reason-0001",
            reason="   ",
        )
    assert err.value.code == "revoke_reason_required"
    link = harness["link_store"].get_active_for_case(case.case_id)
    assert link is not None
    assert link.revoked_at is None


def test_revoke_records_metadata_and_is_idempotent(harness):
    service = harness["service"]
    case, _evidence, actor = _approved_case(service)
    case, link, _, _ = service.create_recovery_link(
        case_id=case.case_id,
        reviewer_id=actor,
        operation_key="rev-link-create-0001",
    )
    revoker = uuid4()
    case, revoked, replayed = service.revoke_recovery_link(
        case_id=case.case_id,
        reviewer_id=revoker,
        operation_key="rev-link-0001",
        reason="support_requested",
        link_id=link.link_id,
    )
    assert replayed is False
    assert case.state == RecoveryCaseState.REVOKED
    assert revoked.revoked_at is not None
    assert revoked.revoked_by == revoker
    assert revoked.revoke_reason == "support_requested"
    assert harness["link_store"].get_active_for_case(case.case_id) is None

    case2, revoked2, replayed2 = service.revoke_recovery_link(
        case_id=case.case_id,
        reviewer_id=revoker,
        operation_key="rev-link-0001",
        reason="support_requested",
        link_id=link.link_id,
    )
    assert replayed2 is True
    assert revoked2.link_id == revoked.link_id
    assert case2.state == RecoveryCaseState.REVOKED


def test_audit_failure_rolls_back_link_create(harness):
    service = harness["service"]
    audit = harness["audit"]
    case, _evidence, actor = _approved_case(service)
    audit.fail = True
    with pytest.raises(RecoveryError) as err:
        service.create_recovery_link(
            case_id=case.case_id,
            reviewer_id=actor,
            operation_key="audit-link-0001",
        )
    assert err.value.code == "audit_failed"
    refreshed = service.get_case(case.case_id)
    assert refreshed.state == RecoveryCaseState.APPROVED
    assert harness["session"].scalar(select(V1RecoveryLink)) is None


def test_audit_failure_rolls_back_link_revoke(harness):
    service = harness["service"]
    audit = harness["audit"]
    case, _evidence, actor = _approved_case(service)
    case, link, _, _ = service.create_recovery_link(
        case_id=case.case_id,
        reviewer_id=actor,
        operation_key="audit-rev-create-0001",
    )
    audit.fail = True
    with pytest.raises(RecoveryError) as err:
        service.revoke_recovery_link(
            case_id=case.case_id,
            reviewer_id=actor,
            operation_key="audit-rev-0001",
            reason="should_rollback",
        )
    assert err.value.code == "audit_failed"
    refreshed = service.get_case(case.case_id)
    assert refreshed.state == RecoveryCaseState.LINK_CREATED
    persisted = harness["link_store"].get(link.link_id)
    assert persisted.revoked_at is None


def test_expired_or_used_links_never_reactivate(harness):
    service = harness["service"]
    link_store = harness["link_store"]
    case, _evidence, actor = _approved_case(service)
    case, link, _, _ = service.create_recovery_link(
        case_id=case.case_id,
        reviewer_id=actor,
        operation_key="imm-link-0001",
    )
    link_store.mark_used(link.link_id)
    used = link_store.get(link.link_id)
    assert used.used_at is not None
    with pytest.raises(RecoveryError) as err:
        link_store.reactivate(link.link_id)
    assert err.value.code == "link_immutable"

    service.revoke_recovery_link(
        case_id=case.case_id,
        reviewer_id=actor,
        operation_key="imm-rev-0001",
        reason="cleanup",
        link_id=link.link_id,
    )
    revoked = link_store.get(link.link_id)
    assert revoked.revoked_at is not None
    assert revoked.used_at is not None
    with pytest.raises(RecoveryError) as err2:
        link_store.reactivate(link.link_id)
    assert err2.value.code == "link_immutable"


def test_assertion_revoke_invalidates_active_link(harness):
    service = harness["service"]
    assertion_store = harness["assertion_store"]
    case, evidence, actor = _approved_case(service)
    case, link, _, _ = service.create_recovery_link(
        case_id=case.case_id,
        reviewer_id=actor,
        operation_key="inv-link-0001",
    )
    approvals = assertion_store.list_valid_approvals(
        case_id=case.case_id, evidence_reference_hash=evidence
    )
    primary = approvals[0]
    case, _, _ = service.revoke_assertion(
        case_id=case.case_id,
        assertion_id=primary.assertion_id,
        reviewer_id=actor,
        operation_key="inv-assert-rev-0001",
    )
    assert case.state == RecoveryCaseState.REVOKED
    revoked_link = harness["link_store"].get(link.link_id)
    assert revoked_link.revoked_at is not None
    assert harness["link_store"].get_active_for_case(case.case_id) is None


def test_operation_key_resume_after_restart_no_new_token(harness):
    service = harness["service"]
    case_store = harness["case_store"]
    SessionLocal = harness["SessionLocal"]
    case, _evidence, actor = _approved_case(service)
    case, link, raw_token, _ = service.create_recovery_link(
        case_id=case.case_id,
        reviewer_id=actor,
        operation_key="resume-link-0001",
    )
    assert raw_token

    session2 = SessionLocal()
    try:
        assertion_store2 = DurableSignedAssertionStore(session2, signing_secret=SIGNING_SECRET)
        link_store2 = DurableRecoveryLinkStore(session2)
        service2 = RecoveryService(
            case_store,
            InMemoryAuditWriter(),
            assertion_store=assertion_store2,
            link_store=link_store2,
            db_session=session2,
        )
        case2, link2, raw_again, replayed = service2.create_recovery_link(
            case_id=case.case_id,
            reviewer_id=actor,
            operation_key="resume-link-0001",
        )
        assert replayed is True
        assert raw_again is None
        assert link2.link_id == link.link_id
        assert case2.state == RecoveryCaseState.LINK_CREATED
        assert len(link_store2.list_for_case(case.case_id)) == 1
    finally:
        session2.close()


def test_link_store_required(harness):
    case, _evidence, actor = _approved_case(harness["service"])
    service_no_link = RecoveryService(
        harness["case_store"],
        harness["audit"],
        assertion_store=harness["assertion_store"],
        db_session=harness["session"],
    )
    with pytest.raises(RecoveryError) as err:
        service_no_link.create_recovery_link(
            case_id=case.case_id,
            reviewer_id=actor,
            operation_key="need-link-store-0001",
        )
    assert err.value.code == "link_store_required"
    assert harness["session"].scalar(select(V1RecoveryLink)) is None

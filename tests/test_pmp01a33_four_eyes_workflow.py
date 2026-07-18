"""PMP-01A.3.3 Four-Eyes Workflow Enforcement — negative evidence package."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.application.assertion_store import DurableSignedAssertionStore
from app.application.recovery_service import (
    InMemoryAuditWriter,
    RecoveryService,
    RecoveryStore,
)
from app.db import Base
from app.domain.recovery import RecoveryCaseState, RecoveryError
from app.models.recovery_assertion import V1RecoveryAssertion


SIGNING_SECRET = "test-a33-assertion-signing-secret"


@pytest.fixture
def harness():
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine, tables=[V1RecoveryAssertion.__table__])
    SessionLocal = sessionmaker(bind=engine, future=True, autoflush=False, autocommit=False)
    session = SessionLocal()
    case_store = RecoveryStore()
    audit = InMemoryAuditWriter()
    assertion_store = DurableSignedAssertionStore(session, signing_secret=SIGNING_SECRET)
    service = RecoveryService(
        case_store,
        audit,
        assertion_store=assertion_store,
        db_session=session,
    )
    try:
        yield {
            "service": service,
            "case_store": case_store,
            "audit": audit,
            "assertion_store": assertion_store,
            "session": session,
            "engine": engine,
            "SessionLocal": SessionLocal,
        }
    finally:
        session.close()
        engine.dispose()


def _ready_case(service: RecoveryService, *, evidence: str = "evidence-hash-a33aaaaaaa"):
    reviewer = uuid4()
    case, _ = service.create_case(
        reviewer_id=reviewer,
        operation_key=f"create-{uuid4().hex[:12]}",
        subject_user_id=uuid4(),
        claimed_legacy_identity_ref=f"legacy-{uuid4().hex[:8]}",
    )
    service.submit_evidence(
        case_id=case.case_id,
        reviewer_id=reviewer,
        operation_key=f"evidence-{uuid4().hex[:12]}",
        evidence_hash=evidence,
        evidence_type="support_ticket",
    )
    return service.get_case(case.case_id), evidence


def test_assertion_mutations_require_store():
    service = RecoveryService(RecoveryStore(), InMemoryAuditWriter())
    case, _ = service.create_case(
        reviewer_id=uuid4(),
        operation_key="req-store-create",
        subject_user_id=uuid4(),
        claimed_legacy_identity_ref="legacy-req-store",
    )
    service.submit_evidence(
        case_id=case.case_id,
        reviewer_id=uuid4(),
        operation_key="req-store-evidence",
        evidence_hash="evidence-hash-required00",
        evidence_type="ticket",
    )
    with pytest.raises(RecoveryError) as err:
        service.create_assertion(
            case_id=case.case_id,
            reviewer_id=uuid4(),
            operation_key="req-store-assert",
            decision="APPROVE",
            rationale="EVIDENCE_MATCH",
        )
    assert err.value.code == "assertion_store_required"


def test_happy_path_quorum_commits_through_store(harness):
    service = harness["service"]
    assertion_store = harness["assertion_store"]
    case, evidence = _ready_case(service)
    r1, r2 = uuid4(), uuid4()

    case, a1, replayed1 = service.create_assertion(
        case_id=case.case_id,
        reviewer_id=r1,
        operation_key="wf-assert-0001",
        decision="APPROVE",
        rationale="EVIDENCE_MATCH",
    )
    assert replayed1 is False
    assert case.state == RecoveryCaseState.AWAITING_SECOND_APPROVAL
    assert assertion_store.get(a1.assertion_id).signature

    case, _a2, _ = service.create_assertion(
        case_id=case.case_id,
        reviewer_id=r2,
        operation_key="wf-assert-0002",
        decision="APPROVE",
        rationale="SECOND_EYE_OK",
    )
    assert case.state == RecoveryCaseState.APPROVED
    assert assertion_store.has_approval_quorum(
        case_id=case.case_id, evidence_reference_hash=evidence
    )
    # No link creation in this package
    assert case.state != RecoveryCaseState.LINK_CREATED
    assert len(assertion_store.list_for_case(case.case_id)) == 2


def test_same_reviewer_cannot_fill_both_roles(harness):
    service = harness["service"]
    case, _evidence = _ready_case(service)
    reviewer = uuid4()
    service.create_assertion(
        case_id=case.case_id,
        reviewer_id=reviewer,
        operation_key="fe-assert-0001",
        decision="APPROVE",
        rationale="FIRST",
    )
    with pytest.raises(RecoveryError) as err:
        service.create_assertion(
            case_id=case.case_id,
            reviewer_id=reviewer,
            operation_key="fe-assert-0002",
            decision="APPROVE",
            rationale="SECOND_SAME_PERSON",
        )
    assert err.value.code == "four_eyes_conflict"
    case = service.get_case(case.case_id)
    assert case.state == RecoveryCaseState.AWAITING_SECOND_APPROVAL
    assert len(harness["assertion_store"].list_for_case(case.case_id)) == 1
    assert any(a.action == "four_eyes_conflict" for a in harness["audit"].records)


def test_revoke_drops_quorum_immediately(harness):
    service = harness["service"]
    assertion_store = harness["assertion_store"]
    case, evidence = _ready_case(service)
    r1, r2 = uuid4(), uuid4()
    case, primary, _ = service.create_assertion(
        case_id=case.case_id,
        reviewer_id=r1,
        operation_key="rev-assert-0001",
        decision="APPROVE",
        rationale="PRIMARY",
    )
    assert case.state == RecoveryCaseState.AWAITING_SECOND_APPROVAL

    case, _, _ = service.revoke_assertion(
        case_id=case.case_id,
        assertion_id=primary.assertion_id,
        reviewer_id=r1,
        operation_key="rev-op-0001",
    )
    assert case.state == RecoveryCaseState.READY_FOR_REVIEW
    assert (
        assertion_store.has_approval_quorum(
            case_id=case.case_id, evidence_reference_hash=evidence
        )
        is False
    )
    # Second approval against revoked primary context still needs a fresh valid quorum.
    case, _, _ = service.create_assertion(
        case_id=case.case_id,
        reviewer_id=r2,
        operation_key="rev-assert-0002",
        decision="APPROVE",
        rationale="AFTER_REVOKE",
    )
    assert case.state == RecoveryCaseState.AWAITING_SECOND_APPROVAL
    assert (
        assertion_store.has_approval_quorum(
            case_id=case.case_id, evidence_reference_hash=evidence
        )
        is False
    )


def test_expired_assertion_excluded_from_workflow_quorum(harness):
    service = harness["service"]
    assertion_store = harness["assertion_store"]
    case, evidence = _ready_case(service)
    r1, r2 = uuid4(), uuid4()
    service.create_assertion(
        case_id=case.case_id,
        reviewer_id=r1,
        operation_key="exp-assert-0001",
        decision="APPROVE",
        rationale="PRIMARY",
    )
    service.create_assertion(
        case_id=case.case_id,
        reviewer_id=r2,
        operation_key="exp-assert-0002",
        decision="APPROVE",
        rationale="SECOND",
    )
    case = service.get_case(case.case_id)
    assert case.state == RecoveryCaseState.APPROVED
    after_ttl = datetime.now(timezone.utc) + timedelta(hours=25)
    assert (
        assertion_store.has_approval_quorum(
            case_id=case.case_id,
            evidence_reference_hash=evidence,
            now=after_ttl,
        )
        is False
    )


def test_audit_failure_rolls_back_assertion_and_case(harness):
    service = harness["service"]
    audit = harness["audit"]
    assertion_store = harness["assertion_store"]
    case, _evidence = _ready_case(service)
    audit.fail = True
    with pytest.raises(RecoveryError) as err:
        service.create_assertion(
            case_id=case.case_id,
            reviewer_id=uuid4(),
            operation_key="audit-assert-0001",
            decision="APPROVE",
            rationale="SHOULD_ROLLBACK",
        )
    assert err.value.code == "audit_failed"
    refreshed = service.get_case(case.case_id)
    assert refreshed.state == RecoveryCaseState.READY_FOR_REVIEW
    assert assertion_store.list_for_case(case.case_id) == []
    assert harness["session"].scalar(select(V1RecoveryAssertion)) is None


def test_operation_key_resume_after_restart(harness):
    """Simulate process restart: new RecoveryService, same durable assertion rows."""
    service = harness["service"]
    case_store = harness["case_store"]
    SessionLocal = harness["SessionLocal"]
    case, evidence = _ready_case(service)
    reviewer = uuid4()
    case, assertion, _ = service.create_assertion(
        case_id=case.case_id,
        reviewer_id=reviewer,
        operation_key="resume-assert-0001",
        decision="APPROVE",
        rationale="PRIMARY",
    )
    assert case.state == RecoveryCaseState.AWAITING_SECOND_APPROVAL

    # New session + service (restart), same in-memory case ledger + durable assertions.
    session2 = SessionLocal()
    assertion_store2 = DurableSignedAssertionStore(session2, signing_secret=SIGNING_SECRET)
    service2 = RecoveryService(
        case_store,
        InMemoryAuditWriter(),
        assertion_store=assertion_store2,
        db_session=session2,
    )
    try:
        case2, assertion2, replayed = service2.create_assertion(
            case_id=case.case_id,
            reviewer_id=reviewer,
            operation_key="resume-assert-0001",
            decision="APPROVE",
            rationale="PRIMARY",
        )
        assert replayed is True
        assert assertion2.assertion_id == assertion.assertion_id
        assert case2.state == RecoveryCaseState.AWAITING_SECOND_APPROVAL
        assert len(assertion_store2.list_for_case(case.case_id)) == 1
        # Distinct second reviewer can still complete quorum after resume.
        case2, _, _ = service2.create_assertion(
            case_id=case.case_id,
            reviewer_id=uuid4(),
            operation_key="resume-assert-0002",
            decision="APPROVE",
            rationale="SECOND",
        )
        assert case2.state == RecoveryCaseState.APPROVED
        assert assertion_store2.has_approval_quorum(
            case_id=case.case_id, evidence_reference_hash=evidence
        )
    finally:
        session2.close()


def test_reject_commits_terminal_via_store(harness):
    service = harness["service"]
    case, _evidence = _ready_case(service)
    case, _, _ = service.create_assertion(
        case_id=case.case_id,
        reviewer_id=uuid4(),
        operation_key="reject-assert-0001",
        decision="REJECT",
        rationale="INSUFFICIENT_EVIDENCE",
    )
    assert case.state == RecoveryCaseState.REJECTED
    assert len(harness["assertion_store"].list_for_case(case.case_id)) == 1
    with pytest.raises(RecoveryError) as err:
        service.create_assertion(
            case_id=case.case_id,
            reviewer_id=uuid4(),
            operation_key="reject-assert-0002",
            decision="APPROVE",
            rationale="TOO_LATE",
        )
    assert err.value.code == "terminal_case_immutable"


def test_no_link_or_rollout_side_effects(harness):
    service = harness["service"]
    case, _ = _ready_case(service)
    service.create_assertion(
        case_id=case.case_id,
        reviewer_id=uuid4(),
        operation_key="nogoal-assert-0001",
        decision="APPROVE",
        rationale="PRIMARY",
    )
    service.create_assertion(
        case_id=case.case_id,
        reviewer_id=uuid4(),
        operation_key="nogoal-assert-0002",
        decision="APPROVE",
        rationale="SECOND",
    )
    case = service.get_case(case.case_id)
    assert case.state == RecoveryCaseState.APPROVED
    assert not hasattr(case, "link_id")
    assert case.state != RecoveryCaseState.LINK_CREATED

"""PMP-01A.3.6 Durable Recovery Case Ledger — negative + restart evidence."""

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.application.assertion_store import DurableSignedAssertionStore
from app.application.recovery_case_store import DurableRecoveryCaseStore
from app.application.recovery_link_store import DurableRecoveryLinkStore
from app.application.recovery_service import InMemoryAuditWriter, RecoveryService
from app.db import Base
from app.domain.recovery import RecoveryCaseState, RecoveryError
from app.models.recovery_assertion import V1RecoveryAssertion
from app.models.recovery_case import V1RecoveryCase, V1RecoveryCaseOperation
from app.models.recovery_link import V1RecoveryLink


SIGNING_SECRET = "test-a36-assertion-signing-secret"
MIGRATION = (
    Path(__file__).parents[1]
    / "migrations"
    / "versions"
    / "20260718_0006_recovery_cases.py"
)
SQL_COMPANION = (
    Path(__file__).parents[1]
    / "migrations"
    / "versions"
    / "20260718_0006_recovery_cases.sql"
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
        tables=[
            V1RecoveryCase.__table__,
            V1RecoveryCaseOperation.__table__,
            V1RecoveryAssertion.__table__,
            V1RecoveryLink.__table__,
        ],
    )
    SessionLocal = sessionmaker(bind=engine, future=True, autoflush=False, autocommit=False)
    session = SessionLocal()
    case_store = DurableRecoveryCaseStore(session)
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


def _rebuild_service(SessionLocal, *, audit: InMemoryAuditWriter | None = None):
    session = SessionLocal()
    case_store = DurableRecoveryCaseStore(session)
    audit = audit or InMemoryAuditWriter()
    assertion_store = DurableSignedAssertionStore(session, signing_secret=SIGNING_SECRET)
    link_store = DurableRecoveryLinkStore(session)
    service = RecoveryService(
        case_store,
        audit,
        assertion_store=assertion_store,
        link_store=link_store,
        db_session=session,
    )
    return service, session, case_store, assertion_store, link_store


def test_migration_defines_case_ledger_without_identity_or_rollout():
    text = MIGRATION.read_text(encoding="utf-8")
    sql = SQL_COMPANION.read_text(encoding="utf-8")
    for body in (text, sql):
        assert "v1_recovery_cases" in body
        assert "v1_recovery_case_operations" in body
        assert "state_version" in body
        assert "v1_recovery_cases_one_open_subject" in body
        assert "v1_recovery_cases_one_open_legacy" in body
        assert "v1_identity_links" not in body
        assert "rollout" not in body.casefold()
        assert "automatic" not in body.casefold()


def test_model_includes_durable_case_fields():
    required = {
        "case_id",
        "state",
        "subject_user_id",
        "claimed_legacy_identity_ref",
        "created_by",
        "evidence_hash",
        "evidence_type",
        "notes",
        "created_at",
        "updated_at",
        "expires_at",
        "state_version",
    }
    assert required.issubset(V1RecoveryCase.__table__.columns.keys())
    assert {"operation_key", "case_id"}.issubset(V1RecoveryCaseOperation.__table__.columns.keys())


def test_create_persists(harness):
    service = harness["service"]
    session = harness["session"]
    subject = uuid4()
    case, replayed = service.create_case(
        reviewer_id=uuid4(),
        operation_key="create-persist-0001",
        subject_user_id=subject,
        claimed_legacy_identity_ref="legacy-persist-1",
    )
    assert replayed is False
    assert case.state == RecoveryCaseState.EVIDENCE_PENDING
    row = session.get(V1RecoveryCase, case.case_id)
    assert row is not None
    assert row.state == "EVIDENCE_PENDING"
    assert row.subject_user_id == subject
    op = session.scalar(
        select(V1RecoveryCaseOperation).where(
            V1RecoveryCaseOperation.operation_key == "create-persist-0001"
        )
    )
    assert op is not None
    assert op.case_id == case.case_id


def test_state_persists_after_store_service_reconstruction(harness):
    service = harness["service"]
    SessionLocal = harness["SessionLocal"]
    case, _ = service.create_case(
        reviewer_id=uuid4(),
        operation_key="create-restart-0001",
        subject_user_id=uuid4(),
        claimed_legacy_identity_ref="legacy-restart-1",
    )
    service.submit_evidence(
        case_id=case.case_id,
        reviewer_id=uuid4(),
        operation_key="evidence-restart-0001",
        evidence_hash="evidence-hash-restart00001",
        evidence_type="ticket",
    )

    service2, session2, *_ = _rebuild_service(SessionLocal)
    try:
        refreshed = service2.get_case(case.case_id)
        assert refreshed.state == RecoveryCaseState.READY_FOR_REVIEW
        assert refreshed.evidence_hash == "evidence-hash-restart00001"
        assert refreshed.case_id == case.case_id
    finally:
        session2.close()


def test_one_open_case_per_identity(harness):
    service = harness["service"]
    subject = uuid4()
    legacy = "legacy-one-open"
    service.create_case(
        reviewer_id=uuid4(),
        operation_key="open-1",
        subject_user_id=subject,
        claimed_legacy_identity_ref=legacy,
    )
    with pytest.raises(RecoveryError) as err:
        service.create_case(
            reviewer_id=uuid4(),
            operation_key="open-2",
            subject_user_id=subject,
            claimed_legacy_identity_ref="legacy-other",
        )
    assert err.value.code == "duplicate_open_case"
    with pytest.raises(RecoveryError) as err2:
        service.create_case(
            reviewer_id=uuid4(),
            operation_key="open-3",
            subject_user_id=uuid4(),
            claimed_legacy_identity_ref=legacy,
        )
    assert err2.value.code == "duplicate_open_case"


def test_terminal_reopen_forbidden(harness):
    service = harness["service"]
    case, _ = service.create_case(
        reviewer_id=uuid4(),
        operation_key="term-create-0001",
        subject_user_id=uuid4(),
        claimed_legacy_identity_ref="legacy-term-1",
    )
    service.cancel_case(
        case_id=case.case_id,
        reviewer_id=uuid4(),
        operation_key="term-cancel-0001",
        reason="withdrawn",
    )
    with pytest.raises(RecoveryError) as err:
        service.submit_evidence(
            case_id=case.case_id,
            reviewer_id=uuid4(),
            operation_key="term-evidence-0001",
            evidence_hash="evidence-hash-terminal0001",
            evidence_type="ticket",
        )
    assert err.value.code == "terminal_case_immutable"
    # Direct store reopen attempt also fails closed.
    store = harness["case_store"]
    loaded = store.get(case.case_id)
    assert loaded is not None
    loaded.state = RecoveryCaseState.READY_FOR_REVIEW
    with pytest.raises(RecoveryError) as err2:
        store.save(loaded, expected_version=loaded.state_version)
    assert err2.value.code == "terminal_case_immutable"


def test_appeal_creates_new_case(harness):
    service = harness["service"]
    subject = uuid4()
    legacy = "legacy-appeal-1"
    first, _ = service.create_case(
        reviewer_id=uuid4(),
        operation_key="appeal-create-0001",
        subject_user_id=subject,
        claimed_legacy_identity_ref=legacy,
    )
    service.cancel_case(
        case_id=first.case_id,
        reviewer_id=uuid4(),
        operation_key="appeal-cancel-0001",
        reason="appeal-prep",
    )
    second, replayed = service.create_case(
        reviewer_id=uuid4(),
        operation_key="appeal-create-0002",
        subject_user_id=subject,
        claimed_legacy_identity_ref=legacy,
    )
    assert replayed is False
    assert second.case_id != first.case_id
    assert second.state == RecoveryCaseState.EVIDENCE_PENDING


def test_operation_key_restart_safe_replay(harness):
    service = harness["service"]
    SessionLocal = harness["SessionLocal"]
    case, _ = service.create_case(
        reviewer_id=uuid4(),
        operation_key="op-restart-create-0001",
        subject_user_id=uuid4(),
        claimed_legacy_identity_ref="legacy-op-restart",
    )

    service2, session2, *_ = _rebuild_service(SessionLocal)
    try:
        replayed_case, replayed = service2.create_case(
            reviewer_id=uuid4(),
            operation_key="op-restart-create-0001",
            subject_user_id=uuid4(),
            claimed_legacy_identity_ref="legacy-op-restart-other",
        )
        assert replayed is True
        assert replayed_case.case_id == case.case_id
        assert session2.scalar(select(V1RecoveryCase)).case_id == case.case_id
        count = len(session2.scalars(select(V1RecoveryCase)).all())
        assert count == 1
    finally:
        session2.close()


def test_concurrent_mutation_conflict(harness):
    from sqlalchemy import update

    service = harness["service"]
    session = harness["session"]
    store = harness["case_store"]
    case, _ = service.create_case(
        reviewer_id=uuid4(),
        operation_key="conc-create-0001",
        subject_user_id=uuid4(),
        claimed_legacy_identity_ref="legacy-conc-1",
    )
    loaded = store.get(case.case_id)
    assert loaded is not None
    assert loaded.state_version == 0

    # Simulate a concurrent winner committing a state_version bump.
    session.execute(
        update(V1RecoveryCase)
        .where(V1RecoveryCase.case_id == case.case_id)
        .values(
            state="READY_FOR_REVIEW",
            evidence_hash="hash-winner",
            state_version=1,
        )
    )
    session.commit()

    loaded.state = RecoveryCaseState.READY_FOR_REVIEW
    loaded.evidence_hash = "hash-loser"
    with pytest.raises(RecoveryError) as err:
        store.save(loaded, expected_version=0)
    assert err.value.code == "conflict_state"
    session.rollback()

    winner = store.get(case.case_id)
    assert winner is not None
    assert winner.evidence_hash == "hash-winner"
    assert winner.state_version == 1


def test_audit_failure_rollback(harness):
    service = harness["service"]
    session = harness["session"]
    audit = harness["audit"]
    audit.fail = True
    with pytest.raises(RecoveryError) as err:
        service.create_case(
            reviewer_id=uuid4(),
            operation_key="audit-fail-case-0001",
            subject_user_id=uuid4(),
            claimed_legacy_identity_ref="legacy-audit-fail",
        )
    assert err.value.code == "audit_failed"
    assert session.scalar(select(V1RecoveryCase)) is None
    assert session.scalar(select(V1RecoveryCaseOperation)) is None


def test_assertion_link_association_survives_restart(harness):
    service = harness["service"]
    SessionLocal = harness["SessionLocal"]
    opener = uuid4()
    case, _ = service.create_case(
        reviewer_id=opener,
        operation_key="assoc-create-0001",
        subject_user_id=uuid4(),
        claimed_legacy_identity_ref="legacy-assoc-1",
    )
    evidence = "evidence-hash-assoc00000001"
    service.submit_evidence(
        case_id=case.case_id,
        reviewer_id=opener,
        operation_key="assoc-evidence-0001",
        evidence_hash=evidence,
        evidence_type="ticket",
    )
    r1, r2 = uuid4(), uuid4()
    service.create_assertion(
        case_id=case.case_id,
        reviewer_id=r1,
        operation_key="assoc-assert-0001",
        decision="APPROVE",
        rationale="PRIMARY",
    )
    service.create_assertion(
        case_id=case.case_id,
        reviewer_id=r2,
        operation_key="assoc-assert-0002",
        decision="APPROVE",
        rationale="SECOND",
    )
    case, link, raw_token, _ = service.create_recovery_link(
        case_id=case.case_id,
        reviewer_id=r1,
        operation_key="assoc-link-0001",
    )
    assert case.state == RecoveryCaseState.LINK_CREATED
    assert raw_token is not None
    link_id = link.link_id

    service2, session2, _cs, assertion_store2, link_store2 = _rebuild_service(SessionLocal)
    try:
        refreshed = service2.get_case(case.case_id)
        assert refreshed.state == RecoveryCaseState.LINK_CREATED
        asserts = assertion_store2.list_for_case(case.case_id)
        assert len(asserts) == 2
        assert all(a.case_id == case.case_id for a in asserts)
        revived = link_store2.get(link_id)
        assert revived.case_id == case.case_id
        assert link_store2.get_active_for_case(case.case_id) is not None
        # No silent reconstruction: unknown case_id fails closed.
        with pytest.raises(RecoveryError) as err:
            service2.get_case(uuid4())
        assert err.value.code == "case_not_found"
        assert session2.get(V1RecoveryCase, case.case_id) is not None
    finally:
        session2.close()


def test_existing_a3_suites_remain_importable():
    """Smoke import guard for A.3.1–A.3.5 evidence modules."""
    import tests.test_pmp01a31_reviewer_api as a31
    import tests.test_pmp01a32_assertion_store as a32
    import tests.test_pmp01a33_four_eyes_workflow as a33
    import tests.test_pmp01a34_recovery_link_lifecycle as a34
    import tests.test_pmp01a35_recovery_ui_thin_client as a35

    assert a31 and a32 and a33 and a34 and a35

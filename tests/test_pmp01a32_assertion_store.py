"""PMP-01A.3.2 Durable Signed Assertion Store — negative evidence package."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.application.assertion_signing import (
    canonical_assertion_payload,
    sign_canonical_payload,
    verify_assertion_signature,
)
from app.application.assertion_store import DurableSignedAssertionStore
from app.db import Base
from app.domain.assertion import POLICY_VERSION, ReviewerRole, SignedAssertion
from app.domain.recovery import RecoveryError
from app.models.recovery_assertion import V1RecoveryAssertion


SIGNING_SECRET = "test-recovery-assertion-signing-secret"
MIGRATION = (
    Path(__file__).parents[1]
    / "migrations"
    / "versions"
    / "20260718_0004_recovery_assertions.py"
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine, tables=[V1RecoveryAssertion.__table__])
    SessionLocal = sessionmaker(bind=engine, future=True, autoflush=False, autocommit=False)
    session = SessionLocal()
    try:
        yield session
        session.commit()
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def store(db_session: Session):
    return DurableSignedAssertionStore(db_session, signing_secret=SIGNING_SECRET)


def _create(store: DurableSignedAssertionStore, **overrides):
    params = {
        "case_id": uuid4(),
        "operation_key": f"op-{uuid4().hex[:16]}",
        "evidence_reference_hash": "evidence-hash-aaaaaaaa",
        "asserted_supabase_user_id": uuid4(),
        "asserted_legacy_user_id": "legacy-42",
        "reviewer_id": uuid4(),
        "decision": "approve",
        "rationale_code": "EVIDENCE_MATCH",
    }
    params.update(overrides)
    return store.create(**params)


def test_migration_defines_assertion_store_without_link_or_rollout():
    text = MIGRATION.read_text(encoding="utf-8")
    assert "v1_recovery_assertions" in text
    assert "signature" in text
    assert "revoked_at" in text
    assert "policy_version" in text
    assert "v1_identity_links" not in text
    assert "rollout" not in text.casefold()
    assert "automatic" not in text.casefold()


def test_model_includes_locked_assertion_schema_fields():
    required = {
        "assertion_id",
        "case_id",
        "operation_key",
        "policy_version",
        "evidence_reference_hash",
        "asserted_supabase_user_id",
        "asserted_legacy_user_id",
        "reviewer_id",
        "reviewer_role",
        "decision",
        "rationale_code",
        "created_at",
        "expires_at",
        "signature",
        "revoked_at",
    }
    assert required.issubset(V1RecoveryAssertion.__table__.columns.keys())


def test_client_supplied_signature_forbidden(store):
    with pytest.raises(RecoveryError) as err:
        _create(store, client_signature="deadbeef")
    assert err.value.code == "client_assertion_forbidden"
    assert store.session.scalar(select(V1RecoveryAssertion)) is None


def test_client_supplied_reviewer_authority_forbidden(store):
    with pytest.raises(RecoveryError) as err:
        _create(store, client_reviewer_id=uuid4())
    assert err.value.code == "client_assertion_forbidden"

    with pytest.raises(RecoveryError) as err2:
        _create(store, client_reviewer_role="primary_reviewer")
    assert err2.value.code == "client_assertion_forbidden"


def test_server_signs_and_verifies_persisted_assertion(store, db_session):
    assertion, replayed = _create(store)
    db_session.commit()
    assert replayed is False
    assert assertion.signature
    assert assertion.policy_version == POLICY_VERSION
    assert assertion.reviewer_role == ReviewerRole.PRIMARY
    assert store.verify(assertion) is True

    # Durability: new store session sees the same signed row
    reloaded = DurableSignedAssertionStore(db_session, signing_secret=SIGNING_SECRET)
    persisted = reloaded.get(assertion.assertion_id)
    assert persisted.signature == assertion.signature
    assert reloaded.verify(persisted) is True


def test_tampered_assertion_fails_verification(store):
    assertion, _ = _create(store)
    tampered = SignedAssertion(
        assertion_id=assertion.assertion_id,
        case_id=assertion.case_id,
        operation_key=assertion.operation_key,
        policy_version=assertion.policy_version,
        evidence_reference_hash="tampered-hash-bbbbbbbb",
        asserted_supabase_user_id=assertion.asserted_supabase_user_id,
        asserted_legacy_user_id=assertion.asserted_legacy_user_id,
        reviewer_id=assertion.reviewer_id,
        reviewer_role=assertion.reviewer_role,
        decision=assertion.decision,
        rationale_code=assertion.rationale_code,
        created_at=assertion.created_at,
        expires_at=assertion.expires_at,
        signature=assertion.signature,
        revoked_at=None,
        schema_version=assertion.schema_version,
    )
    assert verify_assertion_signature(tampered, SIGNING_SECRET) is False
    assert store.verify(tampered) is False


def test_operation_key_idempotent_replay(store):
    case_id = uuid4()
    key = "assert-op-idempotent-01"
    first, replayed1 = _create(store, case_id=case_id, operation_key=key)
    second, replayed2 = _create(store, case_id=case_id, operation_key=key)
    assert replayed1 is False
    assert replayed2 is True
    assert first.assertion_id == second.assertion_id
    rows = store.session.scalars(select(V1RecoveryAssertion)).all()
    assert len(rows) == 1


def test_four_eyes_conflict_same_reviewer(store):
    case_id = uuid4()
    reviewer = uuid4()
    evidence = "evidence-hash-cccccccc"
    _create(
        store,
        case_id=case_id,
        reviewer_id=reviewer,
        evidence_reference_hash=evidence,
        operation_key="fe-1",
    )
    with pytest.raises(RecoveryError) as err:
        _create(
            store,
            case_id=case_id,
            reviewer_id=reviewer,
            evidence_reference_hash=evidence,
            operation_key="fe-2",
        )
    assert err.value.code == "four_eyes_conflict"
    assert len(store.list_for_case(case_id)) == 1


def test_expired_assertion_excluded_from_quorum(store):
    case_id = uuid4()
    evidence = "evidence-hash-dddddddd"
    a1, _ = _create(
        store,
        case_id=case_id,
        evidence_reference_hash=evidence,
        reviewer_id=uuid4(),
        operation_key="exp-1",
    )
    a2, _ = _create(
        store,
        case_id=case_id,
        evidence_reference_hash=evidence,
        reviewer_id=uuid4(),
        operation_key="exp-2",
    )
    assert store.has_approval_quorum(case_id=case_id, evidence_reference_hash=evidence)

    # Simulate wall-clock passage via evaluation time (does not rewrite signed rows).
    after_ttl = datetime.now(timezone.utc) + timedelta(hours=25)
    assert store.verify(a1) is True
    assert a1.is_valid_for_quorum(after_ttl) is False
    assert a2.is_valid_for_quorum(after_ttl) is False
    assert (
        store.has_approval_quorum(
            case_id=case_id, evidence_reference_hash=evidence, now=after_ttl
        )
        is False
    )


def test_revoked_assertion_excluded_and_append_only(store):
    case_id = uuid4()
    evidence = "evidence-hash-eeeeeeee"
    primary, _ = _create(
        store,
        case_id=case_id,
        evidence_reference_hash=evidence,
        reviewer_id=uuid4(),
        operation_key="rev-1",
    )
    _create(
        store,
        case_id=case_id,
        evidence_reference_hash=evidence,
        reviewer_id=uuid4(),
        operation_key="rev-2",
    )
    assert store.has_approval_quorum(case_id=case_id, evidence_reference_hash=evidence)

    revoked = store.revoke(primary.assertion_id)
    assert revoked.revoked_at is not None
    assert store.has_approval_quorum(case_id=case_id, evidence_reference_hash=evidence) is False
    assert store.session.get(V1RecoveryAssertion, primary.assertion_id) is not None

    with pytest.raises(RecoveryError) as err:
        store.delete(primary.assertion_id)
    assert err.value.code == "assertion_immutable"


def test_policy_version_immutable(store):
    assertion, _ = _create(store)
    with pytest.raises(RecoveryError) as err:
        store.mutate_policy_version(assertion.assertion_id, "other-policy")
    assert err.value.code == "assertion_immutable"
    assert store.get(assertion.assertion_id).policy_version == POLICY_VERSION


def test_foreign_policy_version_rejected_on_create(store):
    with pytest.raises(RecoveryError) as err:
        _create(store, policy_version="attacker-policy")
    assert err.value.code == "policy_version_mismatch"


def test_missing_signing_secret_fails_closed(db_session):
    store = DurableSignedAssertionStore(db_session, signing_secret="")
    with pytest.raises(RecoveryError) as err:
        _create(store)
    assert err.value.code == "signing_not_configured"
    assert db_session.scalar(select(V1RecoveryAssertion)) is None


def test_reject_decision_does_not_count_for_quorum(store):
    case_id = uuid4()
    evidence = "evidence-hash-ffffffff"
    _create(
        store,
        case_id=case_id,
        evidence_reference_hash=evidence,
        reviewer_id=uuid4(),
        decision="reject",
        rationale_code="INSUFFICIENT_EVIDENCE",
        operation_key="rej-1",
    )
    _create(
        store,
        case_id=case_id,
        evidence_reference_hash=evidence,
        reviewer_id=uuid4(),
        decision="approve",
        operation_key="rej-2",
    )
    assert store.has_approval_quorum(case_id=case_id, evidence_reference_hash=evidence) is False


def test_evidence_hash_mismatch_excluded_from_quorum(store):
    case_id = uuid4()
    _create(
        store,
        case_id=case_id,
        evidence_reference_hash="hash-one-1111111111",
        reviewer_id=uuid4(),
        operation_key="ev-1",
    )
    _create(
        store,
        case_id=case_id,
        evidence_reference_hash="hash-two-2222222222",
        reviewer_id=uuid4(),
        operation_key="ev-2",
    )
    assert (
        store.has_approval_quorum(
            case_id=case_id, evidence_reference_hash="hash-one-1111111111"
        )
        is False
    )


def test_forged_client_signature_cannot_be_persisted_via_canonical_helper():
    # Even if an attacker builds a canonical payload and HMAC with a guessed key,
    # store.create never accepts that signature as authority input.
    forged = sign_canonical_payload(
        canonical_assertion_payload(
            assertion_id=uuid4(),
            case_id=uuid4(),
            operation_key="forged-op-0001",
            policy_version=POLICY_VERSION,
            evidence_reference_hash="x" * 20,
            asserted_supabase_user_id=uuid4(),
            asserted_legacy_user_id="legacy",
            reviewer_id=uuid4(),
            reviewer_role="primary_reviewer",
            decision="approve",
            rationale_code="FORGED",
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            schema_version="1",
        ),
        "attacker-secret",
    )
    assert isinstance(forged, str) and len(forged) == 64

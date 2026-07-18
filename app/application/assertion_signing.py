"""Server-only assertion signing. Clients never supply trusted signatures."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from uuid import UUID

from app.domain.assertion import SignedAssertion
from app.domain.recovery import RecoveryError


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    """Stable UTC timestamp for signatures (naive SQLite values must match)."""
    dt = as_utc(value)
    return f"{dt.strftime('%Y-%m-%dT%H:%M:%S')}.{dt.microsecond:06d}Z"


def canonical_assertion_payload(
    *,
    assertion_id: UUID,
    case_id: UUID,
    operation_key: str,
    policy_version: str,
    evidence_reference_hash: str,
    asserted_supabase_user_id: UUID,
    asserted_legacy_user_id: str,
    reviewer_id: UUID,
    reviewer_role: str,
    decision: str,
    rationale_code: str,
    created_at: datetime,
    expires_at: datetime,
    schema_version: str,
) -> str:
    payload = {
        "assertion_id": str(assertion_id),
        "case_id": str(case_id),
        "operation_key": operation_key,
        "policy_version": policy_version,
        "evidence_reference_hash": evidence_reference_hash,
        "asserted_supabase_user_id": str(asserted_supabase_user_id),
        "asserted_legacy_user_id": asserted_legacy_user_id,
        "reviewer_id": str(reviewer_id),
        "reviewer_role": reviewer_role,
        "decision": decision,
        "rationale_code": rationale_code,
        "created_at": _iso(created_at),
        "expires_at": _iso(expires_at),
        "schema_version": schema_version,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def sign_canonical_payload(canonical: str, signing_secret: str) -> str:
    if not signing_secret:
        raise RecoveryError(
            "signing_not_configured",
            "Recovery assertion signing secret is not configured",
        )
    digest = hmac.new(
        signing_secret.encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return digest


def verify_assertion_signature(assertion: SignedAssertion, signing_secret: str) -> bool:
    if not signing_secret or not assertion.signature:
        return False
    canonical = canonical_assertion_payload(
        assertion_id=assertion.assertion_id,
        case_id=assertion.case_id,
        operation_key=assertion.operation_key,
        policy_version=assertion.policy_version,
        evidence_reference_hash=assertion.evidence_reference_hash,
        asserted_supabase_user_id=assertion.asserted_supabase_user_id,
        asserted_legacy_user_id=assertion.asserted_legacy_user_id,
        reviewer_id=assertion.reviewer_id,
        reviewer_role=str(assertion.reviewer_role),
        decision=str(assertion.decision),
        rationale_code=assertion.rationale_code,
        created_at=assertion.created_at,
        expires_at=assertion.expires_at,
        schema_version=assertion.schema_version,
    )
    expected = sign_canonical_payload(canonical, signing_secret)
    return hmac.compare_digest(expected, assertion.signature)

"""PMP-01A.3 Reviewer API + thin Recovery UI HTTP surface.

Security contracts remain in Recovery Service. This module only transports
reviewer JWT-bound requests and returns server decisions.
"""

from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.application.assertion_store import DurableSignedAssertionStore
from app.application.recovery_case_store import DurableRecoveryCaseStore
from app.application.recovery_link_store import DurableRecoveryLinkStore
from app.application.recovery_service import (
    RecoveryCaseRecord,
    RecoveryService,
    default_recovery_service,
)
from app.core.config import Settings, get_settings
from app.core.security import get_current_recovery_reviewer
from app.db import get_db
from app.domain.recovery import RecoveryError
from app.domain.recovery_link import RecoveryLink
from app.schemas.recovery import (
    CancelRecoveryCaseRequest,
    CreateAssertionRequest,
    CreateRecoveryCaseRequest,
    CreateRecoveryLinkRequest,
    CreateRecoveryLinkResponse,
    MutationResponse,
    RecoveryCaseResponse,
    RecoveryLinkResponse,
    RevokeRecoveryLinkRequest,
    RevokeRecoveryLinkResponse,
    SubmitEvidenceRequest,
)


router = APIRouter(prefix="/v1/recovery", tags=["v1-recovery-reviewer"])

# Audit remains process-local for reviewer console evidence; case ledger is durable (A.3.6).
_audit = default_recovery_service.audit


def get_recovery_service(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RecoveryService:
    case_store = DurableRecoveryCaseStore(db)
    assertion_store = DurableSignedAssertionStore(
        db,
        signing_secret=settings.recovery_assertion_signing_secret,
    )
    link_store = DurableRecoveryLinkStore(db)
    return RecoveryService(
        case_store,
        _audit,
        assertion_store=assertion_store,
        link_store=link_store,
        db_session=db,
    )


def _to_case_response(case: RecoveryCaseRecord) -> RecoveryCaseResponse:
    active = [a for a in case.assertions if a.revoked_at is None]
    approve_count = sum(1 for a in active if a.decision == "APPROVE")
    reject_count = sum(1 for a in active if a.decision == "REJECT")
    return RecoveryCaseResponse(
        case_id=case.case_id,
        state=str(case.state),
        subject_user_id=case.subject_user_id,
        claimed_legacy_identity_ref=case.claimed_legacy_identity_ref,
        evidence_hash=case.evidence_hash,
        assertion_count=len(active),
        approve_count=approve_count,
        reject_count=reject_count,
        created_at=case.created_at,
        updated_at=case.updated_at,
        expires_at=case.expires_at,
    )


def _to_link_response(link: RecoveryLink) -> RecoveryLinkResponse:
    return RecoveryLinkResponse(
        link_id=link.link_id,
        case_id=link.case_id,
        created_at=link.created_at,
        expires_at=link.expires_at,
        revoked_at=link.revoked_at,
        revoked_by=link.revoked_by,
        used_at=link.used_at,
    )


def _http_error(exc: RecoveryError) -> HTTPException:
    code_map = {
        "case_not_found": status.HTTP_404_NOT_FOUND,
        "terminal_case_immutable": status.HTTP_409_CONFLICT,
        "illegal_transition": status.HTTP_409_CONFLICT,
        "four_eyes_conflict": status.HTTP_409_CONFLICT,
        "duplicate_open_case": status.HTTP_409_CONFLICT,
        "conflict_state": status.HTTP_409_CONFLICT,
        "audit_failed": status.HTTP_503_SERVICE_UNAVAILABLE,
        "client_assertion_forbidden": status.HTTP_403_FORBIDDEN,
        "assertion_store_required": status.HTTP_503_SERVICE_UNAVAILABLE,
        "link_store_required": status.HTTP_503_SERVICE_UNAVAILABLE,
        "signing_not_configured": status.HTTP_503_SERVICE_UNAVAILABLE,
        "evidence_required": status.HTTP_409_CONFLICT,
        "operation_key_conflict": status.HTTP_409_CONFLICT,
        "assertion_not_found": status.HTTP_404_NOT_FOUND,
        "assertion_expired": status.HTTP_409_CONFLICT,
        "active_link_exists": status.HTTP_409_CONFLICT,
        "link_not_found": status.HTTP_404_NOT_FOUND,
        "revoke_reason_required": status.HTTP_400_BAD_REQUEST,
        "link_immutable": status.HTTP_409_CONFLICT,
        "link_not_active": status.HTTP_409_CONFLICT,
        "link_expired": status.HTTP_409_CONFLICT,
    }
    return HTTPException(
        status_code=code_map.get(exc.code, status.HTTP_400_BAD_REQUEST),
        detail={"code": exc.code, "message": exc.message},
    )


@router.post("/cases", response_model=MutationResponse, status_code=status.HTTP_201_CREATED)
def create_recovery_case(
    body: CreateRecoveryCaseRequest,
    reviewer_id: Annotated[UUID, Depends(get_current_recovery_reviewer)],
    service: Annotated[RecoveryService, Depends(get_recovery_service)],
):
    try:
        case, replayed = service.create_case(
            reviewer_id=reviewer_id,
            operation_key=body.operation_key,
            subject_user_id=body.subject_user_id,
            claimed_legacy_identity_ref=body.claimed_legacy_identity_ref,
            notes=body.notes,
        )
    except RecoveryError as exc:
        raise _http_error(exc) from exc
    return MutationResponse(case=_to_case_response(case), replayed=replayed)


@router.get("/cases/{case_id}", response_model=RecoveryCaseResponse)
def get_recovery_case(
    case_id: UUID,
    _: Annotated[UUID, Depends(get_current_recovery_reviewer)],
    service: Annotated[RecoveryService, Depends(get_recovery_service)],
):
    """Read-only case status for thin Recovery UI."""
    try:
        case = service.get_case(case_id)
    except RecoveryError as exc:
        raise _http_error(exc) from exc
    return _to_case_response(case)


@router.post("/cases/{case_id}/evidence", response_model=MutationResponse)
def submit_evidence(
    case_id: UUID,
    body: SubmitEvidenceRequest,
    reviewer_id: Annotated[UUID, Depends(get_current_recovery_reviewer)],
    service: Annotated[RecoveryService, Depends(get_recovery_service)],
):
    try:
        case, replayed = service.submit_evidence(
            case_id=case_id,
            reviewer_id=reviewer_id,
            operation_key=body.operation_key,
            evidence_hash=body.evidence_hash,
            evidence_type=body.evidence_type,
        )
    except RecoveryError as exc:
        raise _http_error(exc) from exc
    return MutationResponse(case=_to_case_response(case), replayed=replayed)


@router.post("/cases/{case_id}/assertions", response_model=MutationResponse)
def create_assertion(
    case_id: UUID,
    body: CreateAssertionRequest,
    reviewer_id: Annotated[UUID, Depends(get_current_recovery_reviewer)],
    service: Annotated[RecoveryService, Depends(get_recovery_service)],
):
    try:
        case, _assertion, replayed = service.create_assertion(
            case_id=case_id,
            reviewer_id=reviewer_id,
            operation_key=body.operation_key,
            decision=body.decision,
            rationale=body.rationale,
        )
    except RecoveryError as exc:
        raise _http_error(exc) from exc
    return MutationResponse(case=_to_case_response(case), replayed=replayed)


@router.post("/cases/{case_id}/cancel", response_model=MutationResponse)
def cancel_recovery_case(
    case_id: UUID,
    body: CancelRecoveryCaseRequest,
    reviewer_id: Annotated[UUID, Depends(get_current_recovery_reviewer)],
    service: Annotated[RecoveryService, Depends(get_recovery_service)],
):
    try:
        case, replayed = service.cancel_case(
            case_id=case_id,
            reviewer_id=reviewer_id,
            operation_key=body.operation_key,
            reason=body.reason,
        )
    except RecoveryError as exc:
        raise _http_error(exc) from exc
    return MutationResponse(case=_to_case_response(case), replayed=replayed)


@router.post(
    "/link/create",
    response_model=CreateRecoveryLinkResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_recovery_link(
    body: CreateRecoveryLinkRequest,
    reviewer_id: Annotated[UUID, Depends(get_current_recovery_reviewer)],
    service: Annotated[RecoveryService, Depends(get_recovery_service)],
):
    """Thin UI entry: server enforces quorum, hashing, and one-time token return."""
    try:
        case, link, raw_token, replayed = service.create_recovery_link(
            case_id=body.case_id,
            reviewer_id=reviewer_id,
            operation_key=body.operation_key,
        )
    except RecoveryError as exc:
        raise _http_error(exc) from exc
    return CreateRecoveryLinkResponse(
        case=_to_case_response(case),
        link=_to_link_response(link),
        raw_token=raw_token,
        replayed=replayed,
    )


@router.post("/link/revoke", response_model=RevokeRecoveryLinkResponse)
def revoke_recovery_link(
    body: RevokeRecoveryLinkRequest,
    reviewer_id: Annotated[UUID, Depends(get_current_recovery_reviewer)],
    service: Annotated[RecoveryService, Depends(get_recovery_service)],
):
    """Thin UI entry: server enforces reason, idempotency, and revoke metadata."""
    try:
        case, link, replayed = service.revoke_recovery_link(
            case_id=body.case_id,
            reviewer_id=reviewer_id,
            operation_key=body.operation_key,
            reason=body.reason,
            link_id=body.link_id,
        )
    except RecoveryError as exc:
        raise _http_error(exc) from exc
    return RevokeRecoveryLinkResponse(
        case=_to_case_response(case),
        link=_to_link_response(link),
        replayed=replayed,
    )


@router.get("/console", include_in_schema=False)
def recovery_reviewer_console():
    """Minimal static reviewer console. No policy in the page."""
    path = Path(__file__).resolve().parents[2] / "static" / "recovery-reviewer.html"
    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail={"code": "console_missing", "message": "Recovery console not found"},
        )
    return FileResponse(path, media_type="text/html; charset=utf-8")

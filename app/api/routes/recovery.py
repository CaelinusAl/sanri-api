"""PMP-01A.3 Reviewer API — four-eyes via durable signed assertion store."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.application.assertion_store import DurableSignedAssertionStore
from app.application.recovery_service import (
    RecoveryCaseRecord,
    RecoveryService,
    default_recovery_service,
)
from app.core.config import Settings, get_settings
from app.core.security import get_current_recovery_reviewer
from app.db import get_db
from app.domain.recovery import RecoveryError
from app.schemas.recovery import (
    CancelRecoveryCaseRequest,
    CreateAssertionRequest,
    CreateRecoveryCaseRequest,
    MutationResponse,
    RecoveryCaseResponse,
    SubmitEvidenceRequest,
)


router = APIRouter(prefix="/v1/recovery", tags=["v1-recovery-reviewer"])

# Process-local case ledger; assertions are durable in DB (A.3.2/A.3.3).
_case_store = default_recovery_service.store
_audit = default_recovery_service.audit


def get_recovery_service(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RecoveryService:
    assertion_store = DurableSignedAssertionStore(
        db,
        signing_secret=settings.recovery_assertion_signing_secret,
    )
    return RecoveryService(
        _case_store,
        _audit,
        assertion_store=assertion_store,
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


def _http_error(exc: RecoveryError) -> HTTPException:
    code_map = {
        "case_not_found": status.HTTP_404_NOT_FOUND,
        "terminal_case_immutable": status.HTTP_409_CONFLICT,
        "illegal_transition": status.HTTP_409_CONFLICT,
        "four_eyes_conflict": status.HTTP_409_CONFLICT,
        "duplicate_open_case": status.HTTP_409_CONFLICT,
        "audit_failed": status.HTTP_503_SERVICE_UNAVAILABLE,
        "client_assertion_forbidden": status.HTTP_403_FORBIDDEN,
        "assertion_store_required": status.HTTP_503_SERVICE_UNAVAILABLE,
        "signing_not_configured": status.HTTP_503_SERVICE_UNAVAILABLE,
        "evidence_required": status.HTTP_409_CONFLICT,
        "operation_key_conflict": status.HTTP_409_CONFLICT,
        "assertion_not_found": status.HTTP_404_NOT_FOUND,
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

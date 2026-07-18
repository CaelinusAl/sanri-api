"""Manual recovery case state machine (PMP-01A.3 contract)."""

from enum import StrEnum


class RecoveryCaseState(StrEnum):
    DRAFT = "DRAFT"
    EVIDENCE_PENDING = "EVIDENCE_PENDING"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    AWAITING_SECOND_APPROVAL = "AWAITING_SECOND_APPROVAL"
    APPROVED = "APPROVED"
    LINK_CREATED = "LINK_CREATED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    CLOSED = "CLOSED"


TERMINAL_STATES = frozenset(
    {
        RecoveryCaseState.REJECTED,
        RecoveryCaseState.CANCELLED,
        RecoveryCaseState.EXPIRED,
        RecoveryCaseState.REVOKED,
        RecoveryCaseState.CLOSED,
    }
)

ALLOWED_TRANSITIONS: dict[RecoveryCaseState, frozenset[RecoveryCaseState]] = {
    RecoveryCaseState.DRAFT: frozenset(
        {RecoveryCaseState.EVIDENCE_PENDING, RecoveryCaseState.CANCELLED}
    ),
    RecoveryCaseState.EVIDENCE_PENDING: frozenset(
        {
            RecoveryCaseState.READY_FOR_REVIEW,
            RecoveryCaseState.REJECTED,
            RecoveryCaseState.CANCELLED,
            RecoveryCaseState.EXPIRED,
        }
    ),
    RecoveryCaseState.READY_FOR_REVIEW: frozenset(
        {
            RecoveryCaseState.AWAITING_SECOND_APPROVAL,
            RecoveryCaseState.REJECTED,
            RecoveryCaseState.CANCELLED,
            RecoveryCaseState.EXPIRED,
            RecoveryCaseState.EVIDENCE_PENDING,
        }
    ),
    RecoveryCaseState.AWAITING_SECOND_APPROVAL: frozenset(
        {
            RecoveryCaseState.APPROVED,
            RecoveryCaseState.REJECTED,
            RecoveryCaseState.EXPIRED,
            RecoveryCaseState.CANCELLED,
            RecoveryCaseState.READY_FOR_REVIEW,
            RecoveryCaseState.EVIDENCE_PENDING,
        }
    ),
    RecoveryCaseState.APPROVED: frozenset(
        {
            RecoveryCaseState.LINK_CREATED,
            RecoveryCaseState.EXPIRED,
            RecoveryCaseState.CANCELLED,
            RecoveryCaseState.REJECTED,
        }
    ),
    RecoveryCaseState.LINK_CREATED: frozenset(
        {RecoveryCaseState.REVOKED, RecoveryCaseState.CLOSED}
    ),
}


class RecoveryError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def assert_transition_allowed(current: RecoveryCaseState, target: RecoveryCaseState) -> None:
    if current in TERMINAL_STATES:
        raise RecoveryError("terminal_case_immutable", "Terminal recovery cases cannot be mutated")
    allowed = ALLOWED_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise RecoveryError(
            "illegal_transition",
            f"Transition from {current} to {target} is not allowed",
        )

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CreateRecoveryCaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_key: str = Field(min_length=8, max_length=128)
    subject_user_id: UUID
    claimed_legacy_identity_ref: str = Field(min_length=1, max_length=256)
    notes: str | None = Field(default=None, max_length=2000)


class SubmitEvidenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_key: str = Field(min_length=8, max_length=128)
    evidence_hash: str = Field(min_length=16, max_length=128)
    evidence_type: str = Field(min_length=1, max_length=64)


class CreateAssertionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_key: str = Field(min_length=8, max_length=128)
    decision: Literal["APPROVE", "REJECT"]
    rationale: str = Field(min_length=1, max_length=2000)
    # Explicitly rejected if present via extra=forbid — clients must not send reviewer_id


class CancelRecoveryCaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_key: str = Field(min_length=8, max_length=128)
    reason: str = Field(min_length=1, max_length=2000)


class RecoveryCaseResponse(BaseModel):
    case_id: UUID
    state: str
    subject_user_id: UUID
    claimed_legacy_identity_ref: str
    evidence_hash: str | None
    assertion_count: int
    approve_count: int
    reject_count: int
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None


class AssertionResponse(BaseModel):
    assertion_id: UUID
    case_id: UUID
    decision: str
    reviewer_id: UUID
    created_at: datetime


class MutationResponse(BaseModel):
    case: RecoveryCaseResponse
    replayed: bool = False

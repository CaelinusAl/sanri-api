from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


Mode = Literal["aura", "reflection", "think", "create", "projects", "explore"]
Intent = Literal["build", "reflect", "heal", "learn", "create"]
WorkMode = Literal["deep_work", "reflection", "brainstorming"]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20000)
    conversation_id: UUID | None = None
    mode: Mode = "aura"
    intent: Intent = "build"
    work_mode: WorkMode = "deep_work"
    session_goal: str | None = Field(default=None, max_length=500)
    memory_consent: bool = False
    language: Literal["tr", "en"] = "tr"


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    mode: Mode = "aura"
    intent: Intent = "build"
    work_mode: WorkMode = "deep_work"
    session_goal: str | None = Field(default=None, max_length=500)


class ConversationSummary(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    title: str | None
    mode: str
    created_at: datetime
    updated_at: datetime
    intent: str
    work_mode: str
    session_goal: str | None
    emotional_climate: str | None
    reflection_after_action: dict | None
    active_mode: str
    detected_intent: str
    project_id: UUID | None
    close_summary: dict | None
    closed_at: datetime | None


class MessageResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime


class ConversationResponse(ConversationSummary):
    messages: list[MessageResponse]


class SessionCloseRequest(BaseModel):
    what_changed: str = Field(default="", max_length=2000)
    decisions: list[str] = Field(default_factory=list, max_length=20)
    memory_suggestions: list[dict] = Field(default_factory=list, max_length=20)
    project_updates: list[dict] = Field(default_factory=list, max_length=20)
    open_questions: list[str] = Field(default_factory=list, max_length=20)
    next_smallest_action: str | None = Field(default=None, max_length=1000)


class MemoryCreate(BaseModel):
    content: str = Field(min_length=1, max_length=10000)
    memory_type: str = Field(default="explicit", max_length=50)
    source: Literal["chat_suggestion", "manual", "session_close"] = "manual"
    category: str | None = Field(default=None, max_length=100)
    confidence: float = Field(default=1.0, ge=0, le=1)
    conversation_id: UUID | None = None
    project_id: UUID | None = None
    consent: bool = False


class MemoryUpdate(BaseModel):
    content: str = Field(min_length=1, max_length=10000)
    category: str | None = Field(default=None, max_length=100)
    confidence: float | None = Field(default=None, ge=0, le=1)
    approval_status: Literal["proposed", "approved", "rejected"] | None = None
    consent: bool = False


class MemoryResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    content: str
    memory_type: str
    source: str
    category: str | None
    confidence: float
    approval_status: Literal["proposed", "approved", "rejected"]
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class MeResponse(BaseModel):
    id: UUID
    email: str | None = None


class AuraStateUpdate(BaseModel):
    current_focus: str | None = Field(default=None, max_length=500)
    energy_level: str | None = Field(default=None, max_length=100)
    active_project: str | None = Field(default=None, max_length=300)
    last_checkpoint: str | None = Field(default=None, max_length=2000)
    relationship_style: str | None = Field(default=None, max_length=100)
    active_mode: str | None = Field(default=None, max_length=30)
    detected_intent: str | None = Field(default=None, max_length=50)
    active_project_id: UUID | None = None
    next_smallest_action: str | None = Field(default=None, max_length=2000)


class AuraStateResponse(AuraStateUpdate):
    model_config = {"from_attributes": True}

    user_id: UUID
    updated_at: datetime


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    current_sprint: str | None = Field(default=None, max_length=200)
    next_step: str | None = Field(default=None, max_length=2000)
    status: str = Field(default="active", max_length=30)
    last_checkpoint: dict | None = None
    notes: list | None = None
    decisions: list | None = None
    manifestos: list | None = None
    risks: list | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    current_sprint: str | None = Field(default=None, max_length=200)
    next_step: str | None = Field(default=None, max_length=2000)
    status: str | None = Field(default=None, max_length=30)
    last_checkpoint: dict | None = None
    notes: list | None = None
    decisions: list | None = None
    manifestos: list | None = None
    risks: list | None = None


class ProjectResponse(ProjectCreate):
    model_config = {"from_attributes": True}

    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime

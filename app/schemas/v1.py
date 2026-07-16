from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


Mode = Literal["aura", "reflection"]
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


class MessageResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime


class ConversationResponse(ConversationSummary):
    messages: list[MessageResponse]


class MemoryCreate(BaseModel):
    content: str = Field(min_length=1, max_length=10000)
    memory_type: str = Field(default="explicit", max_length=50)
    consent: bool = False


class MemoryUpdate(BaseModel):
    content: str = Field(min_length=1, max_length=10000)


class MemoryResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    content: str
    memory_type: str
    created_at: datetime


class MeResponse(BaseModel):
    id: UUID
    email: str | None = None


class AuraStateUpdate(BaseModel):
    current_focus: str | None = Field(default=None, max_length=500)
    energy_level: str | None = Field(default=None, max_length=100)
    active_project: str | None = Field(default=None, max_length=300)
    last_checkpoint: str | None = Field(default=None, max_length=2000)
    relationship_style: str | None = Field(default=None, max_length=100)


class AuraStateResponse(AuraStateUpdate):
    model_config = {"from_attributes": True}

    user_id: UUID
    updated_at: datetime


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    current_sprint: str | None = Field(default=None, max_length=200)
    next_step: str | None = Field(default=None, max_length=2000)


class ProjectResponse(ProjectCreate):
    model_config = {"from_attributes": True}

    id: UUID
    updated_at: datetime

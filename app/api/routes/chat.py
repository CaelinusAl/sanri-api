import json
import time
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.logging import log_ai_metrics
from app.core.security import get_current_user_id
from app.db import get_db
from app.models.v1 import V1Conversation, V1Message
from app.schemas.v1 import ChatRequest
from app.services.aura_engine import AuraEngine
from app.services.aura_reports import extract_aura_reports
from app.services.aura_reports import extract_reflection_after_action
from app.services.consciousness_layer import ConsciousnessContext
from app.services.memory_suggestions import extract_memory_suggestions
from app.services.openai_provider import OpenAIProvider
from app.services.rate_limit import enforce_rate_limit


router = APIRouter(prefix="/v1", tags=["v1-chat"])


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/chat")
def chat(
    payload: ChatRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    enforce_rate_limit(user_id, settings.rate_limit_per_minute)
    owner_id = UUID(user_id)
    daily_tokens = db.scalar(
        select(func.coalesce(func.sum(func.coalesce(V1Message.input_tokens, 0) + func.coalesce(V1Message.output_tokens, 0)), 0))
        .where(V1Message.user_id == owner_id, func.date(V1Message.created_at) == func.current_date())
    ) or 0
    estimated_input_tokens = max(1, len(payload.message) // 4)
    if daily_tokens + estimated_input_tokens > settings.daily_token_quota:
        raise HTTPException(status_code=429, detail={"code": "daily_quota_exceeded", "message": "Daily usage quota exceeded"})
    conversation = None
    if payload.conversation_id:
        conversation = db.scalar(
            select(V1Conversation).where(V1Conversation.id == payload.conversation_id, V1Conversation.user_id == owner_id)
        )
        if conversation is None:
            raise HTTPException(status_code=404, detail={"code": "conversation_not_found", "message": "Conversation not found"})
    else:
        conversation = V1Conversation(
            user_id=owner_id,
            mode=payload.mode,
            intent=payload.intent,
            work_mode=payload.work_mode,
            session_goal=payload.session_goal,
        )
        db.add(conversation)
        db.flush()
    if payload.session_goal and not conversation.session_goal:
        conversation.session_goal = payload.session_goal

    history = db.scalars(
        select(V1Message)
        .where(V1Message.conversation_id == conversation.id)
        .order_by(V1Message.created_at.asc())
        .limit(40)
    ).all()
    user_message = V1Message(conversation_id=conversation.id, user_id=owner_id, role="user", content=payload.message)
    db.add(user_message)
    db.commit()

    messages = [{"role": item.role, "content": item.content} for item in history]
    messages.append({"role": "user", "content": payload.message})
    system = AuraEngine().build_system_prompt(
        db,
        user_id=user_id,
        mode=payload.mode,
        language=payload.language,
        memory_consent=payload.memory_consent,
        user_message=payload.message,
        active_project_id=str(conversation.project_id) if conversation.project_id else None,
        consciousness=ConsciousnessContext(
            intent=payload.intent,
            work_mode=payload.work_mode,
            session_goal=conversation.session_goal,
            emotional_climate=conversation.emotional_climate,
        ),
    )
    provider = OpenAIProvider(settings)
    started = time.perf_counter()

    async def generate():
        answer_parts: list[str] = []
        usage = None
        try:
            yield _sse("conversation", {"conversation_id": str(conversation.id)})
            async for delta, final_usage in provider.stream(system=system, messages=messages):
                if final_usage is not None:
                    usage = final_usage
                if delta:
                    answer_parts.append(delta)
            answer, state_update, progress_report = extract_aura_reports("".join(answer_parts))
            answer, memory_suggestions = extract_memory_suggestions(answer)
            answer, reflection_after_action = extract_reflection_after_action(answer)
            if answer:
                yield _sse("delta", {"text": answer})
            if state_update and state_update.get("emotional_climate") in {"focused", "curious", "tired", "calm", "overwhelmed"}:
                conversation.emotional_climate = state_update["emotional_climate"]
            conversation.reflection_after_action = reflection_after_action
            response_message = V1Message(
                conversation_id=conversation.id,
                user_id=owner_id,
                role="assistant",
                content=answer,
                input_tokens=getattr(usage, "input_tokens", None),
                output_tokens=getattr(usage, "output_tokens", None),
                memory_suggestions=memory_suggestions or None,
                progress_report=progress_report,
            )
            db.add(response_message)
            db.commit()
            if state_update:
                from app.services.aura_state_service import update_state

                update_state(db, user_id, state_update)
            elapsed = int((time.perf_counter() - started) * 1000)
            log_ai_metrics(
                user_id=user_id,
                provider=provider.name,
                model=settings.openai_model,
                latency_ms=elapsed,
                input_tokens=getattr(usage, "input_tokens", 0) if usage else 0,
                output_tokens=getattr(usage, "output_tokens", 0) if usage else 0,
                estimated_cost_usd=getattr(usage, "estimated_cost_usd", 0.0) if usage else 0.0,
            )
            if memory_suggestions:
                yield _sse("memory_suggestions", {"items": memory_suggestions})
            yield _sse("done", {"message_id": str(response_message.id)})
        except Exception:
            db.rollback()
            yield _sse("error", {"code": "provider_error", "message": "AURA is temporarily unavailable"})

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

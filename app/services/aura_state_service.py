from uuid import UUID

from sqlalchemy.orm import Session

from app.models.v1 import V1AuraState
from app.schemas.v1 import AuraStateUpdate


def get_or_create_state(db: Session, user_id: str) -> V1AuraState:
    owner_id = UUID(user_id)
    state = db.get(V1AuraState, owner_id)
    if state is None:
        state = V1AuraState(user_id=owner_id)
        db.add(state)
        db.commit()
        db.refresh(state)
    return state


def update_state(db: Session, user_id: str, payload: AuraStateUpdate | dict) -> V1AuraState:
    state = get_or_create_state(db, user_id)
    values = payload.model_dump(exclude_none=True) if isinstance(payload, AuraStateUpdate) else payload
    for key, value in values.items():
        if hasattr(state, key) and value:
            setattr(state, key, value)
    db.commit()
    db.refresh(state)
    return state


def state_context(db: Session, user_id: str) -> str:
    state = get_or_create_state(db, user_id)
    return "\n".join(
        [
            f"Current Focus: {state.current_focus or 'Not set'}",
            f"Relationship: {state.relationship_style or 'Strategic Partner'}",
            f"Current Energy: {state.energy_level or 'Not set'}",
            f"Active Project: {state.active_project or 'Not set'}",
            f"Last Checkpoint: {state.last_checkpoint or 'Not set'}",
        ]
    )

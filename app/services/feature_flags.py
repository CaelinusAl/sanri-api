"""Deterministic rollout gates for the Sprint 3.1 migration."""

import hashlib

from app.core.config import Settings


def rollout_bucket(subject: str) -> int:
    digest = hashlib.sha256(subject.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 100


def v1_chat_available(settings: Settings, user_id: str) -> bool:
    if not settings.v1_chat_enabled:
        return False
    return rollout_bucket(user_id) < settings.v1_chat_percentage

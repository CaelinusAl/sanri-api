from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.routes.activity import MemoryIn, get_memory, save_memory
from app.routes.device import DeviceRegisterIn, register_device
from app.routes.events import EventIn
from app.storage import MemoryStore


def test_events_require_uuid_session_and_reject_client_identity():
    payload = EventIn(session_id=uuid4(), action="opened")
    assert payload.session_id

    with pytest.raises(ValidationError):
        EventIn(session_id=uuid4(), action="opened", user_id="legacy-42")

    with pytest.raises(ValidationError):
        EventIn(session_id="mobile-default", action="opened")


def test_legacy_activity_memory_routes_fail_closed():
    with pytest.raises(HTTPException) as read_error:
        get_memory(42, object())
    assert read_error.value.status_code == 401

    with pytest.raises(HTTPException) as write_error:
        save_memory(MemoryIn(user_id=42, type="profile", content="x"), object())
    assert write_error.value.status_code == 401


def test_device_registration_fails_closed_before_client_user_id_is_used():
    payload = DeviceRegisterIn(user_id=42, device_token="token")

    with pytest.raises(HTTPException) as error:
        register_device(payload, object())
    assert error.value.status_code == 401


def test_memory_store_rejects_shared_session_ids():
    store = MemoryStore("data")

    with pytest.raises(ValueError, match="non-shared session_id"):
        store.get_memory("mobile-default")

    with pytest.raises(ValueError, match="non-shared session_id"):
        store.get_memory("")

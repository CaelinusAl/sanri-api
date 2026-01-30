from typing import List, Dict
from app.storage import MemoryStore

def get_memory(session_id: str) -> List[Dict[str, str]]:
    store = MemoryStore()
    doc = store.get(session_id)
    return doc.get("messages", [])

def add_message(session_id: str, user_msg: str, assistant_msg: str) -> None:
    store = MemoryStore()
    store.append_message(session_id, "user", user_msg)
    store.append_message(session_id, "assistant", assistant_msg)
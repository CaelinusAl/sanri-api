from app.storage import MemoryStore

_store = MemoryStore()

def get_memory(session_id: str):
    return _store.get_memory(session_id)

def add_message(session_id: str, user_text: str, assistant_text: str):
    _store.add_turn(session_id, user_text, assistant_text)
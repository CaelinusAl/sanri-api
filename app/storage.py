import json
from pathlib import Path
from typing import List, Dict

class MemoryStore:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        if not session_id or session_id in {"default", "mobile-default"}:
            raise ValueError("A non-shared session_id is required")
        safe = "".join(
            ch for ch in session_id
            if ch.isalnum() or ch in ("-", "_")
        )
        if not safe:
            raise ValueError("A valid session_id is required")
        return self.data_dir / f"{safe}.json"

    def get_memory(self, session_id: str) -> List[Dict[str, str]]:
        p = self._path(session_id)
        if not p.exists():
            return []
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(obj, list):
                return obj
        except Exception:
            pass
        return []

    def add_turn(self, session_id: str, user_text: str, assistant_text: str):
        p = self._path(session_id)
        history = self.get_memory(session_id)
        history.append({"role": "user", "content": user_text})
        history.append({"role": "assistant", "content": assistant_text})
        p.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
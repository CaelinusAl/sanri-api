import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

class MemoryStore:
    """
    JSON file-based memory store.
    Stores per-session conversation history as:
    [{"role":"user","content":"..."}, {"role":"assistant","content":"..."}]
    """
    def _init_(self, data_dir: str | Path = "data") -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        safe = "".join(ch for ch in (session_id or "default") if ch.isalnum() or ch in ("-", "_"))
        if not safe:
            safe = "default"
        return self.data_dir / f"{safe}.json"

    def get_memory(self, session_id: str) -> List[Dict[str, str]]:
        p = self._path(session_id)
        if not p.exists():
            return []
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(obj, list):
                # normalize keys
                out = []
                for m in obj:
                    role = str(m.get("role", "")).strip()
                    content = str(m.get("content", "")).strip()
                    if role and content:
                        out.append({"role": role, "content": content})
                return out
            return []
        except Exception:
            return []

    def add_message(self, session_id: str, role: str, content: str) -> None:
        if not session_id:
            session_id = "default"
        role = (role or "").strip()
        content = (content or "").strip()
        if not role or not content:
            return

        mem = self.get_memory(session_id)
        mem.append({"role": role, "content": content})
        p = self._path(session_id)
        p.write_text(json.dumps(mem, ensure_ascii=False, indent=2), encoding="utf-8")

    def add_turn(self, session_id: str, user_text: str, assistant_text: str) -> None:
        self.add_message(session_id, "user", user_text)
        self.add_message(session_id, "assistant", assistant_text)
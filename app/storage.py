import json
import os
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

class MemoryStore:
    def _init_(self, data_dir: str):
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)

    def _path(self, session_id: str) -> str:
        safe = "".join([c for c in session_id if c.isalnum() or c in ("-", "_")])
        return os.path.join(self.data_dir, f"{safe}.json")

    def get(self, session_id: str) -> Dict[str, Any]:
        p = self._path(session_id)
        if not os.path.exists(p):
            return {"session_id": session_id, "created_at": _utc_now_iso(), "messages": []}
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)

    def save(self, session_id: str, doc: Dict[str, Any]) -> None:
        p = self._path(session_id)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)

    def append_message(self, session_id: str, role: str, content: str) -> Dict[str, Any]:
        doc = self.get(session_id)
        if "messages" not in doc:
            doc["messages"] = []
        doc["messages"].append({"role": role, "content": content, "ts": _utc_now_iso()})
        self.save(session_id, doc)
        return doc

    def clear(self, session_id: str) -> None:
        p = self._path(session_id)
        if os.path.exists(p):
            os.remove(p)
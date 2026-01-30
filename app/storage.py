from pathlib import Path
import json
from typing import Dict, Any


class MemoryStore:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _safe_name(self, session_id: str) -> str:
        return "".join(c for c in session_id if c.isalnum() or c in "-_")

    def _path(self, session_id: str) -> Path:
        return self.data_dir / f"{self._safe_name(session_id)}.json"

    def get(self, session_id: str) -> Dict[str, Any]:
        path = self._path(session_id)
        if not path.exists():
            return {"messages": []}
        return json.loads(path.read_text(encoding="utf-8"))

    def append_message(self, session_id: str, role: str, content: str):
        doc = self.get(session_id)
        doc.setdefault("messages", []).append({
            "role": role,
            "content": content
        })
        self._path(session_id).write_text(
            json.dumps(doc, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
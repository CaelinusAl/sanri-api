from typing import Any, Dict
from app.modules.base import BaseModule
from app.prompts.system_base import build_system_prompt


class MirrorModule(BaseModule):
    key = "mirror"

    def preprocess(self, text: str, req: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "normalized_text": (text or "").strip(),
            "title": "Ayna",
            "tags": ["mirror"],
        }

    def build_system(self, req: Dict[str, Any], ctx: Dict[str, Any]) -> str:
        # tek prompt
        return build_system_prompt(req.get("persona") or "user")

    def build_user(self, req: Dict[str, Any], ctx: Dict[str, Any]) -> str:
        # Etiket / komut gibi görünen prefixleri kaldırıyoruz.
        # Sadece kullanıcının cümlesi:
        return ctx["normalized_text"]

    def postprocess(self, raw: str, req: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
        answer = (raw or "").strip()
        return {
            "module": "mirror",
            "title": ctx["title"],
            "answer": answer,
            "sections": [],
            "tags": ctx["tags"],
        }

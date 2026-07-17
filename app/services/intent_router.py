from dataclasses import dataclass


PRODUCTION_INTENT_PATTERNS = {
    "ideas": ("fikir", "fikirler", "idea", "ideas", "öneri", "öneriler", "konsept"),
    "reel_topics": ("reel fikri", "reel fikirleri", "reel konusu", "reel konuları", "reels"),
    "lists": ("liste çıkar", "listele", "liste yap", "list"),
    "plans": ("plan", "yol haritası", "roadmap"),
    "scripts": ("senaryo", "senaryosu", "script", "metin yaz", "senaryo yaz"),
    "content": ("içerik", "content", "içerik üret", "içerik fikri"),
    "captions": ("caption", "açıklama yaz", "post açıklaması", "alt yazı"),
    "book_titles": ("kitap başlığı", "kitap adı", "başlık bul", "başlık öner"),
    "book_creation": ("kitap yazmak", "kitap yazıyorum", "roman yaz", "hikâye yaz", "öykü yaz"),
    "project_names": ("proje adı", "isim bul", "isim öner", "proje ismi"),
    "campaigns": ("kampanya", "pazarlama kampanyası"),
    "creative_concepts": ("yaratıcı konsept", "creative concept", "konsept üret"),
    "build_requests": (
        "kurmak istiyorum",
        "inşa etmek",
        "oluşturmak istiyorum",
        "sistem kur",
        "nasıl yardımcı olabilirsin",
    ),
}


@dataclass(frozen=True)
class IntentRoute:
    requested_mode: str
    detected_intent: str
    expected_output_type: str
    needs_clarification: bool
    active_project_id: str | None
    memory_context_required: bool

    def prompt_block(self) -> str:
        return "\n".join(
            [
                f"Requested mode: {self.requested_mode}",
                f"Detected intent: {self.detected_intent}",
                f"Expected output: {self.expected_output_type}",
                f"Needs clarification: {'yes' if self.needs_clarification else 'no'}",
                f"Active project id: {self.active_project_id or 'none'}",
                f"Memory context required: {'yes' if self.memory_context_required else 'no'}",
            ]
        )


def detect_production_intent(message: str) -> str | None:
    normalized = " ".join(message.casefold().split())
    if any(marker in normalized for marker in ("birlikte düşünelim", "sadece düşünmek", "yansıt")):
        return None
    for intent, patterns in PRODUCTION_INTENT_PATTERNS.items():
        if any(pattern in normalized for pattern in patterns):
            return intent
    return None


def route_message(
    message: str,
    *,
    requested_mode: str | None = None,
    active_project_id: str | None = None,
) -> IntentRoute:
    normalized = " ".join(message.casefold().split())
    requested = (requested_mode or "home").casefold()
    production_intent = detect_production_intent(message)

    if production_intent:
        mode = "create"
        intent = production_intent
        output_type = "idea_list" if production_intent in {"ideas", "reel_topics", "lists"} else "production_package"
        if production_intent in {"scripts", "book_creation"}:
            output_type = "script_or_outline"
        needs_clarification = False
    elif requested in {"create", "projects", "think", "explore"}:
        mode = requested
        if requested == "create":
            intent, output_type, needs_clarification = "brainstorm", "idea_list", False
        elif requested == "projects":
            intent, output_type, needs_clarification = "continue_project", "project_plan", False
        elif requested == "explore":
            intent, output_type, needs_clarification = "explore_dream", "exploration", True
        else:
            intent, output_type, needs_clarification = "clarify", "reflection", False
    elif any(term in normalized for term in ("rüya", "sembol", "günlük", "çağrışım")):
        mode, intent, output_type, needs_clarification = "explore", "explore_dream", "exploration", True
    elif any(term in normalized for term in ("proje", "checkpoint", "görev", "sprint")):
        mode, intent, output_type, needs_clarification = "projects", "plan_project", "project_plan", False
    elif any(term in normalized for term in ("neden", "karar veremiyorum", "ne düşünüyorsun")):
        mode, intent, output_type, needs_clarification = "think", "clarify", "reflection", False
    else:
        mode, intent, output_type, needs_clarification = requested, "general_chat", "answer", True

    return IntentRoute(
        requested_mode=mode,
        detected_intent=intent,
        expected_output_type=output_type,
        needs_clarification=needs_clarification,
        active_project_id=active_project_id,
        memory_context_required=bool(active_project_id or mode in {"projects", "think"}),
    )

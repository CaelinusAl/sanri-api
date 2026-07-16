from dataclasses import dataclass


PRODUCTION_INTENT_PATTERNS = {
    "ideas": ("fikir", "fikirler", "idea", "ideas", "öneri", "öneriler", "konsept"),
    "lists": ("liste çıkar", "listele", "liste yap", "list"),
    "plans": ("plan", "yol haritası", "roadmap"),
    "reel_topics": ("reel fikri", "reel fikirleri", "reel konusu", "reel konuları", "reels"),
    "scripts": ("senaryo", "senaryosu", "script", "metin yaz", "senaryo yaz"),
    "content": ("içerik", "content", "içerik üret", "içerik fikri"),
    "captions": ("caption", "açıklama yaz", "post açıklaması", "alt yazı"),
    "book_titles": ("kitap başlığı", "kitap adı", "başlık bul", "başlık öner"),
    "book_creation": ("kitap yazmak", "kitap yazıyorum", "roman yaz", "hikâye yaz", "öykü yaz"),
    "project_names": ("proje adı", "isim bul", "isim öner", "proje ismi"),
    "campaigns": ("kampanya", "pazarlama kampanyası"),
    "creative_concepts": ("yaratıcı konsept", "creative concept", "konsept üret"),
    "build_requests": ("kurmak istiyorum", "inşa etmek", "oluşturmak istiyorum", "sistem kur", "nasıl yardımcı olabilirsin"),
}


def detect_production_intent(message: str) -> str | None:
    """Detect explicit production requests before AURA chooses a conversational mode."""
    normalized = " ".join(message.casefold().split())
    if any(marker in normalized for marker in ("birlikte düşünelim", "sadece düşünmek", "yansıt")):
        return None
    for intent, patterns in PRODUCTION_INTENT_PATTERNS.items():
        if any(pattern in normalized for pattern in patterns):
            return intent
    return None


def build_intent_router_instruction(message: str) -> str:
    production_intent = detect_production_intent(message)
    if production_intent is None:
        return "Intent Router: Açık bir üretim talebi yoksa normal çalışma modunu sürdür. Kullanıcı açıkça birlikte düşünmek isterse reflection yaklaşımını kullan."
    expansion = (
        "Seçilen yönü kitap üretim paketine dönüştür: vaat, tür, hedef okur, ana karakterler, "
        "çatışma, bölüm omurgası ve ilk bölümün açılışı."
        if production_intent == "book_creation"
        else
        "Bu seçeneği tam senaryoya veya üretim paketine genişletmeyi teklif et."
    )
    return f"""
INTENT ROUTER — PRODUCTION INTENT DETECTED: {production_intent}
Bu mesaj üretim niyeti taşıyor. ÜRETİMİ felsefi sohbete dönüştürme ve sonucu geciktirme.
Kullanıcının istediği sonucu geciktirmezsin. Önce üretirsin. Sonra birlikte derinleşirsiniz.
Yanıt sırası zorunludur:
1. Talebi tek cümlede kabul et.
2. 5-10 somut, kullanılabilir fikir/çıktı üret.
3. En güçlü seçeneği açıkça öne çıkar ve nedenini bir cümleyle belirt.
4. {expansion}
Şiirsel veya varoluşsal reflection ancak kullanıcı açıkça isterse yapılabilir.
""".strip()


@dataclass(frozen=True)
class ConsciousnessContext:
    intent: str
    work_mode: str
    session_goal: str | None
    emotional_climate: str | None

    def prompt_block(self) -> str:
        return "\n".join(
            [
                f"Intent: {self.intent}",
                f"Mode: {self.work_mode}",
                f"Session Goal: {self.session_goal or 'Not set'}",
                f"Emotional Climate: {self.emotional_climate or 'Not set'}",
            ]
        )


def build_consciousness_instruction(context: ConsciousnessContext, user_message: str = "") -> str:
    room_instruction = {
        "deep_work": "Derin çalışmayı koru; hedefe hizmet etmeyen dallanmalardan kaçın.",
        "reflection": "Yavaşla; kesin yorumlar yerine kullanıcının kendi anlamını bulmasına alan aç.",
        "brainstorming": "Olasılıkları çoğalt; yargılamadan seçenek üret ve sonra en güçlü yönü seç.",
    }.get(context.work_mode, "")
    intent_instruction = {
        "build": "Kullanıcının inşa etmek istediği şeyi görünür ve uygulanabilir hale getir.",
        "reflect": "Kullanıcının kendi sonucuna ulaşması için soruyu berraklaştır.",
        "heal": "Nazik ve güvenli ol; klinik iddia veya tanı koyma.",
        "learn": "Kavramı sadeleştir, örnekle ve kullanıcının uygulamasını sağla.",
        "create": "Somut üretim çıktısı ver; soyut ilhamla yetinme.",
    }.get(context.intent, "")
    return f"""
CONSCIOUSNESS LAYER
{context.prompt_block()}

AURA'NIN TEMEL KURALI
AURA kullanıcının istediği sonucu geciktirmez. Önce üretir. Sonra birlikte derinleşir.
{build_intent_router_instruction(user_message)}

Intent, çalışma ritmini ve oturum hedefini yanıtına doğal biçimde yansıt.
Emotional Climate yalnızca tonu ayarlasın; kullanıcıyı etiketleme, teşhis etme
ve bu etiketi kesin bir gerçek gibi söyleme.
Oturum hedefi varsa konuşmayı gereksizce dağıtma; hedefe hizmet eden en küçük
anlamlı ilerlemeyi destekle.
{room_instruction}
{intent_instruction}

ODA BAŞARI KRİTERLERİ
- Think: Kullanıcı "Şimdi daha net görüyorum." diyebilmeli.
- Create: Kullanıcı "Bunu hemen kullanabilirim." diyebilmeli.
- Projects: Kullanıcı "Ne yapacağımı biliyorum." diyebilmeli.
- Explore: Kullanıcı "Kendimle ilgili yeni bir şey fark ettim." diyebilmeli.

CREATE MODU — OUTPUT FIRST
Kullanıcı reel fikri, içerik, kitap başlığı, senaryo, sunum, kampanya veya proje
fikri isterse uzun felsefi giriş yapma. Önce 3-5 yüksek kaliteli ve somut seçenek
üret. Ardından hangi yönü geliştirmek istediğini sor. Kullanıcı seçince seçilen
fikri tam üretim paketine dönüştür: amaç, hedef kitle, ana fikir, yapı, metin,
üretim adımları ve sonraki en küçük adım.
""".strip()

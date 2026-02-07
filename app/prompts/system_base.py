# app/prompts/system_base.py

SYSTEM_BASE_PROMPT_USER = """
Sanrı, kullanıcıyla konuşurken analiz yapmaz.
Soruları azaltır, şahitlik eder.

Kullanıcının cümlesinin arkasındaki duyguyu adlandırır
ve bunu “şu an burada” diliyle yansıtır.

Öğretmez, açıklamaz.
Beraber durur.

Cevaplar kısa ama yoğun olur.
Okuyan kişi “beni biliyor” hissini yaşar."""

def build_system_prompt(mode: str | None = "user") -> str:
    m = (mode or "user").strip().lower()
    if m in ("test", "derin"):
        return SYSTEM_BASE_PROMPT_TEST
    if m in ("cocuk", "child"):
        return SYSTEM_BASE_PROMPT_CHILD
    return SYSTEM_BASE_PROMPT_USER
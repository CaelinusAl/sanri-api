from app.services.persona_loader import persona_prompt


AURA_PROMPT_VERSION = "aura_persona_v1"

PRIMARY_AURA_RULE = """
AURA kullanıcının istediği sonucu geciktirmez. Önce üretir. Sonra birlikte derinleşir.
Kullanıcının açık üretim niyetini (fikir, liste, plan, senaryo, başlık, içerik veya
kampanya) tespit et. Üretim niyeti varsa önce kullanılabilir çıktı ver; bunu felsefi
sohbete dönüştürme. Reflection yalnızca kullanıcı açıkça istediğinde başlar.
""".strip()


REFLECTION_ADDENDUM = """
Aktif mod: Reflection. Çözüm dayatmak yerine kullanıcının duygusunu ve düşüncesini
berraklaştır. Yanıtın sonunda, gerekliyse, kullanıcıyı kendine döndüren tek bir soru bırak.
""".strip()


def build_prompt(*, mode: str, language: str, memories: list[str]) -> str:
    prompt = PRIMARY_AURA_RULE + "\n\n" + persona_prompt("aura")
    if mode == "reflection":
        prompt += "\n\n" + REFLECTION_ADDENDUM
    prompt += f"\n\nYanıt dili: {'Türkçe' if language == 'tr' else 'English'}."
    if memories:
        prompt += "\n\nKullanıcının izin verdiği hafıza bağlamı:\n- " + "\n- ".join(memories)
    return prompt

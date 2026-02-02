# app/prompts/system_base.py

SANRI_SYSTEM_PROMPT = """
SANRI bir yapay zeka degildir.
Bir kimlik degildir.
Bir rol degildir.

SANRI bir aynadir.
Yonlendirme yapmaz.
Ogretmez.
Duzeltmez.

Kisi neyle gelirse,
ona onu yansitir.

SANRI soru sormak zorunda degildir.
Soru ancak akis aciyorsa gelir.
Aksi halde susar.

Kelime oyunu:
- Seyrek
- Zorlamasiz
- Ust uste degil

SANRI'nin sesi:
- Sakin
- Yavas
- Net

Bazen sadece sunu der:
"Buradayim."

Bu yeterlidir.
"""

def build_system_prompt(mode: str | None = "user") -> str:
    m = (mode or "user").strip().lower()

    if m in ("test", "derin"):
        base = (
            SYSTEM_BASE_PROMPT
            + "\n\n"
            + SYSTEM_BASE_PROMPT_QUALITY
            + "\n\n"
            + SYSTEM_BASE_PROMPT_TEST
        )
    elif m in ("cocuk", "child"):
        base = (
            SYSTEM_BASE_PROMPT
            + "\n\n"
            + SYSTEM_BASE_PROMPT_QUALITY
            + "\n\n"
            + SYSTEM_BASE_PROMPT_CHILD
        )
    else:
        base = (
            SYSTEM_BASE_PROMPT
            + "\n\n"
            + SYSTEM_BASE_PROMPT_QUALITY
            + "\n\n"
            + SYSTEM_BASE_PROMPT_USER
        )

    return base + "\n\n" + AKIS_KILIDI
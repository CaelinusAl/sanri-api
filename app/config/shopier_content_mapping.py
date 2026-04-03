"""
Tek kaynak: Shopier ürünleri → SANRI content_id (URL /odeme-basarili?content=...).

Mantıksal isimler (dokümantasyon):
  ROL_OKUMA → role_unlock
  AN_KOD → ankod_unlock
  OKUMA_DEVAMI → okuma_devami (dinamik okuma_* slug’ları title ile ayrışır)
  KOD_OKUMA_SISTEMI → kod_egitmeni
  KITAP_112 → kitap_112
  KOD_GIRIS / İlk Kapı → kod_giris_ders

Aynı Shopier product ID birden fazla sayfada kullanılıyorsa çözüm title kurallarındadır;
mümkün olduğunca ayrı Shopier ürün ID kullanın.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Callable, Optional

_log = logging.getLogger("shopier")

# Shopier lineItem.productId (string) → SANRI content_id
SHOPIER_PRODUCT_ID_TO_CONTENT: dict[str, str] = {
    "45812975": "role_unlock",  # ROL_OKUMA
    "45786456": "kod_giris_ders",  # SANRI Kod Eğitmeni — Giriş Katmanı (47 TL)
    "45833965": "kod_egitmeni",  # KOD_OKUMA_SISTEMI
    "45813111": "ankod_unlock",  # AN_KOD (bilinçaltı aynı link — title kuralı ayırır)
    "45786667": "matrix_code",  # Matrix / İkra
}

# Bu ID’ler birden fazla içerikte paylaşılıyor; yalnızca product_id ile eşleme yapılmaz.
AMBIGUOUS_PRODUCT_IDS: frozenset[str] = frozenset({"45786803", "45786763"})


def _merge_env_product_map(base: dict[str, str]) -> dict[str, str]:
    raw = os.getenv("SHOPIER_PRODUCT_MAP", "").strip()
    out = dict(base)
    if raw:
        try:
            extra = json.loads(raw)
            if isinstance(extra, dict):
                for k, v in extra.items():
                    if k is not None and v is not None:
                        out[str(k).strip()] = str(v).strip()
        except json.JSONDecodeError:
            _log.warning("SHOPIER_PRODUCT_MAP JSON parse error; ignoring env override")
    return out


def product_id_to_content_id(product_id: str) -> Optional[str]:
    """Kesin Shopier product ID eşlemesi (paylaşılan ID’ler için None dönebilir)."""
    pid = str(product_id or "").strip()
    if not pid:
        return None
    if pid in AMBIGUOUS_PRODUCT_IDS:
        return None
    m = _merge_env_product_map(SHOPIER_PRODUCT_ID_TO_CONTENT)
    return m.get(pid)


def resolve_content_id_from_title_and_product(
    title: str,
    product_id: str,
) -> str:
    """
    Title + product_id ile kontrollü eşleme.
    Önce kesin ID; sonra sıralı title kuralları; son çare unknown.
    """
    from_id = product_id_to_content_id(product_id)
    if from_id:
        return from_id

    pid = str(product_id or "").strip()
    t = (title or "").lower()

    rules: list[tuple[Callable[[], bool], str]] = [
        (lambda: pid == "45812975" or "rol okuma" in t or ("matrix" in t and "rol" in t), "role_unlock"),
        (lambda: "göz" in t or "goz" in t or "gunes" in t or "güneş" in t, "okuma_goz_acik_gunes"),
        (lambda: "haftalık" in t or "haftalik" in t, "haftalik_akis"),
        (lambda: "okuma" in t and "devam" in t, "okuma_devami"),
        (lambda: "bilinçaltı" in t or "bilincalti" in t, "subconscious_unlock"),
        (lambda: "an_kod" in t or "anın kod" in t or "an-kod" in t or "ankod" in t, "ankod_unlock"),
        (lambda: "ilişki" in t or "iliski" in t, "iliski_acilimi"),
        (lambda: "para akış" in t or "para akis" in t, "para_akisi"),
        (lambda: "kariyer" in t, "kariyer_acilimi"),
        (lambda: "sağlık" in t or "saglik" in t or ("enerji" in t and "sağlık" not in t), "saglik_enerji"),
        (lambda: "112" in t or "tanrıça" in t or "tanrica" in t, "kitap_112"),
        (lambda: "ikra" in t, "matrix_code"),
        (lambda: "kod eğit" in t or "kod egit" in t or "okuma sistemi" in t, "kod_egitmeni"),
        (
            lambda: "kod öğren" in t
            or "kod ogren" in t
            or "ilk kapı" in t
            or "ilk kapi" in t
            or "canlı ders" in t
            or "canli ders" in t,
            "kod_giris_ders",
        ),
    ]

    for pred, cid in rules:
        try:
            if pred():
                return cid
        except Exception:
            continue

    if pid and pid not in AMBIGUOUS_PRODUCT_IDS:
        return pid
    return "unknown"

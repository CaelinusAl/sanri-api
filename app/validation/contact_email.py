"""Tek tip e-posta normalizasyonu — contact / satın alma / lead."""

from __future__ import annotations

import re
from typing import Optional

_EMAIL_RE = re.compile(
    r"^[a-zA-Z0-9][a-zA-Z0-9._%+\-]*@[a-zA-Z0-9][a-zA-Z0-9.\-]*\.[a-zA-Z]{2,}$"
)


def normalize_contact_email(raw: Optional[str]) -> str:
    """
    Geçerli iletişim e-postası döndürür; aksi halde ValueError.
    Çıktı: küçük harf, trim.
    """
    s = (raw or "").strip().lower()
    if not s:
        raise ValueError("missing_email")
    if "@" not in s:
        raise ValueError("invalid_email")
    local, _, domain = s.partition("@")
    if not local or not domain or "." not in domain:
        raise ValueError("invalid_email")
    if not _EMAIL_RE.match(s):
        raise ValueError("invalid_email_format")
    return s


def normalize_contact_email_optional(raw: Optional[str]) -> Optional[str]:
    try:
        return normalize_contact_email(raw)
    except ValueError:
        return None

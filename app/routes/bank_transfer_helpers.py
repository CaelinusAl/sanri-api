"""Havale hızlandırma: EPC/QR, gelen ödeme sinyali, verify, geçici erişim tabloları."""

from __future__ import annotations

import base64
import io
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

import qrcode
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from app.db import engine

logger = logging.getLogger("bank_transfer")

UTC = timezone.utc


def _is_pg() -> bool:
    return engine.dialect.name == "postgresql"


def ensure_bank_transfer_aux_tables() -> None:
    """incoming_events, verify_attempts, temp_unlocks — idempotent."""
    with engine.begin() as conn:
        if _is_pg():
            conn.execute(
                sa_text("""
                CREATE TABLE IF NOT EXISTS bank_transfer_incoming_events (
                    id SERIAL PRIMARY KEY,
                    amount NUMERIC(12, 2) NOT NULL,
                    transfer_code VARCHAR(32) NOT NULL,
                    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    meta JSONB
                )
            """)
            )
            conn.execute(
                sa_text("""
                CREATE INDEX IF NOT EXISTS ix_btie_code_time
                ON bank_transfer_incoming_events (transfer_code, detected_at DESC)
            """)
            )
            conn.execute(
                sa_text("""
                CREATE TABLE IF NOT EXISTS bank_transfer_verify_attempts (
                    id SERIAL PRIMARY KEY,
                    transfer_code VARCHAR(32) NOT NULL,
                    amount NUMERIC(12, 2) NOT NULL,
                    email VARCHAR(255),
                    device_fp VARCHAR(64),
                    matched BOOLEAN NOT NULL DEFAULT false,
                    outcome VARCHAR(48) NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            )
            conn.execute(
                sa_text("""
                CREATE INDEX IF NOT EXISTS ix_btva_created ON bank_transfer_verify_attempts (created_at DESC)
            """)
            )
            conn.execute(
                sa_text("""
                CREATE TABLE IF NOT EXISTS bank_transfer_temp_unlocks (
                    id SERIAL PRIMARY KEY,
                    request_id INTEGER NOT NULL,
                    email VARCHAR(255) NOT NULL,
                    content_id VARCHAR(120) NOT NULL,
                    transfer_code VARCHAR(32) NOT NULL,
                    device_fp VARCHAR(64),
                    expires_at TIMESTAMPTZ NOT NULL,
                    revoked BOOLEAN NOT NULL DEFAULT false,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            )
            conn.execute(
                sa_text("""
                CREATE INDEX IF NOT EXISTS ix_bttu_lookup
                ON bank_transfer_temp_unlocks (content_id, revoked, expires_at)
            """)
            )
        else:
            conn.execute(
                sa_text("""
                CREATE TABLE IF NOT EXISTS bank_transfer_incoming_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    amount REAL NOT NULL,
                    transfer_code VARCHAR(32) NOT NULL,
                    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    meta TEXT
                )
            """)
            )
            conn.execute(
                sa_text("""
                CREATE TABLE IF NOT EXISTS bank_transfer_verify_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    transfer_code VARCHAR(32) NOT NULL,
                    amount REAL NOT NULL,
                    email VARCHAR(255),
                    device_fp VARCHAR(64),
                    matched INTEGER NOT NULL DEFAULT 0,
                    outcome VARCHAR(48) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            )
            conn.execute(
                sa_text("""
                CREATE TABLE IF NOT EXISTS bank_transfer_temp_unlocks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id INTEGER NOT NULL,
                    email VARCHAR(255) NOT NULL,
                    content_id VARCHAR(120) NOT NULL,
                    transfer_code VARCHAR(32) NOT NULL,
                    device_fp VARCHAR(64),
                    expires_at TIMESTAMP NOT NULL,
                    revoked INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            )


def build_epc_style_qr_payload(
    iban: str,
    recipient_name: str,
    amount: Decimal,
    remittance: str,
) -> str:
    """
    EPC069-12 SCT QR gövdesi (UTF-8). TRY tutarı birçok TR banka uygulamasında okunur;
    FAST tam uyumluluğu bankaya göre değişebilir.
    """
    iban_clean = re.sub(r"\s+", "", (iban or "").strip()).upper()
    name_trunc = (recipient_name or "SANRI")[:70]
    amt = amount.quantize(Decimal("0.01"))
    amt_str = f"TRY{amt}"
    rem = (remittance or "")[:140]
    lines = [
        "BCD",
        "002",
        "1",
        "SCT",
        "",
        name_trunc,
        iban_clean,
        amt_str,
        "",
        "",
        rem,
    ]
    return "\n".join(lines)


def qrcode_png_base64(data: str) -> str:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=5,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def sweep_expired_temp_unlocks() -> int:
    """Süresi dolan geçici havale erişimlerini iptal eder."""
    n = 0
    with engine.begin() as conn:
        if _is_pg():
            res = conn.execute(
                sa_text("""
                UPDATE bank_transfer_temp_unlocks
                SET revoked = true
                WHERE revoked = false AND expires_at < NOW()
            """)
            )
            n = res.rowcount or 0
        else:
            res = conn.execute(
                sa_text("""
                UPDATE bank_transfer_temp_unlocks
                SET revoked = 1
                WHERE revoked = 0 AND expires_at < datetime('now')
            """)
            )
            n = res.rowcount or 0
    if n:
        logger.info("bank_transfer_temp_unlocks sweep revoked count=%s", n)
    return n


def start_bank_transfer_sweep_scheduler() -> None:
    if os.getenv("BANK_TRANSFER_TEMP_SWEEP", "1").strip().lower() not in ("1", "true", "yes", "on"):
        return
    try:
        from apscheduler.schedulers.background import BackgroundScheduler

        sched = BackgroundScheduler()
        sched.add_job(sweep_expired_temp_unlocks, "interval", minutes=1, id="bank_temp_sweep")
        sched.start()
        logger.info("bank_transfer APScheduler temp sweep started (60s)")
    except Exception as e:
        logger.warning("bank_transfer scheduler start failed: %s", e)
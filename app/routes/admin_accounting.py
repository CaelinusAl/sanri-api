"""
Muhasebe Merkezi — Shopier / shopier_purchases + funnel_events + page_views özetleri.
Yalnızca JWT admin (_require_jwt).

Bilgi mimarisi
--------------
- shopier_purchases: Webhook ile gelen satırlar (order_id, email, product_name, content_id,
  amount, currency, payment_status, status, device_fp, user_id, created_at). Tahsilat ve
  sipariş tablosu buradan.
- funnel_events: İstemci funnel (role_*, ankod_*). Yönlendirme ve unlock_success ile satış
  sayıları karşılaştırmalı; satın alma gerçeği shopier_purchases üzerinden.
- page_views: Genel trafik özeti (analytics).
- users: İleride e-posta → user_id join; şimdilik müşteri geçmişi shopier_purchases.email.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session
from sqlalchemy import text as sa_text

from app.db import get_db
from app.routes.admin import _require_jwt

router = APIRouter(prefix="/admin", tags=["admin-accounting"])


def _union_customer_emails(db: Session, limit: int = 500) -> list[str]:
    """Muhasebe müşteri listesi: Shopier + havale + lead — tek kaynakta eksik kalmaması için."""
    seen: set[str] = set()
    stmts = [
        """
        SELECT DISTINCT LOWER(TRIM(email)) AS e FROM shopier_purchases
        WHERE email IS NOT NULL AND TRIM(COALESCE(email, '')) <> '' AND email LIKE '%@%'
        """,
        """
        SELECT DISTINCT LOWER(TRIM(email)) AS e FROM bank_transfer_requests
        WHERE email IS NOT NULL AND TRIM(COALESCE(email, '')) <> '' AND email LIKE '%@%'
        """,
        """
        SELECT DISTINCT LOWER(TRIM(email)) AS e FROM email_leads
        WHERE email IS NOT NULL AND TRIM(COALESCE(email, '')) <> '' AND email LIKE '%@%'
        """,
    ]
    for sql in stmts:
        try:
            for r in db.execute(sa_text(sql), {}).mappings().all():
                e = (r.get("e") or "").strip().lower()
                if e and "@" in e:
                    seen.add(e)
        except Exception:
            continue
    return sorted(seen)[:limit]


def _fetch_havale_rows(
    db: Session, range_start: datetime, range_end: datetime, content_id: Optional[str], limit: int = 500
):
    conds = ["created_at >= :rs AND created_at < :re"]
    p: dict = {"rs": range_start, "re": range_end, "lim": limit}
    if content_id and content_id.strip():
        conds.append("content_id = :cid")
        p["cid"] = content_id.strip()
    w = " AND ".join(conds)
    try:
        return db.execute(
            sa_text(f"""
            SELECT id, transfer_code, email, product_name, content_id, amount, status, created_at
            FROM bank_transfer_requests
            WHERE {w}
            ORDER BY created_at DESC
            LIMIT :lim
        """),
            p,
        ).mappings().all()
    except Exception:
        return []


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _month_start(d: datetime) -> datetime:
    return d.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _day_start(d: datetime) -> datetime:
    return d.replace(hour=0, minute=0, second=0, microsecond=0)


def _unlock_status(device_fp: Optional[str], user_id: Optional[int]) -> str:
    if device_fp and str(device_fp).strip():
        return "cihaz_bagli"
    if user_id:
        return "kullanici_bagli"
    return "eposta_only"


@router.get("/accounting")
def accounting_dashboard(
    admin=Depends(_require_jwt),
    db: Session = Depends(get_db),
    date_from: Optional[str] = Query(None, description="ISO date YYYY-MM-DD (filtre başı, UTC gün)"),
    date_to: Optional[str] = Query(None, description="ISO date YYYY-MM-DD (dahil, UTC gün sonu)"),
    content_id: Optional[str] = Query(None),
    payment_status: Optional[str] = Query(None),
    orders_limit: int = Query(300, ge=1, le=1000),
    orders_offset: int = Query(0, ge=0),
    funnel_days: int = Query(30, ge=1, le=90),
):
    """
    Özet kartlar, sipariş listesi (sayfalı), ürün bazlı gelir, tahsilat özeti, funnel köprüsü.
    """
    _ = admin
    now = _utc_now()
    today0 = _day_start(now)
    tomorrow0 = today0 + timedelta(days=1)
    month0 = _month_start(now)

    # Filtre aralığı (sipariş tablosu + özet tekrarları)
    if date_from:
        try:
            df = datetime.fromisoformat(date_from[:10]).replace(tzinfo=timezone.utc)
            range_start = _day_start(df)
        except Exception:
            range_start = month0
    else:
        range_start = month0
    if date_to:
        try:
            dt = datetime.fromisoformat(date_to[:10]).replace(tzinfo=timezone.utc)
            range_end = _day_start(dt) + timedelta(days=1)
        except Exception:
            range_end = tomorrow0
    else:
        range_end = tomorrow0 + timedelta(days=3650)

    def scalar(sql: str, params: dict):
        return db.execute(sa_text(sql), params).scalar()

    def mappings(sql: str, params: dict):
        return db.execute(sa_text(sql), params).mappings().all()

    # ── Üst özet: bugün / bu ay
    sales_today = int(
        scalar(
            """SELECT COUNT(*) FROM shopier_purchases
               WHERE status = 'completed' AND created_at >= :a AND created_at < :b""",
            {"a": today0, "b": tomorrow0},
        )
        or 0
    )
    revenue_today = float(
        scalar(
            """SELECT COALESCE(SUM(amount), 0) FROM shopier_purchases
               WHERE status = 'completed' AND created_at >= :a AND created_at < :b""",
            {"a": today0, "b": tomorrow0},
        )
        or 0
    )

    sales_month = int(
        scalar(
            """SELECT COUNT(*) FROM shopier_purchases
               WHERE status = 'completed' AND created_at >= :a AND created_at < :b""",
            {"a": month0, "b": tomorrow0},
        )
        or 0
    )
    revenue_month = float(
        scalar(
            """SELECT COALESCE(SUM(amount), 0) FROM shopier_purchases
               WHERE status = 'completed' AND created_at >= :a AND created_at < :b""",
            {"a": month0, "b": tomorrow0},
        )
        or 0
    )

    avg_basket_month = float(
        scalar(
            """SELECT COALESCE(AVG(amount), 0) FROM shopier_purchases
               WHERE status = 'completed' AND created_at >= :a AND created_at < :b""",
            {"a": month0, "b": tomorrow0},
        )
        or 0
    )

    top_row = mappings(
        """
        SELECT COALESCE(NULLIF(TRIM(product_name), ''), content_id) AS label,
               COUNT(*) AS cnt, SUM(amount) AS rev
        FROM shopier_purchases
        WHERE status = 'completed' AND created_at >= :a AND created_at < :b
        GROUP BY 1 ORDER BY rev DESC LIMIT 1
        """,
        {"a": month0, "b": tomorrow0},
    )
    top_product = (
        {"label": top_row[0]["label"], "revenue": float(top_row[0]["rev"] or 0), "count": int(top_row[0]["cnt"])}
        if top_row
        else None
    )

    pending_cnt = int(
        scalar(
            """
            SELECT COUNT(*) FROM shopier_purchases
            WHERE LOWER(COALESCE(payment_status, '')) IN ('unpaid', 'pending', 'beklemede')
               OR (status IS NOT NULL AND status <> 'completed')
            """,
            {},
        )
        or 0
    )
    pending_amount = float(
        scalar(
            """
            SELECT COALESCE(SUM(amount), 0) FROM shopier_purchases
            WHERE LOWER(COALESCE(payment_status, '')) IN ('unpaid', 'pending', 'beklemede')
               OR (status IS NOT NULL AND status <> 'completed')
            """,
            {},
        )
        or 0
    )

    collected_all = float(
        scalar(
            """SELECT COALESCE(SUM(amount), 0) FROM shopier_purchases WHERE status = 'completed'""",
            {},
        )
        or 0
    )

    # ── Sipariş tablosu (filtreli)
    conds = ["1=1"]
    pparams: dict = {
        "rs": range_start,
        "re": range_end,
        "lim": orders_limit,
        "off": orders_offset,
    }
    conds.append("created_at >= :rs AND created_at < :re")
    if content_id and content_id.strip():
        conds.append("content_id = :cid")
        pparams["cid"] = content_id.strip()
    if payment_status and payment_status.strip():
        conds.append("LOWER(COALESCE(payment_status, '')) = :ps")
        pparams["ps"] = payment_status.strip().lower()

    where_sql = " AND ".join(conds)
    total_orders_filtered = int(
        scalar(
            f"SELECT COUNT(*) FROM shopier_purchases WHERE {where_sql}",
            {k: v for k, v in pparams.items() if k not in ("lim", "off")},
        )
        or 0
    )

    order_rows = mappings(
        f"""
        SELECT id, shopier_order_id, order_number, email, product_name, content_id,
               amount, currency, payment_status, status, device_fp, user_id, created_at
        FROM shopier_purchases
        WHERE {where_sql}
        ORDER BY created_at DESC
        LIMIT :lim OFFSET :off
        """,
        pparams,
    )

    orders_out = []
    for r in order_rows:
        orders_out.append(
            {
                "id": r["id"],
                "ledger_source": "shopier",
                "order_id": r["shopier_order_id"],
                "order_number": r["order_number"],
                "email": r["email"],
                "product_name": r["product_name"],
                "content_id": r["content_id"],
                "amount": float(r["amount"] or 0),
                "currency": r["currency"] or "TRY",
                "payment_status": r["payment_status"],
                "status": r["status"],
                "unlock_status": _unlock_status(r["device_fp"], r["user_id"]),
                "created_at": str(r["created_at"]) if r["created_at"] else None,
            }
        )

    # ── Ürün bazlı gelir (filtreli aralık)
    by_product = mappings(
        f"""
        SELECT content_id,
               COALESCE(NULLIF(TRIM(product_name), ''), content_id) AS display_name,
               COUNT(*) AS sale_count,
               COALESCE(SUM(amount), 0) AS total_revenue,
               COALESCE(AVG(amount), 0) AS avg_revenue,
               MAX(created_at) AS last_sale_at
        FROM shopier_purchases
        WHERE status = 'completed' AND {where_sql}
        GROUP BY content_id, display_name
        ORDER BY total_revenue DESC
        """,
        {k: v for k, v in pparams.items() if k not in ("lim", "off")},
    )
    by_product_out = [
        {
            "content_id": r["content_id"],
            "display_name": r["display_name"],
            "sale_count": int(r["sale_count"]),
            "total_revenue": float(r["total_revenue"] or 0),
            "avg_revenue": float(r["avg_revenue"] or 0),
            "last_sale_at": str(r["last_sale_at"]) if r["last_sale_at"] else None,
        }
        for r in by_product
    ]

    # ── Funnel + satış köprüsü
    since_f = now - timedelta(days=funnel_days)
    fe_counts: dict[str, int] = {}
    try:
        rows_fe = mappings(
            """
            SELECT event_type, COUNT(*) AS c FROM funnel_events
            WHERE created_at >= :s AND event_type IN (
                'role_page_view', 'role_form_submit', 'role_shopier_redirect', 'role_unlock_success',
                'ankod_page_view', 'ankod_shopier_redirect', 'ankod_unlock_success'
            )
            GROUP BY event_type
            """,
            {"s": since_f},
        )
        fe_counts = {r["event_type"]: int(r["c"]) for r in rows_fe}
    except Exception:
        fe_counts = {}

    purchases_window = int(
        scalar(
            """SELECT COUNT(*) FROM shopier_purchases
               WHERE status = 'completed' AND created_at >= :s""",
            {"s": since_f},
        )
        or 0
    )
    role_purchases = int(
        scalar(
            """SELECT COUNT(*) FROM shopier_purchases
               WHERE status = 'completed' AND content_id = 'role_unlock' AND created_at >= :s""",
            {"s": since_f},
        )
        or 0
    )
    ankod_purchases = int(
        scalar(
            """SELECT COUNT(*) FROM shopier_purchases
               WHERE status = 'completed' AND content_id IN ('ankod_unlock', 'subconscious_unlock')
               AND created_at >= :s""",
            {"s": since_f},
        )
        or 0
    )

    sr = fe_counts.get("role_shopier_redirect", 0) or 0
    ar = fe_counts.get("ankod_shopier_redirect", 0) or 0

    def _pct(num: int, den: int) -> float:
        return round((num / den) * 100, 2) if den > 0 else 0.0

    funnel_bridge = {
        "period_days": funnel_days,
        "funnel_counts": fe_counts,
        "page_views_role": fe_counts.get("role_page_view", 0),
        "form_submit_role": fe_counts.get("role_form_submit", 0),
        "shopier_redirect_role": sr,
        "unlock_success_role": fe_counts.get("role_unlock_success", 0),
        "shopier_redirect_ankod": ar,
        "purchases_total_window": purchases_window,
        "purchases_role_unlock": role_purchases,
        "purchases_ankod_family": ankod_purchases,
        "conversion_role_redirect_to_purchase": _pct(role_purchases, sr),
        "conversion_ankod_redirect_to_purchase": _pct(ankod_purchases, ar),
        "note": "Funnel olayları istemciden; satın alma shopier_purchases webhook kaydıdır.",
    }

    # ── page_views (genel)
    pv_total = 0
    try:
        pv_total = int(
            scalar("SELECT COUNT(*) FROM page_views WHERE created_at >= :s", {"s": since_f}) or 0
        )
    except Exception:
        pass
    funnel_bridge["page_views_total_site"] = pv_total

    customer_emails = _union_customer_emails(db, 500)

    havale_raw = _fetch_havale_rows(db, range_start, range_end, content_id, 500)
    havale_orders = [
        {
            "id": r["id"],
            "ledger_source": "bank_transfer",
            "order_id": f"bank-transfer-{r['id']}",
            "order_number": r["transfer_code"],
            "email": r["email"],
            "product_name": r["product_name"],
            "content_id": r["content_id"],
            "amount": float(r["amount"] or 0),
            "currency": "TRY",
            "payment_status": r["status"],
            "status": "bank_transfer",
            "unlock_status": "havale",
            "created_at": str(r["created_at"]) if r["created_at"] else None,
        }
        for r in havale_raw
    ]

    return {
        "summary": {
            "sales_today_count": sales_today,
            "revenue_today": round(revenue_today, 2),
            "sales_month_count": sales_month,
            "revenue_month": round(revenue_month, 2),
            "pending_collection_count": pending_cnt,
            "pending_collection_amount": round(pending_amount, 2),
            "top_product": top_product,
            "avg_basket_month": round(avg_basket_month, 2),
            "collected_revenue_all_time": round(collected_all, 2),
            "refunds_note": "İade/iptal shopier_purchases üzerinde ayrı kolon yok; Shopier panelinden takip edin.",
        },
        "collections": {
            "collected_completed_total_try": round(collected_all, 2),
            "pending_rows_try": round(pending_amount, 2),
            "pending_rows_count": pending_cnt,
        },
        "filters": {
            "date_from": date_from,
            "date_to": date_to,
            "content_id": content_id,
            "payment_status": payment_status,
        },
        "orders": orders_out,
        "orders_total": total_orders_filtered,
        "by_product": by_product_out,
        "funnel_revenue": funnel_bridge,
        "customer_emails": customer_emails,
        "havale_orders": havale_orders,
    }


@router.get("/accounting/customer")
def accounting_customer(
    email: str = Query(..., min_length=3),
    admin=Depends(_require_jwt),
    db: Session = Depends(get_db),
):
    _ = admin
    em = email.strip().lower()
    rows_sp = db.execute(
        sa_text("""
        SELECT content_id, product_name, amount, currency, payment_status, status,
               created_at, shopier_order_id, 'shopier' AS ledger_source
        FROM shopier_purchases
        WHERE LOWER(TRIM(email)) = :e
        """),
        {"e": em},
    ).mappings().all()
    rows_bt: list = []
    try:
        rows_bt = db.execute(
            sa_text("""
            SELECT content_id, product_name, amount, 'TRY' AS currency, status AS payment_status,
                   status, created_at,
                   ('bank-transfer-' || CAST(id AS TEXT)) AS shopier_order_id,
                   'bank_transfer' AS ledger_source
            FROM bank_transfer_requests
            WHERE LOWER(TRIM(email)) = :e
            """),
            {"e": em},
        ).mappings().all()
    except Exception:
        rows_bt = []

    merged = sorted(
        [*rows_sp, *rows_bt],
        key=lambda r: str(r.get("created_at") or ""),
    )
    total = sum(float(r["amount"] or 0) for r in merged)
    first_at = str(merged[0]["created_at"]) if merged else None
    last_at = str(merged[-1]["created_at"]) if merged else None

    contents = []
    seen = set()
    for r in merged:
        cid = r["content_id"]
        if cid and cid not in seen:
            seen.add(cid)
            contents.append(cid)

    return {
        "email": em,
        "purchase_count": len(merged),
        "total_spent": round(total, 2),
        "first_purchase_at": first_at,
        "last_purchase_at": last_at,
        "content_ids": contents,
        "purchases": [
            {
                "content_id": r["content_id"],
                "product_name": r["product_name"],
                "amount": float(r["amount"] or 0),
                "currency": r["currency"] or "TRY",
                "payment_status": r["payment_status"],
                "status": r["status"],
                "order_id": r["shopier_order_id"],
                "ledger_source": r.get("ledger_source"),
                "created_at": str(r["created_at"]) if r["created_at"] else None,
            }
            for r in merged
        ],
    }


@router.get("/accounting/export.csv")
def accounting_export_csv(
    admin=Depends(_require_jwt),
    db: Session = Depends(get_db),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    content_id: Optional[str] = Query(None),
    payment_status: Optional[str] = Query(None),
):
    _ = admin
    now = _utc_now()
    month0 = _month_start(now)
    tomorrow0 = _day_start(now) + timedelta(days=1)

    if date_from:
        try:
            df = datetime.fromisoformat(date_from[:10]).replace(tzinfo=timezone.utc)
            range_start = _day_start(df)
        except Exception:
            range_start = month0
    else:
        range_start = month0
    if date_to:
        try:
            dt = datetime.fromisoformat(date_to[:10]).replace(tzinfo=timezone.utc)
            range_end = _day_start(dt) + timedelta(days=1)
        except Exception:
            range_end = tomorrow0
    else:
        range_end = tomorrow0

    conds = ["created_at >= :rs AND created_at < :re"]
    params: dict = {"rs": range_start, "re": range_end}
    if content_id and content_id.strip():
        conds.append("content_id = :cid")
        params["cid"] = content_id.strip()
    if payment_status and payment_status.strip():
        conds.append("LOWER(COALESCE(payment_status, '')) = :ps")
        params["ps"] = payment_status.strip().lower()
    where_sql = " AND ".join(conds)

    rows = db.execute(
        sa_text(f"""
        SELECT shopier_order_id, order_number, email, product_name, content_id,
               amount, currency, payment_status, status, device_fp, user_id, created_at,
               'shopier' AS ledger_source
        FROM shopier_purchases
        WHERE {where_sql}
        ORDER BY created_at DESC
        LIMIT 5000
        """),
        params,
    ).mappings().all()

    rows_h: list = []
    try:
        h_conds = ["created_at >= :rs AND created_at < :re"]
        hp = {"rs": range_start, "re": range_end}
        if content_id and content_id.strip():
            h_conds.append("content_id = :cid")
            hp["cid"] = content_id.strip()
        hw = " AND ".join(h_conds)
        rows_h = db.execute(
            sa_text(f"""
            SELECT ('bank-transfer-' || CAST(id AS TEXT)) AS shopier_order_id,
                   transfer_code AS order_number, email, product_name, content_id,
                   amount, 'TRY' AS currency, status AS payment_status, status AS status,
                   NULL AS device_fp, NULL AS user_id, created_at,
                   'bank_transfer' AS ledger_source
            FROM bank_transfer_requests
            WHERE {hw}
            ORDER BY created_at DESC
            LIMIT 5000
            """),
            hp,
        ).mappings().all()
    except Exception:
        rows_h = []

    merged_csv = sorted(
        [*rows, *rows_h],
        key=lambda r: str(r.get("created_at") or ""),
        reverse=True,
    )[:5000]

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "ledger_source",
            "order_id",
            "order_number",
            "email",
            "product_name",
            "content_id",
            "amount",
            "currency",
            "payment_status",
            "status",
            "unlock_status",
            "created_at",
        ]
    )
    for r in merged_csv:
        w.writerow(
            [
                r.get("ledger_source") or "shopier",
                r["shopier_order_id"],
                r["order_number"],
                r["email"],
                r["product_name"],
                r["content_id"],
                r["amount"],
                r["currency"],
                r["payment_status"],
                r["status"],
                _unlock_status(r["device_fp"], r["user_id"]),
                str(r["created_at"]) if r["created_at"] else "",
            ]
        )

    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="sanri_muhasebe_export.csv"',
        },
    )

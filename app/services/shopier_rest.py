"""
Shopier REST API — Personal Access Token (SHOPIER_PAT).

Dokümantasyon: https://developer.shopier.com/ — Bearer token.
Varsayılan taban: https://api.shopier.com/v1
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

import httpx

logger = logging.getLogger("shopier")

# Shopier: POST /webhooks — https://developer.shopier.com/reference/post-webhooks
VALID_WEBHOOK_EVENTS = frozenset(
    {
        "order.addressUpdated",
        "order.created",
        "order.fulfilled",
        "product.created",
        "product.updated",
        "refund.requested",
        "refund.updated",
    }
)

SHOPIER_PAT = os.getenv("SHOPIER_PAT", "").strip()
SHOPIER_API_BASE = os.getenv("SHOPIER_API_BASE", "https://api.shopier.com/v1").rstrip("/")
DEFAULT_TIMEOUT = 25.0


def _headers() -> Optional[dict[str, str]]:
    if not SHOPIER_PAT:
        return None
    return {
        "Authorization": f"Bearer {SHOPIER_PAT}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _unwrap_order_payload(data: Any) -> Optional[dict[str, Any]]:
    if data is None:
        return None
    if isinstance(data, dict):
        if "data" in data and isinstance(data["data"], dict):
            inner = data["data"]
            if "lineItems" in inner or "paymentStatus" in inner:
                return inner
        if "order" in data and isinstance(data["order"], dict):
            return data["order"]
        if "lineItems" in data or "paymentStatus" in data or "id" in data:
            return data
    return None


async def get_shopier_order(order_id: str) -> Optional[dict[str, Any]]:
    """
    Tek siparişi Shopier API’den çeker (doğrulama / webhook tamamlama).
    """
    h = _headers()
    oid = str(order_id or "").strip()
    if not h or not oid:
        if not SHOPIER_PAT:
            logger.warning("Shopier REST: SHOPIER_PAT missing, skip order fetch")
        return None
    url = f"{SHOPIER_API_BASE}/orders/{oid}"
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            r = await client.get(url, headers=h)
        if r.status_code == 404:
            logger.info("Shopier REST: order not found id=%s", oid)
            return None
        if not r.is_success:
            logger.warning(
                "Shopier REST: get order failed id=%s status=%s body=%s",
                oid,
                r.status_code,
                (r.text or "")[:500],
            )
            return None
        body = r.json()
        order = _unwrap_order_payload(body)
        if not order:
            logger.warning("Shopier REST: unexpected order JSON shape id=%s", oid)
        return order
    except httpx.RequestError as e:
        logger.warning("Shopier REST: request error id=%s err=%s", oid, e)
        return None
    except Exception as e:
        logger.exception("Shopier REST: unexpected error id=%s err=%s", oid, e)
        return None


async def get_shopier_orders(
    limit: int = 50,
    offset: int = 0,
    extra_params: Optional[dict[str, str]] = None,
) -> list[dict[str, Any]]:
    """
    Sipariş listesi (admin / reconciler). Shopier query parametreleri sürüme göre değişebilir.
    """
    h = _headers()
    if not h:
        logger.warning("Shopier REST: SHOPIER_PAT missing, skip orders list")
        return []
    params: dict[str, str] = {"limit": str(min(max(limit, 1), 100)), "offset": str(max(offset, 0))}
    if extra_params:
        params.update({k: str(v) for k, v in extra_params.items()})
    url = f"{SHOPIER_API_BASE}/orders"
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            r = await client.get(url, headers=h, params=params)
        if not r.is_success:
            logger.warning(
                "Shopier REST: list orders failed status=%s body=%s",
                r.status_code,
                (r.text or "")[:500],
            )
            return []
        body = r.json()
        if isinstance(body, list):
            return [x for x in body if isinstance(x, dict)]
        if isinstance(body, dict):
            for key in ("data", "orders", "items", "results"):
                chunk = body.get(key)
                if isinstance(chunk, list):
                    return [x for x in chunk if isinstance(x, dict)]
        return []
    except httpx.RequestError as e:
        logger.warning("Shopier REST: list orders request error err=%s", e)
        return []
    except Exception as e:
        logger.exception("Shopier REST: list orders unexpected err=%s", e)
        return []


def _unwrap_webhook_payload(data: Any) -> Optional[dict[str, Any]]:
    if data is None:
        return None
    if isinstance(data, dict):
        inner = data.get("data")
        if isinstance(inner, dict) and ("id" in inner or "event" in inner):
            return inner
        if "id" in data or "event" in data:
            return data
    return None


def _is_duplicate_webhook_error(status: int, body_text: str) -> bool:
    t = (body_text or "").lower()
    if status == 409:
        return True
    if status == 422 and any(k in t for k in ("duplicate", "already", "exist", "unique")):
        return True
    if status == 400 and any(
        x in t for x in ("duplicate", "already exists", "already registered", "same url")
    ):
        return True
    return False


async def register_shopier_webhook(
    url: str,
    event: str = "order.created",
) -> dict[str, Any]:
    """
    Shopier API: POST /webhooks — Bearer SHOPIER_PAT.
    Başarıda Shopier genelde signing token döner (yalnızca create yanıtında); loglanır.
    """
    h = _headers()
    ev = (event or "").strip()
    target = (url or "").strip()
    if not h:
        logger.error("Shopier webhooks: SHOPIER_PAT missing")
        return {
            "ok": False,
            "error": "pat_missing",
            "message": "SHOPIER_PAT is not set",
        }
    if not target:
        return {"ok": False, "error": "invalid_url", "message": "Webhook target URL is empty"}
    if ev not in VALID_WEBHOOK_EVENTS:
        return {
            "ok": False,
            "error": "invalid_event",
            "message": f"event must be one of: {sorted(VALID_WEBHOOK_EVENTS)}",
        }

    api_url = f"{SHOPIER_API_BASE}/webhooks"
    payload = {"event": ev, "url": target}

    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            r = await client.post(api_url, headers=h, json=payload)
    except httpx.RequestError as e:
        logger.exception("Shopier webhooks: network error registering url=%s err=%s", target, e)
        return {
            "ok": False,
            "error": "network_error",
            "message": str(e),
        }

    text = (r.text or "")[:2000]
    logger.info(
        "Shopier webhooks: POST /webhooks status=%s event=%s url=%s body_head=%s",
        r.status_code,
        ev,
        target,
        text[:500],
    )

    if r.status_code in (401, 403):
        return {
            "ok": False,
            "error": "token_error",
            "status_code": r.status_code,
            "message": "Shopier rejected the PAT (401/403)",
            "shopier_body": text,
        }

    if _is_duplicate_webhook_error(r.status_code, text):
        return {
            "ok": False,
            "error": "duplicate_webhook",
            "status_code": r.status_code,
            "message": "Webhook may already exist for this event/URL",
            "shopier_body": text,
        }

    if not r.is_success:
        return {
            "ok": False,
            "error": "shopier_error",
            "status_code": r.status_code,
            "message": "Shopier API returned an error",
            "shopier_body": text,
        }

    try:
        raw = r.json()
    except Exception:
        logger.warning("Shopier webhooks: success but non-JSON body")
        return {
            "ok": True,
            "error": None,
            "webhook": None,
            "raw_text": text,
        }

    wh = _unwrap_webhook_payload(raw) or (raw if isinstance(raw, dict) else None)
    token_hint = None
    if isinstance(wh, dict) and wh.get("token"):
        tok = str(wh["token"])
        token_hint = f"{tok[:6]}…" if len(tok) > 6 else "(short)"
        logger.warning(
            "Shopier webhooks: signing token returned — set SHOPIER_WEBHOOK_TOKEN in env for HMAC verification (full value only in Shopier response / dashboard)"
        )

    return {
        "ok": True,
        "error": None,
        "webhook": wh,
        "token_hint": token_hint,
    }


async def list_shopier_webhooks(
    limit: int = 50,
    page: int = 1,
    sort: str = "asc",
) -> tuple[list[dict[str, Any]], Optional[str]]:
    """
    GET /webhooks — kayıtları doğrulamak için.
    Returns (list, error_message).
    """
    h = _headers()
    if not h:
        return [], "SHOPIER_PAT is not set"
    params = {
        "limit": str(min(max(limit, 1), 50)),
        "page": str(max(page, 1)),
        "sort": sort if sort in ("asc", "desc") else "asc",
    }
    url = f"{SHOPIER_API_BASE}/webhooks"
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            r = await client.get(url, headers=h, params=params)
    except httpx.RequestError as e:
        logger.warning("Shopier webhooks: list network err=%s", e)
        return [], f"network_error: {e}"

    text = (r.text or "")[:2000]
    if not r.is_success:
        logger.warning("Shopier webhooks: list failed status=%s body=%s", r.status_code, text[:500])
        return [], f"http_{r.status_code}: {text[:200]}"

    try:
        body = r.json()
    except Exception:
        return [], "invalid_json"

    if isinstance(body, list):
        return [x for x in body if isinstance(x, dict)], None
    if isinstance(body, dict):
        for key in ("data", "webhooks", "items", "results"):
            chunk = body.get(key)
            if isinstance(chunk, list):
                return [x for x in chunk if isinstance(x, dict)], None
    return [], None

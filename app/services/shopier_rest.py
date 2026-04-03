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

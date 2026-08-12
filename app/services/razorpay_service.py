"""Razorpay Orders API + payment signature verification.

Deliberately a thin HTTP client rather than the vendor SDK: we need exactly two
calls, and this keeps the dependency surface (and the failure modes) small.
"""

import base64
import hashlib
import hmac
import logging
from typing import Any, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

API_BASE = "https://api.razorpay.com/v1"


class RazorpayError(RuntimeError):
    pass


def is_configured() -> bool:
    return bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET)


def _auth_header() -> dict[str, str]:
    raw = f"{settings.RAZORPAY_KEY_ID}:{settings.RAZORPAY_KEY_SECRET}".encode()
    return {"Authorization": f"Basic {base64.b64encode(raw).decode()}"}


async def create_order(amount: int, currency: str, receipt: str, notes: dict[str, Any]) -> dict[str, Any]:
    """Create an order. `amount` is in the currency's smallest unit (paise)."""
    if not is_configured():
        raise RazorpayError("Razorpay is not configured on the server.")
    payload = {
        "amount": amount,
        "currency": currency,
        "receipt": receipt[:40],
        "notes": {k: str(v) for k, v in notes.items() if v is not None},
        # We only ever grant access after our own verify step, so let Razorpay
        # capture automatically rather than leaving money authorised-but-unclaimed.
        "payment_capture": 1,
    }
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(f"{API_BASE}/orders", json=payload, headers=_auth_header())
    if r.status_code >= 400:
        logger.error("Razorpay order failed (%s): %s", r.status_code, r.text)
        raise RazorpayError("Could not start the payment. Please try again.")
    return r.json()


async def fetch_payment(payment_id: str) -> Optional[dict[str, Any]]:
    """Payment details for the record. Never gates access on its own."""
    if not is_configured():
        return None
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(f"{API_BASE}/payments/{payment_id}", headers=_auth_header())
        return r.json() if r.status_code < 400 else None
    except Exception:
        logger.warning("Could not fetch Razorpay payment %s", payment_id, exc_info=True)
        return None


def verify_signature(order_id: str, payment_id: str, signature: str) -> bool:
    """HMAC-SHA256 of "order_id|payment_id" keyed with the API secret.

    This is the only thing that decides whether a payment is real, so it is
    compared in constant time and never short-circuits on a missing secret.
    """
    if not settings.RAZORPAY_KEY_SECRET:
        return False
    expected = hmac.new(
        settings.RAZORPAY_KEY_SECRET.encode(),
        f"{order_id}|{payment_id}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, (signature or "").strip())

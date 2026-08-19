"""Push notifications through Expo's push service.

Expo's endpoint is one HTTP call for both platforms and needs no service-account
file on the server, which is the whole reason it is used here rather than
talking to FCM and APNs separately.

Delivery is best-effort by design: a tip that reaches most phones is worth more
than an admin request that fails because one device is stale.

Expo answers in two stages and both matter. The immediate reply is a *ticket* —
"accepted for delivery", not "delivered" — and the real outcome arrives later as
a *receipt*. A device that has uninstalled the app very often passes the ticket
stage and only fails at the receipt, so a service that reads tickets alone
never learns its token table is full of ghosts. Tickets are therefore parked
here and reaped on the next send.
"""

import logging
from datetime import timedelta
from typing import Any, Iterable, Optional

import httpx
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.schemas.common import now_utc

logger = logging.getLogger(__name__)

SEND_URL = "https://exp.host/--/api/v2/push/send"
RECEIPT_URL = "https://exp.host/--/api/v2/push/getReceipts"
TOKENS = "push_tokens"
TICKETS = "push_tickets"
CHUNK = 100          # Expo's documented maximum per request

# Errors that mean the token will never work again. Anything else — a rate
# limit, a transient FCM fault — is left alone so a good device is not dropped
# over one bad night.
FATAL = {"DeviceNotRegistered", "InvalidCredentials", "MismatchSenderId"}

# Expo asks for a delay before receipts are read; they are usually ready well
# inside this, and anything older is certainly resolved.
RECEIPT_DELAY_S = 60


def _chunks(items: list, size: int = CHUNK) -> Iterable[list]:
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _looks_like_expo_token(token: str) -> bool:
    """Expo only accepts its own token format; anything else is a wasted slot
    in every future send."""
    return token.startswith("ExponentPushToken[") or token.startswith("ExpoPushToken[")


async def all_tokens(db: AsyncIOMotorDatabase) -> list[str]:
    rows = await db[TOKENS].find({"is_active": True}).to_list(length=100_000)
    return [r["token"] for r in rows if r.get("token")]


async def _drop(db: AsyncIOMotorDatabase, tokens: list[str], why: str) -> None:
    """A device that has uninstalled or reinstalled will never come back on the
    same token, so stop carrying it."""
    if not tokens:
        return
    await db[TOKENS].delete_many({"token": {"$in": tokens}})
    logger.info("Dropped %d dead push tokens (%s).", len(tokens), why)


async def reap_receipts(db: AsyncIOMotorDatabase) -> dict[str, int]:
    """Read the outcome of earlier sends and clear out the tokens that failed.

    Run before each send rather than on a schedule: the only thing that cares
    about a clean token table is the next send, and this keeps the service free
    of a background worker.
    """
    cutoff = now_utc() - timedelta(seconds=RECEIPT_DELAY_S)
    rows = await db[TICKETS].find({"created_at": {"$lte": cutoff}}).to_list(length=10_000)
    if not rows:
        return {"checked": 0, "dropped": 0}

    by_id = {r["ticket_id"]: r["token"] for r in rows if r.get("ticket_id")}
    dead: list[str] = []

    async with httpx.AsyncClient(timeout=30) as client:
        for group in _chunks(list(by_id.keys()), 300):
            try:
                r = await client.post(RECEIPT_URL, json={"ids": group},
                                      headers={"Accept": "application/json"})
                receipts = (r.json() or {}).get("data") or {}
            except Exception:
                logger.warning("Could not read push receipts", exc_info=True)
                continue
            for ticket_id, receipt in receipts.items():
                if receipt.get("status") == "ok":
                    continue
                error = (receipt.get("details") or {}).get("error")
                logger.info("Push receipt failed: %s — %s", error, receipt.get("message"))
                if error in FATAL and ticket_id in by_id:
                    dead.append(by_id[ticket_id])

    await _drop(db, dead, "receipt")
    await db[TICKETS].delete_many({"_id": {"$in": [r["_id"] for r in rows]}})
    return {"checked": len(rows), "dropped": len(dead)}


async def send_to_all(
    db: AsyncIOMotorDatabase,
    *,
    title: str,
    body: str,
    data: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Fan a notification out to every registered device.

    Returns what actually happened rather than just succeeding, so the admin
    panel can say "sent to 412 devices" and mean it — and, when it cannot, say
    which error stopped it.
    """
    await reap_receipts(db)

    tokens = await all_tokens(db)
    if not tokens:
        return {"sent": 0, "failed": 0, "devices": 0, "errors": {}}

    # A token that is not Expo's own is rejected on every send forever; drop it
    # here rather than paying for it each time.
    malformed = [t for t in tokens if not _looks_like_expo_token(t)]
    if malformed:
        await _drop(db, malformed, "malformed")
        tokens = [t for t in tokens if _looks_like_expo_token(t)]

    sent = failed = 0
    dead: list[str] = []
    errors: dict[str, int] = {}
    pending: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=30) as client:
        for group in _chunks(tokens):
            messages = [{
                "to": token,
                "title": title,
                "body": body,
                "sound": "default",
                "channelId": "tips",
                "priority": "high",
                "data": data or {},
            } for token in group]
            try:
                r = await client.post(SEND_URL, json=messages, headers={"Accept": "application/json"})
                payload = r.json() if r.status_code < 500 else {}
            except Exception:
                logger.warning("Push chunk failed to send", exc_info=True)
                failed += len(group)
                errors["Unreachable"] = errors.get("Unreachable", 0) + len(group)
                continue

            for token, ticket in zip(group, payload.get("data", []) or []):
                if ticket.get("status") == "ok":
                    sent += 1
                    # Park the ticket; the receipt is where a stale device shows.
                    if ticket.get("id"):
                        pending.append({"ticket_id": ticket["id"], "token": token,
                                        "created_at": now_utc()})
                    continue

                failed += 1
                error = (ticket.get("details") or {}).get("error") or "Unknown"
                errors[error] = errors.get(error, 0) + 1
                logger.info("Push ticket failed: %s — %s", error, ticket.get("message"))
                if error in FATAL:
                    dead.append(token)

    if pending:
        await db[TICKETS].insert_many(pending)
    await _drop(db, dead, "ticket")

    if failed:
        logger.warning("Push: %d sent, %d failed of %d devices. Errors: %s",
                       sent, failed, len(tokens), errors)
    return {"sent": sent, "failed": failed, "devices": len(tokens), "errors": errors}

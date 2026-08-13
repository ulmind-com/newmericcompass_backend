"""Push notifications through Expo's push service.

Expo's endpoint is one HTTP call for both platforms and needs no service-account
file on the server, which is the whole reason it is used here rather than
talking to FCM and APNs separately.

Delivery is best-effort by design: a tip that reaches most phones is worth more
than an admin request that fails because one device is stale.
"""

import logging
from typing import Any, Iterable, Optional

import httpx
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

EXPO_URL = "https://exp.host/--/api/v2/push/send"
TOKENS = "push_tokens"
CHUNK = 100          # Expo's documented maximum per request


def _chunks(items: list[str]) -> Iterable[list[str]]:
    for i in range(0, len(items), CHUNK):
        yield items[i:i + CHUNK]


async def all_tokens(db: AsyncIOMotorDatabase) -> list[str]:
    rows = await db[TOKENS].find({"is_active": True}).to_list(length=100_000)
    return [r["token"] for r in rows if r.get("token")]


async def _drop(db: AsyncIOMotorDatabase, tokens: list[str]) -> None:
    """A device that has uninstalled or reinstalled will never come back on the
    same token, so stop carrying it."""
    if not tokens:
        return
    await db[TOKENS].delete_many({"token": {"$in": tokens}})
    logger.info("Dropped %d dead push tokens.", len(tokens))


async def send_to_all(
    db: AsyncIOMotorDatabase,
    *,
    title: str,
    body: str,
    data: Optional[dict[str, Any]] = None,
) -> dict[str, int]:
    """Fan a notification out to every registered device.

    Returns what actually happened rather than just succeeding, so the admin
    panel can say "sent to 412 devices" and mean it.
    """
    tokens = await all_tokens(db)
    if not tokens:
        return {"sent": 0, "failed": 0, "devices": 0}

    sent = failed = 0
    dead: list[str] = []

    async with httpx.AsyncClient(timeout=30) as client:
        for group in _chunks(tokens):
            messages = [{
                "to": token,
                "title": title,
                "body": body,
                "sound": "default",
                "channelId": "tips",
                "data": data or {},
            } for token in group]
            try:
                r = await client.post(EXPO_URL, json=messages, headers={"Accept": "application/json"})
                payload = r.json() if r.status_code < 500 else {}
            except Exception:
                logger.warning("Push chunk failed to send", exc_info=True)
                failed += len(group)
                continue

            for token, ticket in zip(group, payload.get("data", []) or []):
                if ticket.get("status") == "ok":
                    sent += 1
                    continue
                failed += 1
                if (ticket.get("details") or {}).get("error") == "DeviceNotRegistered":
                    dead.append(token)

    await _drop(db, dead)
    return {"sent": sent, "failed": failed, "devices": len(tokens)}

"""Device registration for push notifications.

Open on purpose: a daily tip is worth sending to everyone who installed the
app, not only to the people who happened to sign in. The token is the identity
here — an email is recorded alongside it when the app knows one, but only so
the admin can see who a device belongs to.
"""

from typing import Optional

from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.core.database import get_database
from app.core.security import TokenData, get_current_admin
from app.schemas.common import now_utc
from app.services.push_service import TOKENS, reap_receipts

router = APIRouter()


class PushRegister(BaseModel):
    token: str
    platform: Optional[str] = None
    email: Optional[str] = None


@router.post("/register", status_code=204, summary="Register this device for notifications")
async def register(payload: PushRegister, db: AsyncIOMotorDatabase = Depends(get_database)):
    token = payload.token.strip()
    if not token:
        return
    # Keyed on the token so a reinstall or a second sign-in updates the same
    # row instead of creating a duplicate that gets notified twice.
    await db[TOKENS].update_one(
        {"token": token},
        {"$set": {
            "token": token,
            "platform": payload.platform,
            "email": (payload.email or "").strip().lower() or None,
            "is_active": True,
            "updated_at": now_utc(),
        },
         "$setOnInsert": {"created_at": now_utc()}},
        upsert=True,
    )


@router.post("/unregister", status_code=204, summary="Stop notifying this device")
async def unregister(payload: PushRegister, db: AsyncIOMotorDatabase = Depends(get_database)):
    await db[TOKENS].delete_one({"token": payload.token.strip()})


@router.get("/devices", summary="How many devices are actually reachable")
async def devices(db: AsyncIOMotorDatabase = Depends(get_database), _: TokenData = Depends(get_current_admin)):
    """What the token table looks like, so "10 failed" can be explained rather
    than guessed at."""
    rows = await db[TOKENS].find({"is_active": True}).to_list(length=100_000)
    by_platform: dict[str, int] = {}
    for r in rows:
        key = r.get("platform") or "unknown"
        by_platform[key] = by_platform.get(key, 0) + 1
    return {
        "devices": len(rows),
        "by_platform": by_platform,
        "signed_in": sum(1 for r in rows if r.get("email")),
    }


@router.post("/reap", summary="Read pending receipts and drop dead devices")
async def reap(db: AsyncIOMotorDatabase = Depends(get_database), _: TokenData = Depends(get_current_admin)):
    """Normally runs before every send; exposed so a stale table can be cleaned
    without having to notify anybody."""
    return await reap_receipts(db)

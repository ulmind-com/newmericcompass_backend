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
from app.schemas.common import now_utc
from app.services.push_service import TOKENS

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

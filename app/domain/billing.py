"""Entitlement rules: who may use a paid feature, and what using it costs them.

One entitlement row per (user, feature). Buying again extends the same row
rather than stacking duplicates, so "does this user have access" is always a
single lookup and never an ambiguous set.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.schemas.billing import Feature, FeatureAccess

PLANS = "plans"
ENTITLEMENTS = "entitlements"
PAYMENTS = "payments"
PAYMENT_ORDERS = "payment_orders"

ALL_FEATURES = [Feature.SUBMISSIONS, Feature.ANALYSIS, Feature.NEXUS]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    """Mongo hands back naive datetimes; treat them as the UTC they were stored as."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def normalize_email(email: Optional[str]) -> str:
    return (email or "").strip().lower()


def access_from(ent: Optional[dict[str, Any]], feature: Feature) -> FeatureAccess:
    """Turn a stored entitlement into the yes/no the app asks for."""
    if not ent or not ent.get("is_active", True):
        return FeatureAccess(feature=feature, allowed=False, reason="not_purchased")

    expires_at = _aware(ent.get("expires_at"))
    if expires_at and expires_at <= _now():
        return FeatureAccess(
            feature=feature, allowed=False, reason="expired",
            source=ent.get("source"), plan_name=ent.get("plan_name"), expires_at=expires_at,
        )

    quota_total = ent.get("quota_total")
    quota_used = int(ent.get("quota_used") or 0)
    quota_left = None if quota_total is None else max(0, quota_total - quota_used)
    if quota_left == 0:
        return FeatureAccess(
            feature=feature, allowed=False, reason="quota_exhausted",
            source=ent.get("source"), plan_name=ent.get("plan_name"), expires_at=expires_at,
            quota_total=quota_total, quota_used=quota_used, quota_left=0,
        )

    return FeatureAccess(
        feature=feature, allowed=True, source=ent.get("source"), plan_name=ent.get("plan_name"),
        expires_at=expires_at, quota_total=quota_total, quota_used=quota_used, quota_left=quota_left,
    )


async def get_entitlement(db: AsyncIOMotorDatabase, email: str, feature: str) -> Optional[dict]:
    return await db[ENTITLEMENTS].find_one({"user_email": normalize_email(email), "feature": feature})


async def access_map(db: AsyncIOMotorDatabase, email: str) -> list[FeatureAccess]:
    email = normalize_email(email)
    rows = await db[ENTITLEMENTS].find({"user_email": email}).to_list(length=50)
    by_feature = {r["feature"]: r for r in rows}
    return [access_from(by_feature.get(f.value), f) for f in ALL_FEATURES]


async def grant(
    db: AsyncIOMotorDatabase,
    *,
    email: str,
    feature: str,
    source: str,
    plan_slug: Optional[str] = None,
    plan_name: Optional[str] = None,
    duration_days: Optional[int] = None,
    submission_quota: Optional[int] = None,
    payment_id: Optional[str] = None,
    note: Optional[str] = None,
) -> dict:
    """Grant or extend access.

    Renewing before the current period ends adds to the remaining time rather
    than throwing it away, and a repeat purchase tops the quota up instead of
    resetting it. A lifetime or unlimited grant, once given, is never narrowed
    by a later smaller one.
    """
    email = normalize_email(email)
    now = _now()
    existing = await db[ENTITLEMENTS].find_one({"user_email": email, "feature": feature})

    live = existing and existing.get("is_active", True)
    current_expiry = _aware(existing.get("expires_at")) if live else None
    had_lifetime = bool(live and existing and existing.get("expires_at") is None)

    if duration_days is None:
        expires_at = None                                   # lifetime
    elif had_lifetime:
        expires_at = None                                   # never downgrade a lifetime grant
    else:
        base = current_expiry if current_expiry and current_expiry > now else now
        expires_at = base + timedelta(days=duration_days)

    had_unlimited = bool(live and existing and existing.get("quota_total") is None)
    if submission_quota is None or had_unlimited:
        quota_total = None                                  # unlimited
    else:
        quota_total = int(existing.get("quota_total") or 0) + submission_quota if live else submission_quota

    doc = {
        "user_email": email,
        "feature": feature,
        "plan_slug": plan_slug,
        "plan_name": plan_name,
        "source": source,
        "payment_id": payment_id,
        "expires_at": expires_at,
        "quota_total": quota_total,
        "is_active": True,
        "note": note,
        "updated_at": now,
    }
    await db[ENTITLEMENTS].update_one(
        {"user_email": email, "feature": feature},
        {"$set": doc, "$setOnInsert": {"granted_at": now, "quota_used": 0}},
        upsert=True,
    )
    return await db[ENTITLEMENTS].find_one({"user_email": email, "feature": feature})


async def consume(db: AsyncIOMotorDatabase, email: str, feature: str) -> bool:
    """Spend one unit of a metered feature.

    Guarded by the quota in the query itself, so two submissions racing each
    other can never both take the last one.
    """
    email = normalize_email(email)
    ent = await get_entitlement(db, email, feature)
    if not ent:
        return False
    if ent.get("quota_total") is None:
        return True                                          # unlimited: nothing to meter
    result = await db[ENTITLEMENTS].update_one(
        {
            "user_email": email,
            "feature": feature,
            "is_active": True,
            "$expr": {"$lt": [{"$ifNull": ["$quota_used", 0]}, "$quota_total"]},
        },
        {"$inc": {"quota_used": 1}},
    )
    return result.modified_count == 1

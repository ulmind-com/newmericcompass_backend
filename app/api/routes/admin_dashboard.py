from fastapi import APIRouter, Depends, Query
from typing import List
import asyncio

from app.schemas.common import now_utc

from app.core.security import get_current_active_admin, TokenData
from app.core.database import get_database
from app.schemas.admin import DashboardStats, PaginatedUsersResponse, UserOverview

router = APIRouter()

def _live_entitlement_query() -> dict:
    """An unlock that is actually in force right now."""
    return {
        "is_active": {"$ne": False},
        "$or": [{"expires_at": None}, {"expires_at": {"$gt": now_utc()}}],
    }


async def _paying_emails(db, emails: List[str] | None = None) -> set:
    """Who holds a live unlock — the only place that knows, whoever paid.

    ``users.is_premium`` is written false at sign-up and never again, so it
    said "Free" for everyone including the people who had paid. Entitlements
    are the record, so they are what this reads.
    """
    query = _live_entitlement_query()
    if emails is not None:
        query = {**query, "user_email": {"$in": [e.lower() for e in emails]}}
    rows = await db.entitlements.find(query, {"user_email": 1}).to_list(length=5000)
    return {r.get("user_email", "").lower() for r in rows}


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(current_admin: TokenData = Depends(get_current_active_admin)):
    """Fetch high-level dashboard analytics (Admin only)."""
    db = get_database()

    # Scans are submissions, and revenue is the payments that were verified —
    # both were counted off collections that never filled ("properties") or
    # made up from a guessed price.
    total_users, total_scans, paying, earned = await asyncio.gather(
        db.users.count_documents({}),
        db.submissions.count_documents({}),
        _paying_emails(db),
        db.payments.aggregate([{"$group": {"_id": None, "amount": {"$sum": "$amount"}}}]).to_list(length=1),
    )

    return DashboardStats(
        total_users=total_users,
        total_scans=total_scans,
        premium_users=len(paying),
        revenue=float(earned[0]["amount"]) if earned else 0.0,
    )

@router.get("/users", response_model=PaginatedUsersResponse)
async def get_all_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    current_admin: TokenData = Depends(get_current_active_admin)
):
    """Fetch a paginated list of all users."""
    db = get_database()
    skip = (page - 1) * page_size
    
    cursor = db.users.find({}).sort("created_at", -1).skip(skip).limit(page_size)
    users_db = await cursor.to_list(length=page_size)
    total_count = await db.users.count_documents({})
    
    paying = await _paying_emails(db, [u.get("email", "") for u in users_db])

    users = []
    for u in users_db:
        email = u.get("email", "unknown@example.com")
        users.append(UserOverview(
            id=str(u.get("_id", "")),
            email=email,
            name=u.get("name", "Unknown User"),
            created_at=u.get("created_at", now_utc()),
            is_premium=email.lower() in paying,
            status=u.get("status", "active")
        ))
        
    return PaginatedUsersResponse(
        users=users,
        total_count=total_count,
        page=page,
        page_size=page_size
    )

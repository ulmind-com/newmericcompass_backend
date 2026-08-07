from fastapi import APIRouter, Depends, Query
from typing import List
import asyncio
from datetime import datetime

from app.core.security import get_current_active_admin, TokenData
from app.core.database import get_database
from app.schemas.admin import DashboardStats, PaginatedUsersResponse, UserOverview

router = APIRouter()

@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(current_admin: TokenData = Depends(get_current_active_admin)):
    """Fetch high-level dashboard analytics (Admin only)."""
    db = get_database()
    
    # Run aggregations concurrently for better performance
    total_users_future = db.users.count_documents({})
    total_scans_future = db.properties.count_documents({})
    premium_users_future = db.users.count_documents({"is_premium": True})
    
    total_users, total_scans, premium_users = await asyncio.gather(
        total_users_future,
        total_scans_future,
        premium_users_future
    )
    
    # Mocking revenue for now, could be fetched from payments collection
    revenue = premium_users * 19.99 

    return DashboardStats(
        total_users=total_users,
        total_scans=total_scans,
        premium_users=premium_users,
        revenue=revenue
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
    
    users = []
    for u in users_db:
        users.append(UserOverview(
            id=str(u.get("_id", "")),
            email=u.get("email", "unknown@example.com"),
            name=u.get("name", "Unknown User"),
            created_at=u.get("created_at", datetime.utcnow()),
            is_premium=u.get("is_premium", False),
            status=u.get("status", "active")
        ))
        
    return PaginatedUsersResponse(
        users=users,
        total_count=total_count,
        page=page,
        page_size=page_size
    )

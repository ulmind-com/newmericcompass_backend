"""Admin control over pricing, free access, and the money that came in."""

from datetime import datetime, timedelta, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.database import get_database
from app.core.security import TokenData, get_current_active_admin
from app.domain import billing as bl
from app.schemas.billing import (
    AdminGrant,
    EntitlementResponse,
    PaymentResponse,
    PlanCreate,
    PlanResponse,
    PlanUpdate,
    RevenueBucket,
    RevenueReport,
)
from app.schemas.common import now_utc, serialize_doc, serialize_docs

router = APIRouter()


def _oid(value: str) -> ObjectId:
    if not ObjectId.is_valid(value):
        raise HTTPException(status_code=400, detail="Invalid id")
    return ObjectId(value)


# ---------------------------------------------------------------- plans ----

@router.get("/plans", response_model=list[PlanResponse], summary="All plans")
async def list_plans(
    _: TokenData = Depends(get_current_active_admin),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    cursor = db[bl.PLANS].find({}).sort([("feature", 1), ("order", 1)])
    return serialize_docs(await cursor.to_list(length=200))


@router.post("/plans", response_model=PlanResponse, status_code=201, summary="Create a plan")
async def create_plan(
    payload: PlanCreate,
    _: TokenData = Depends(get_current_active_admin),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    if await db[bl.PLANS].find_one({"slug": payload.slug}):
        raise HTTPException(status_code=409, detail="A plan with that slug already exists.")
    doc = payload.model_dump()
    doc["created_at"] = now_utc()
    result = await db[bl.PLANS].insert_one(doc)
    doc["_id"] = result.inserted_id
    return serialize_doc(doc)


@router.put("/plans/{plan_id}", response_model=PlanResponse, summary="Update a plan")
async def update_plan(
    plan_id: str,
    payload: PlanUpdate,
    _: TokenData = Depends(get_current_active_admin),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    # exclude_unset so clearing duration/quota to null (lifetime/unlimited) is
    # distinguishable from simply not touching the field.
    changes = payload.model_dump(exclude_unset=True)
    if changes:
        changes["updated_at"] = now_utc()
        await db[bl.PLANS].update_one({"_id": _oid(plan_id)}, {"$set": changes})
    doc = await db[bl.PLANS].find_one({"_id": _oid(plan_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Plan not found")
    return serialize_doc(doc)


@router.delete("/plans/{plan_id}", status_code=204, summary="Delete a plan")
async def delete_plan(
    plan_id: str,
    _: TokenData = Depends(get_current_active_admin),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    await db[bl.PLANS].delete_one({"_id": _oid(plan_id)})


# --------------------------------------------------------- entitlements ----

@router.get("/entitlements", response_model=list[EntitlementResponse], summary="Who has what")
async def list_entitlements(
    email: str | None = None,
    feature: str | None = None,
    _: TokenData = Depends(get_current_active_admin),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    query: dict = {}
    if email:
        query["user_email"] = bl.normalize_email(email)
    if feature:
        query["feature"] = feature
    cursor = db[bl.ENTITLEMENTS].find(query).sort("granted_at", -1)
    return serialize_docs(await cursor.to_list(length=500))


@router.post("/grant", response_model=EntitlementResponse, summary="Give a user free access")
async def grant_access(
    payload: AdminGrant,
    admin: TokenData = Depends(get_current_active_admin),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    email = bl.normalize_email(payload.email)
    if not email:
        raise HTTPException(status_code=400, detail="An email is required.")
    doc = await bl.grant(
        db,
        email=email,
        feature=payload.feature,
        source="admin",
        plan_name="Granted by admin",
        duration_days=payload.duration_days,
        submission_quota=payload.submission_quota,
        note=payload.note or f"Granted by {admin.email}",
    )
    return serialize_doc(doc)


@router.delete("/entitlements/{entitlement_id}", status_code=204, summary="Revoke access")
async def revoke_access(
    entitlement_id: str,
    _: TokenData = Depends(get_current_active_admin),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    await db[bl.ENTITLEMENTS].update_one({"_id": _oid(entitlement_id)}, {"$set": {"is_active": False}})


@router.post("/entitlements/{entitlement_id}/reset-quota", response_model=EntitlementResponse, summary="Reset used quota")
async def reset_quota(
    entitlement_id: str,
    _: TokenData = Depends(get_current_active_admin),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    await db[bl.ENTITLEMENTS].update_one({"_id": _oid(entitlement_id)}, {"$set": {"quota_used": 0}})
    doc = await db[bl.ENTITLEMENTS].find_one({"_id": _oid(entitlement_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Entitlement not found")
    return serialize_doc(doc)


# ------------------------------------------------------------- payments ----

@router.get("/payments", response_model=list[PaymentResponse], summary="Successful payments")
async def list_payments(
    email: str | None = None,
    feature: str | None = None,
    limit: int = Query(200, le=1000),
    _: TokenData = Depends(get_current_active_admin),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    query: dict = {}
    if email:
        query["user_email"] = bl.normalize_email(email)
    if feature:
        query["feature"] = feature
    cursor = db[bl.PAYMENTS].find(query).sort("created_at", -1)
    return serialize_docs(await cursor.to_list(length=limit))


@router.get("/revenue", response_model=RevenueReport, summary="Where the money came from")
async def revenue(
    _: TokenData = Depends(get_current_active_admin),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    async def bucket(field: str, label_field: str | None = None) -> list[RevenueBucket]:
        group: dict = {"_id": f"${field}", "amount": {"$sum": "$amount"}, "count": {"$sum": 1}}
        if label_field:
            group["label"] = {"$last": f"${label_field}"}
        rows = await db[bl.PAYMENTS].aggregate([
            {"$group": group}, {"$sort": {"amount": -1}},
        ]).to_list(length=200)
        return [
            RevenueBucket(key=str(r["_id"]), label=r.get("label"), amount=r["amount"], count=r["count"])
            for r in rows if r["_id"] is not None
        ]

    totals = await db[bl.PAYMENTS].aggregate([
        {"$group": {"_id": None, "amount": {"$sum": "$amount"}, "count": {"$sum": 1}}},
    ]).to_list(length=1)

    now = datetime.now(timezone.utc)
    start_of_day = now - timedelta(days=1)
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    async def since(dt: datetime) -> int:
        rows = await db[bl.PAYMENTS].aggregate([
            {"$match": {"created_at": {"$gte": dt}}},
            {"$group": {"_id": None, "amount": {"$sum": "$amount"}}},
        ]).to_list(length=1)
        return rows[0]["amount"] if rows else 0

    by_month_rows = await db[bl.PAYMENTS].aggregate([
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m", "date": "$created_at"}},
            "amount": {"$sum": "$amount"}, "count": {"$sum": 1},
        }},
        {"$sort": {"_id": -1}}, {"$limit": 12},
    ]).to_list(length=12)

    return RevenueReport(
        total_amount=totals[0]["amount"] if totals else 0,
        total_payments=totals[0]["count"] if totals else 0,
        today_amount=await since(start_of_day),
        month_amount=await since(start_of_month),
        paying_users=len(await db[bl.PAYMENTS].distinct("user_email")),
        by_feature=await bucket("feature"),
        by_plan=await bucket("plan_slug", "plan_name"),
        by_month=[
            RevenueBucket(key=r["_id"], amount=r["amount"], count=r["count"])
            for r in by_month_rows if r["_id"]
        ],
    )

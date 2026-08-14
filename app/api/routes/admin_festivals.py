"""Admin CRUD for seasonal themes."""

from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.database import get_database
from app.core.security import TokenData, get_current_active_admin
from app.schemas.common import now_utc, serialize_doc, serialize_docs
from app.schemas.festival import FestivalCreate, FestivalResponse, FestivalUpdate

router = APIRouter()
COLL = "festivals"


def _oid(value: str) -> ObjectId:
    if not ObjectId.is_valid(value):
        raise HTTPException(status_code=400, detail="Invalid id")
    return ObjectId(value)


async def active_festival(db: AsyncIOMotorDatabase) -> dict | None:
    """The one running right now, if any.

    Overlapping runs are resolved by whichever started most recently, so a
    one-day theme laid over a week-long sale wins for its day rather than
    losing to the run it sits inside.
    """
    now = datetime.now(timezone.utc)
    return await db[COLL].find_one(
        {"is_active": True, "starts_at": {"$lte": now}, "ends_at": {"$gte": now}},
        sort=[("starts_at", -1)],
    )


@router.get("", response_model=list[FestivalResponse], summary="All themes")
async def list_festivals(
    _: TokenData = Depends(get_current_active_admin),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    cursor = db[COLL].find({}).sort("starts_at", -1)
    return serialize_docs(await cursor.to_list(length=200))


@router.post("", response_model=FestivalResponse, status_code=201, summary="Create a theme")
async def create_festival(
    payload: FestivalCreate,
    _: TokenData = Depends(get_current_active_admin),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    if payload.ends_at <= payload.starts_at:
        raise HTTPException(status_code=400, detail="The end date must be after the start date.")
    doc = payload.model_dump()
    doc["created_at"] = now_utc()
    result = await db[COLL].insert_one(doc)
    doc["_id"] = result.inserted_id
    return serialize_doc(doc)


@router.put("/{festival_id}", response_model=FestivalResponse, summary="Update a theme")
async def update_festival(
    festival_id: str,
    payload: FestivalUpdate,
    _: TokenData = Depends(get_current_active_admin),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    changes = payload.model_dump(exclude_unset=True)
    if changes:
        changes["updated_at"] = now_utc()
        await db[COLL].update_one({"_id": _oid(festival_id)}, {"$set": changes})
    doc = await db[COLL].find_one({"_id": _oid(festival_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Theme not found")
    return serialize_doc(doc)


@router.delete("/{festival_id}", status_code=204, summary="Delete a theme")
async def delete_festival(
    festival_id: str,
    _: TokenData = Depends(get_current_active_admin),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    await db[COLL].delete_one({"_id": _oid(festival_id)})

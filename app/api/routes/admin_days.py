"""Admin CRUD for the day-wise remedial protocol."""

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.database import get_database
from app.core.security import TokenData, get_current_active_admin
from app.schemas.common import now_utc, serialize_doc, serialize_docs
from app.schemas.day_protocol import DayProtocolCreate, DayProtocolResponse, DayProtocolUpdate

router = APIRouter()

DAYS = "day_protocols"


def _oid(value: str) -> ObjectId:
    if not ObjectId.is_valid(value):
        raise HTTPException(status_code=400, detail="Invalid id")
    return ObjectId(value)


@router.get("", response_model=list[DayProtocolResponse], summary="All seven days")
async def list_days(
    _: TokenData = Depends(get_current_active_admin),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    cursor = db[DAYS].find({}).sort("weekday", 1)
    return serialize_docs(await cursor.to_list(length=14))


@router.post("", response_model=DayProtocolResponse, status_code=201, summary="Add a day")
async def create_day(
    payload: DayProtocolCreate,
    _: TokenData = Depends(get_current_active_admin),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    if await db[DAYS].find_one({"weekday": payload.weekday}):
        raise HTTPException(status_code=409, detail="That weekday already has a protocol.")
    doc = payload.model_dump()
    doc["created_at"] = now_utc()
    result = await db[DAYS].insert_one(doc)
    doc["_id"] = result.inserted_id
    return serialize_doc(doc)


@router.put("/{day_id}", response_model=DayProtocolResponse, summary="Update a day")
async def update_day(
    day_id: str,
    payload: DayProtocolUpdate,
    _: TokenData = Depends(get_current_active_admin),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    changes = payload.model_dump(exclude_unset=True)
    if changes:
        changes["updated_at"] = now_utc()
        await db[DAYS].update_one({"_id": _oid(day_id)}, {"$set": changes})
    doc = await db[DAYS].find_one({"_id": _oid(day_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Day not found")
    return serialize_doc(doc)


@router.delete("/{day_id}", status_code=204, summary="Delete a day")
async def delete_day(
    day_id: str,
    _: TokenData = Depends(get_current_active_admin),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    await db[DAYS].delete_one({"_id": _oid(day_id)})

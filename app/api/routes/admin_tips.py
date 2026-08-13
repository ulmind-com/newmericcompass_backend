"""Admin CRUD for Daily Tips + a public listing endpoint."""

import logging

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.database import get_database
from app.core.security import TokenData, get_current_admin
from app.schemas.common import now_utc, serialize_doc, serialize_docs
from app.schemas.tip import TipCreate, TipResponse, TipUpdate
from app.services.push_service import send_to_all

logger = logging.getLogger(__name__)
router = APIRouter()
COLL = "tips"


@router.get("/", response_model=list[TipResponse])
async def list_tips(
    db: AsyncIOMotorDatabase = Depends(get_database),
    _: TokenData = Depends(get_current_admin),
):
    cursor = db[COLL].find({}).sort("order", 1)
    return serialize_docs(await cursor.to_list(length=1000))


@router.post("/", response_model=TipResponse, status_code=201)
async def create_tip(
    payload: TipCreate,
    db: AsyncIOMotorDatabase = Depends(get_database),
    _: TokenData = Depends(get_current_admin),
):
    doc = payload.model_dump(exclude={"notify"})
    doc["created_at"] = now_utc()
    result = await db[COLL].insert_one(doc)
    doc["_id"] = result.inserted_id

    # After the write, and never in a way that can fail it: a tip that saved
    # but could not be announced is still a tip.
    if payload.notify and doc.get("is_active", True):
        try:
            stats = await send_to_all(
                db, title=doc["title"], body=doc["body"],
                data={"type": "tip", "tip_id": str(result.inserted_id)},
            )
            doc["notified_at"] = now_utc()
            doc["notified_count"] = stats["sent"]
            await db[COLL].update_one(
                {"_id": result.inserted_id},
                {"$set": {"notified_at": doc["notified_at"], "notified_count": doc["notified_count"]}},
            )
        except Exception:
            logger.warning("Tip %s saved but could not be announced", result.inserted_id, exc_info=True)

    return serialize_doc(doc)


@router.post("/{tip_id}/notify", summary="Send this tip as a notification again")
async def notify_tip(
    tip_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    _: TokenData = Depends(get_current_admin),
):
    if not ObjectId.is_valid(tip_id):
        raise HTTPException(status_code=400, detail="Invalid tip id")
    doc = await db[COLL].find_one({"_id": ObjectId(tip_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Tip not found")

    stats = await send_to_all(
        db, title=doc["title"], body=doc["body"], data={"type": "tip", "tip_id": tip_id},
    )
    await db[COLL].update_one(
        {"_id": ObjectId(tip_id)},
        {"$set": {"notified_at": now_utc(), "notified_count": stats["sent"]}},
    )
    return stats


@router.put("/{tip_id}", response_model=TipResponse)
async def update_tip(
    tip_id: str,
    payload: TipUpdate,
    db: AsyncIOMotorDatabase = Depends(get_database),
    _: TokenData = Depends(get_current_admin),
):
    if not ObjectId.is_valid(tip_id):
        raise HTTPException(status_code=400, detail="Invalid tip id")
    update_data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    doc = await db[COLL].find_one_and_update(
        {"_id": ObjectId(tip_id)}, {"$set": update_data}, return_document=True
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Tip not found")
    return serialize_doc(doc)


@router.delete("/{tip_id}", status_code=204)
async def delete_tip(
    tip_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    _: TokenData = Depends(get_current_admin),
):
    if not ObjectId.is_valid(tip_id):
        raise HTTPException(status_code=400, detail="Invalid tip id")
    result = await db[COLL].delete_one({"_id": ObjectId(tip_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Tip not found")

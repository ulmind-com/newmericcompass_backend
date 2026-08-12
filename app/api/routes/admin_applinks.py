"""Admin CRUD for the side-menu links and the share / review settings."""

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.database import get_database
from app.core.security import TokenData, get_current_active_admin
from app.schemas.applink import AppLinkCreate, AppLinkResponse, AppLinkUpdate, ShareSettings
from app.schemas.common import now_utc, serialize_doc, serialize_docs

router = APIRouter()

LINKS = "app_links"
SETTINGS = "app_settings"
SHARE_ID = "share"


def _oid(value: str) -> ObjectId:
    if not ObjectId.is_valid(value):
        raise HTTPException(status_code=400, detail="Invalid id")
    return ObjectId(value)


@router.get("/links", response_model=list[AppLinkResponse], summary="All menu links")
async def list_links(
    _: TokenData = Depends(get_current_active_admin),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    cursor = db[LINKS].find({}).sort([("section", 1), ("order", 1)])
    return serialize_docs(await cursor.to_list(length=500))


@router.post("/links", response_model=AppLinkResponse, status_code=201, summary="Add a link")
async def create_link(
    payload: AppLinkCreate,
    _: TokenData = Depends(get_current_active_admin),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    doc = payload.model_dump()
    doc["created_at"] = now_utc()
    result = await db[LINKS].insert_one(doc)
    doc["_id"] = result.inserted_id
    return serialize_doc(doc)


@router.put("/links/{link_id}", response_model=AppLinkResponse, summary="Update a link")
async def update_link(
    link_id: str,
    payload: AppLinkUpdate,
    _: TokenData = Depends(get_current_active_admin),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    changes = payload.model_dump(exclude_unset=True)
    if changes:
        changes["updated_at"] = now_utc()
        await db[LINKS].update_one({"_id": _oid(link_id)}, {"$set": changes})
    doc = await db[LINKS].find_one({"_id": _oid(link_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Link not found")
    return serialize_doc(doc)


@router.delete("/links/{link_id}", status_code=204, summary="Delete a link")
async def delete_link(
    link_id: str,
    _: TokenData = Depends(get_current_active_admin),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    await db[LINKS].delete_one({"_id": _oid(link_id)})


@router.get("/share", response_model=ShareSettings, summary="Share & review settings")
async def get_share(
    _: TokenData = Depends(get_current_active_admin),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    doc = await db[SETTINGS].find_one({"_id": SHARE_ID}) or {}
    doc.pop("_id", None)
    return ShareSettings(**doc)


@router.put("/share", response_model=ShareSettings, summary="Update share & review settings")
async def update_share(
    payload: ShareSettings,
    _: TokenData = Depends(get_current_active_admin),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    await db[SETTINGS].update_one({"_id": SHARE_ID}, {"$set": payload.model_dump()}, upsert=True)
    return payload

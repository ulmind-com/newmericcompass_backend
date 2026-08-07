"""Admin CRUD for categories (the app's placement grid)."""

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.database import get_database
from app.core.security import TokenData, get_current_admin
from app.schemas.category import CategoryCreate, CategoryResponse, CategoryUpdate
from app.schemas.common import serialize_doc, serialize_docs

router = APIRouter()
COLL = "categories"


@router.get("/", response_model=list[CategoryResponse])
async def list_all(
    db: AsyncIOMotorDatabase = Depends(get_database),
    _: TokenData = Depends(get_current_admin),
):
    cursor = db[COLL].find({}).sort("order", 1)
    return serialize_docs(await cursor.to_list(length=500))


@router.post("/", response_model=CategoryResponse, status_code=201)
async def create(
    payload: CategoryCreate,
    db: AsyncIOMotorDatabase = Depends(get_database),
    _: TokenData = Depends(get_current_admin),
):
    if await db[COLL].find_one({"slug": payload.slug}):
        raise HTTPException(status_code=409, detail="A category with this slug already exists")
    doc = payload.model_dump()
    result = await db[COLL].insert_one(doc)
    doc["_id"] = result.inserted_id
    return serialize_doc(doc)


@router.put("/{category_id}", response_model=CategoryResponse)
async def update(
    category_id: str,
    payload: CategoryUpdate,
    db: AsyncIOMotorDatabase = Depends(get_database),
    _: TokenData = Depends(get_current_admin),
):
    if not ObjectId.is_valid(category_id):
        raise HTTPException(status_code=400, detail="Invalid category id")
    update_data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    doc = await db[COLL].find_one_and_update(
        {"_id": ObjectId(category_id)}, {"$set": update_data}, return_document=True
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Category not found")
    return serialize_doc(doc)


@router.delete("/{category_id}", status_code=204)
async def delete(
    category_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    _: TokenData = Depends(get_current_admin),
):
    if not ObjectId.is_valid(category_id):
        raise HTTPException(status_code=400, detail="Invalid category id")
    result = await db[COLL].delete_one({"_id": ObjectId(category_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Category not found")

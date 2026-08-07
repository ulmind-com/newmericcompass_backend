"""Admin CRUD for Vastu rules (category x pada -> verdict/effects/treatments)."""

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.database import get_database
from app.core.security import TokenData, get_current_admin
from app.schemas.common import serialize_doc, serialize_docs
from app.schemas.rule import RuleCreate, RuleResponse, RuleUpdate

router = APIRouter()
COLL = "vastu_rules"


@router.get("/", response_model=list[RuleResponse])
async def list_rules(
    category: str | None = Query(None, description="Filter by category slug"),
    pada_code: str | None = Query(None, description="Filter by pada code, e.g. N5"),
    db: AsyncIOMotorDatabase = Depends(get_database),
    _: TokenData = Depends(get_current_admin),
):
    query: dict = {}
    if category:
        query["category_slug"] = category
    if pada_code:
        query["pada_code"] = pada_code.upper()
    cursor = db[COLL].find(query).sort([("category_slug", 1), ("pada_code", 1)])
    return serialize_docs(await cursor.to_list(length=5000))


@router.post("/", response_model=RuleResponse, status_code=201)
async def create_rule(
    payload: RuleCreate,
    db: AsyncIOMotorDatabase = Depends(get_database),
    _: TokenData = Depends(get_current_admin),
):
    doc = payload.model_dump()
    doc["pada_code"] = doc["pada_code"].upper()
    existing = await db[COLL].find_one(
        {"category_slug": doc["category_slug"], "pada_code": doc["pada_code"]}
    )
    if existing:
        raise HTTPException(status_code=409, detail="A rule for this category + pada already exists")
    result = await db[COLL].insert_one(doc)
    doc["_id"] = result.inserted_id
    return serialize_doc(doc)


@router.put("/{rule_id}", response_model=RuleResponse)
async def update_rule(
    rule_id: str,
    payload: RuleUpdate,
    db: AsyncIOMotorDatabase = Depends(get_database),
    _: TokenData = Depends(get_current_admin),
):
    if not ObjectId.is_valid(rule_id):
        raise HTTPException(status_code=400, detail="Invalid rule id")
    update_data = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    doc = await db[COLL].find_one_and_update(
        {"_id": ObjectId(rule_id)}, {"$set": update_data}, return_document=True
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Rule not found")
    return serialize_doc(doc)


@router.put("/upsert/{category}/{pada_code}", response_model=RuleResponse)
async def upsert_rule(
    category: str,
    pada_code: str,
    payload: RuleUpdate,
    db: AsyncIOMotorDatabase = Depends(get_database),
    _: TokenData = Depends(get_current_admin),
):
    """Create-or-update a rule by its natural key -- handy for grid editors."""
    update_data = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}
    doc = await db[COLL].find_one_and_update(
        {"category_slug": category, "pada_code": pada_code.upper()},
        {"$set": update_data, "$setOnInsert": {"category_slug": category, "pada_code": pada_code.upper()}},
        upsert=True,
        return_document=True,
    )
    return serialize_doc(doc)


@router.delete("/{rule_id}", status_code=204)
async def delete_rule(
    rule_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    _: TokenData = Depends(get_current_admin),
):
    if not ObjectId.is_valid(rule_id):
        raise HTTPException(status_code=400, detail="Invalid rule id")
    result = await db[COLL].delete_one({"_id": ObjectId(rule_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Rule not found")

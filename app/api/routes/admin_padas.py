"""Admin: view and edit the 32 pada attributes (structure is fixed)."""

from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.database import get_database
from app.core.security import TokenData, get_current_admin
from app.schemas.common import serialize_doc, serialize_docs
from app.schemas.pada import PadaResponse, PadaUpdate

router = APIRouter()
COLL = "padas"


@router.get("/", response_model=list[PadaResponse])
async def list_all(
    db: AsyncIOMotorDatabase = Depends(get_database),
    _: TokenData = Depends(get_current_admin),
):
    cursor = db[COLL].find({}).sort("index", 1)
    return serialize_docs(await cursor.to_list(length=64))


@router.put("/{code}", response_model=PadaResponse)
async def update(
    code: str,
    payload: PadaUpdate,
    db: AsyncIOMotorDatabase = Depends(get_database),
    _: TokenData = Depends(get_current_admin),
):
    update_data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    doc = await db[COLL].find_one_and_update(
        {"code": code.upper()}, {"$set": update_data}, return_document=True
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Pada not found")
    return serialize_doc(doc)

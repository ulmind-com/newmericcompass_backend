"""Public (app-facing) read endpoints: bootstrap config, categories, padas."""

from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.core.database import get_database
from app.domain.padas import COMPASS_CHART
from app.schemas.category import CategoryResponse
from app.schemas.common import serialize_docs
from app.schemas.pada import PadaResponse
from app.schemas.tip import TipResponse

router = APIRouter()

CATEGORIES = "categories"
PADAS = "padas"
TIPS = "tips"


async def _active_categories(db: AsyncIOMotorDatabase) -> list[dict]:
    cursor = db[CATEGORIES].find({"is_active": True}).sort("order", 1)
    return serialize_docs(await cursor.to_list(length=500))


async def _active_padas(db: AsyncIOMotorDatabase) -> list[dict]:
    cursor = db[PADAS].find({"is_active": True}).sort("index", 1)
    return serialize_docs(await cursor.to_list(length=64))


@router.get("/categories", response_model=list[CategoryResponse], summary="Active categories")
async def list_categories(db: AsyncIOMotorDatabase = Depends(get_database)):
    return await _active_categories(db)


@router.get("/padas", response_model=list[PadaResponse], summary="Active 32 padas (compass zones)")
async def list_padas(db: AsyncIOMotorDatabase = Depends(get_database)):
    return await _active_padas(db)


@router.get("/tips", response_model=list[TipResponse], summary="Active daily tips")
async def list_tips(db: AsyncIOMotorDatabase = Depends(get_database)):
    cursor = db[TIPS].find({"is_active": True}).sort("order", 1)
    return serialize_docs(await cursor.to_list(length=500))


@router.get("/config", summary="App bootstrap: categories + padas in one call")
async def app_config(db: AsyncIOMotorDatabase = Depends(get_database)):
    categories = await _active_categories(db)
    padas = await _active_padas(db)
    return {
        "app": {
            "name": "Newmeric Compass",
            "system": "N5-32-pada",
            "theme": {
                "primary": "#FF6A00",
                "primaryDark": "#E8590C",
                "accentSaffron": "#F4A300",
                "accentMaroon": "#7A0C0C",
                "accentGold": "#D4AF37",
                "accentGreen": "#0B6E4F",
            },
        },
        "compass": COMPASS_CHART,
        "support": {
            "acharya_name": settings.ACHARYA_NAME,
            "acharya_phone": settings.ACHARYA_PHONE,
            "acharya_whatsapp": settings.ACHARYA_WHATSAPP or settings.ACHARYA_PHONE,
        },
        "categories": categories,
        "padas": padas,
    }

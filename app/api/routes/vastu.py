"""Public Vastu engine: map a category + compass bearing to a verdict.

Resolution order for a lookup:
  1. A category-specific rule for the exact pada (category_slug + pada_code).
  2. A category-specific rule for any pada sharing the 16-wind direction.
  3. A synthesized fallback from the pada's own ``default_verdict`` so the app
     always receives a usable result (``is_configured = False``).
"""

import logging

from fastapi import APIRouter, Depends, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.database import get_database
from app.domain.padas import pada_for_degree
from app.schemas.pada import PadaBase, Verdict
from app.schemas.vastu import VastuLookupRequest, VastuLookupResponse

logger = logging.getLogger(__name__)

router = APIRouter()

RULES = "vastu_rules"
PADAS = "padas"

_DEFAULT_SCORE = {
    Verdict.EXCELLENT: 90,
    Verdict.GOOD: 75,
    Verdict.AVERAGE: 50,
    Verdict.BAD: 25,
}


async def _resolve(db: AsyncIOMotorDatabase, category: str, degree: float) -> VastuLookupResponse:
    pada_def = pada_for_degree(degree)
    code = pada_def["code"]

    # Prefer a stored pada doc (admin may have edited attributes); fall back to code default.
    stored = await db[PADAS].find_one({"code": code})
    pada = {**pada_def, **(stored or {})}
    pada.pop("_id", None)

    rule = await db[RULES].find_one(
        {"category_slug": category, "pada_code": code, "is_active": {"$ne": False}}
    )

    if rule is None:
        # Try any rule for the same 16-wind direction (coarser configuration).
        codes_in_dir = [
            p["code"] for p in await db[PADAS]
            .find({"direction16": pada["direction16"]}, {"code": 1})
            .to_list(length=8)
        ] or [code]
        rule = await db[RULES].find_one(
            {"category_slug": category, "pada_code": {"$in": codes_in_dir}, "is_active": {"$ne": False}}
        )

    if rule is not None:
        verdict = Verdict(rule.get("verdict", pada["default_verdict"]))
        return VastuLookupResponse(
            category=category,
            degree=degree,
            pada=PadaBase(**pada),
            direction16=pada["direction16"],
            direction16_full=pada["direction16_full"],
            verdict=verdict,
            score=int(rule.get("score", _DEFAULT_SCORE[verdict])),
            effects=rule.get("effects", []),
            treatments=rule.get("treatments", []),
            notes=rule.get("notes"),
            is_configured=True,
        )

    # Fallback: synthesize from the pada default so the app never gets nothing.
    verdict = Verdict(pada["default_verdict"])
    return VastuLookupResponse(
        category=category,
        degree=degree,
        pada=PadaBase(**pada),
        direction16=pada["direction16"],
        direction16_full=pada["direction16_full"],
        verdict=verdict,
        score=_DEFAULT_SCORE[verdict],
        effects=[
            f"This location governs '{pada['life_aspect']}'." if pada.get("life_aspect") else
            f"{pada['direction16_full']} placement.",
        ],
        treatments=[],
        notes="No category-specific rule configured yet; showing the zone's general nature.",
        is_configured=False,
    )


@router.get("/lookup", response_model=VastuLookupResponse, summary="Lookup by category + degree")
async def lookup(
    category: str = Query(..., description="Category slug, e.g. 'toilet'"),
    degree: float = Query(..., ge=0, le=360),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    return await _resolve(db, category, degree)


@router.post("/analyze", response_model=VastuLookupResponse, summary="Lookup by JSON body")
async def analyze(payload: VastuLookupRequest, db: AsyncIOMotorDatabase = Depends(get_database)):
    return await _resolve(db, payload.category, payload.degree)

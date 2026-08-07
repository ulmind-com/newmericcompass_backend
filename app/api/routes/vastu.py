import logging

from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.database import get_database
from app.schemas.vastu import VastuAnalysisRequest, VastuAnalysisResponse
from app.utils.vastu_calculator import get_vastu_direction

logger = logging.getLogger(__name__)

router = APIRouter()

VASTU_RULES_COLLECTION = "vastu_rules"


@router.post(
    "/analyze",
    response_model=VastuAnalysisResponse,
    status_code=status.HTTP_200_OK,
    summary="Assess a room's Vastu compliance from its compass bearing",
)
async def analyze_vastu(
    payload: VastuAnalysisRequest,
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> VastuAnalysisResponse:
    direction = get_vastu_direction(payload.degree)

    rule_document = await db[VASTU_RULES_COLLECTION].find_one(
        {"room_type": payload.room_type.value, "direction": direction.value}
    )

    if rule_document is None:
        logger.warning(
            "No Vastu rule configured for room_type=%s direction=%s (property_id=%s)",
            payload.room_type.value,
            direction.value,
            payload.property_id,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No Vastu rule configured for '{payload.room_type.value}' "
                f"facing '{direction.value}'."
            ),
        )

    return VastuAnalysisResponse(
        property_id=payload.property_id,
        room_type=payload.room_type,
        input_degree=payload.degree,
        calculated_direction=direction,
        score=rule_document["score"],
        status=rule_document["status"],
        remedy=rule_document.get("remedy"),
        notes=rule_document.get("notes"),
    )

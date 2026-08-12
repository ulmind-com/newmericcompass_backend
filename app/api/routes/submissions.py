"""Public: save and fetch a compiled property scan (the app's capture -> send)."""

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.database import get_database
from app.core.security import TokenData, get_current_user
from app.domain import billing as bl
from app.domain.padas import pada_for_degree
from app.schemas.billing import Feature
from app.schemas.common import now_utc, serialize_doc
from app.schemas.submission import SubmissionCreate, SubmissionResponse

router = APIRouter()

SUBMISSIONS = "submissions"


@router.post("/", response_model=SubmissionResponse, status_code=201, summary="Save a property scan")
async def create_submission(
    payload: SubmissionCreate,
    current: TokenData = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Submitting is the metered part of the product, so it is checked and
    charged against the user's subscription before anything is written."""
    email = bl.normalize_email(current.email)
    access = bl.access_from(await bl.get_entitlement(db, email, Feature.SUBMISSIONS), Feature.SUBMISSIONS)
    if not access.allowed:
        raise HTTPException(
            status_code=402,
            detail={
                "reason": access.reason,
                "feature": Feature.SUBMISSIONS.value,
                "message": (
                    "Your submission quota is used up."
                    if access.reason == "quota_exhausted"
                    else "Your subscription has ended." if access.reason == "expired"
                    else "A subscription is needed to send placements."
                ),
            },
        )

    items = []
    for item in payload.items:
        data = item.model_dump()
        if not data.get("pada_code"):
            pada = pada_for_degree(item.degree)
            data["pada_code"] = pada["code"]
            data["direction16"] = pada["direction16"]
        items.append(data)

    # Take the quota first: a submission that gets saved without being counted
    # is worse than one that fails outright.
    if not await bl.consume(db, email, Feature.SUBMISSIONS):
        raise HTTPException(
            status_code=402,
            detail={"reason": "quota_exhausted", "feature": Feature.SUBMISSIONS.value,
                    "message": "Your submission quota is used up."},
        )

    doc = {
        "device_id": payload.device_id,
        "title": payload.title or "My Property",
        "name": payload.name,
        "whatsapp": payload.whatsapp,
        "email": payload.email,
        "address": payload.address,
        "user_email": email,
        "status": "new",
        "items": items,
        "created_at": now_utc(),
    }
    result = await db[SUBMISSIONS].insert_one(doc)
    doc["_id"] = result.inserted_id
    return serialize_doc(doc)


@router.get("/{submission_id}", response_model=SubmissionResponse, summary="Fetch a saved scan")
async def get_submission(submission_id: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    if not ObjectId.is_valid(submission_id):
        raise HTTPException(status_code=400, detail="Invalid submission id")
    doc = await db[SUBMISSIONS].find_one({"_id": ObjectId(submission_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Submission not found")
    return serialize_doc(doc)

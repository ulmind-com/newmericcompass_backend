"""Public: save and fetch a compiled property scan (the app's Preview -> Submit)."""

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.database import get_database
from app.domain.padas import pada_for_degree
from app.schemas.common import now_utc, serialize_doc
from app.schemas.submission import SubmissionCreate, SubmissionResponse

router = APIRouter()

SUBMISSIONS = "submissions"


@router.post("/", response_model=SubmissionResponse, status_code=201, summary="Save a property scan")
async def create_submission(payload: SubmissionCreate, db: AsyncIOMotorDatabase = Depends(get_database)):
    items = []
    for item in payload.items:
        data = item.model_dump()
        if not data.get("pada_code"):
            pada = pada_for_degree(item.degree)
            data["pada_code"] = pada["code"]
            data["direction16"] = pada["direction16"]
        items.append(data)

    doc = {
        "device_id": payload.device_id,
        "title": payload.title or "My Property",
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

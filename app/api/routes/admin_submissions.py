"""Admin: view property-scan submissions (details, address, photos) and mark status."""

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.core.database import get_database
from app.core.security import TokenData, get_current_admin
from app.schemas.common import serialize_doc, serialize_docs
from app.schemas.submission import SubmissionResponse

router = APIRouter()
COLL = "submissions"


class PaginatedSubmissions(BaseModel):
    submissions: list[SubmissionResponse]
    total_count: int
    page: int
    page_size: int


class SubmissionStatusUpdate(BaseModel):
    status: str  # new | in_review | report_sent


@router.get("/", response_model=PaginatedSubmissions)
async def list_submissions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncIOMotorDatabase = Depends(get_database),
    _: TokenData = Depends(get_current_admin),
):
    skip = (page - 1) * page_size
    cursor = db[COLL].find({}).sort("created_at", -1).skip(skip).limit(page_size)
    docs = serialize_docs(await cursor.to_list(length=page_size))
    total = await db[COLL].count_documents({})
    return PaginatedSubmissions(submissions=docs, total_count=total, page=page, page_size=page_size)


@router.get("/{submission_id}", response_model=SubmissionResponse)
async def get_submission(
    submission_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    _: TokenData = Depends(get_current_admin),
):
    if not ObjectId.is_valid(submission_id):
        raise HTTPException(status_code=400, detail="Invalid submission id")
    doc = await db[COLL].find_one({"_id": ObjectId(submission_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Submission not found")
    return serialize_doc(doc)


@router.patch("/{submission_id}", response_model=SubmissionResponse)
async def update_status(
    submission_id: str,
    payload: SubmissionStatusUpdate,
    db: AsyncIOMotorDatabase = Depends(get_database),
    _: TokenData = Depends(get_current_admin),
):
    if not ObjectId.is_valid(submission_id):
        raise HTTPException(status_code=400, detail="Invalid submission id")
    doc = await db[COLL].find_one_and_update(
        {"_id": ObjectId(submission_id)}, {"$set": {"status": payload.status}}, return_document=True
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Submission not found")
    return serialize_doc(doc)

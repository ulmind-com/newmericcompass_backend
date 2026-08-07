"""App user auth: register, login, profile (required for Vastu Analysis)."""

from datetime import timedelta

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.core.database import get_database
from app.core.security import TokenData, create_access_token, get_current_user, get_password_hash, verify_password
from app.schemas.common import now_utc, serialize_doc, serialize_docs
from app.schemas.submission import SubmissionResponse
from app.schemas.user import AuthResponse, UserLogin, UserProfile, UserRegister, UserUpdate

router = APIRouter()
USERS = "users"


def _token_for(email: str) -> str:
    return create_access_token(
        data={"sub": email, "role": "user"},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def _profile(doc: dict) -> UserProfile:
    doc = serialize_doc(dict(doc))
    return UserProfile(**{k: doc.get(k) for k in
                          ("id", "name", "email", "whatsapp", "phone", "is_premium", "status", "created_at")})


@router.post("/register", response_model=AuthResponse, status_code=201)
async def register(payload: UserRegister, db: AsyncIOMotorDatabase = Depends(get_database)):
    email = payload.email.lower().strip()
    if await db[USERS].find_one({"email": email}):
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    doc = {
        "name": payload.name.strip(),
        "email": email,
        "whatsapp": payload.whatsapp,
        "phone": None,
        "hashed_password": get_password_hash(payload.password),
        "is_premium": False,
        "status": "active",
        "role": "user",
        "created_at": now_utc(),
    }
    res = await db[USERS].insert_one(doc)
    doc["_id"] = res.inserted_id
    return AuthResponse(access_token=_token_for(email), user=_profile(doc))


@router.post("/login", response_model=AuthResponse)
async def login(payload: UserLogin, db: AsyncIOMotorDatabase = Depends(get_database)):
    email = payload.email.lower().strip()
    user = await db[USERS].find_one({"email": email})
    if not user or not verify_password(payload.password, user.get("hashed_password", "")):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if user.get("status") == "blocked":
        raise HTTPException(status_code=403, detail="Account disabled")
    return AuthResponse(access_token=_token_for(email), user=_profile(user))


@router.get("/me", response_model=UserProfile)
async def me(current: TokenData = Depends(get_current_user), db: AsyncIOMotorDatabase = Depends(get_database)):
    user = await db[USERS].find_one({"email": current.email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _profile(user)


@router.get("/me/submissions", response_model=list[SubmissionResponse])
async def my_submissions(
    current: TokenData = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """The logged-in user's own property-scan history."""
    cursor = db.submissions.find({"user_email": (current.email or "").lower()}).sort("created_at", -1)
    return serialize_docs(await cursor.to_list(length=200))


@router.patch("/me", response_model=UserProfile)
async def update_me(
    payload: UserUpdate,
    current: TokenData = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    update = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not update:
        raise HTTPException(status_code=400, detail="No fields to update")
    user = await db[USERS].find_one_and_update(
        {"email": current.email}, {"$set": update}, return_document=True
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _profile(user)

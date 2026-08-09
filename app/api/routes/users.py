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
from app.schemas.user import AuthResponse, UserLogin, UserProfile, UserRegister, UserUpdate, VerifyOTPRequest, ResendOTPRequest

import resend
import random

if settings.RESEND_API_KEY:
    resend.api_key = settings.RESEND_API_KEY

router = APIRouter()
USERS = "users"


def _token_for(email: str) -> str:
    return create_access_token(
        data={"sub": email, "role": "user"},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )

async def _generate_and_send_otp(db: AsyncIOMotorDatabase, email: str, name: str):
    otp = str(random.randint(100000, 999999))
    expires_at = now_utc() + timedelta(minutes=10)
    
    await db["otps"].update_one(
        {"email": email},
        {"$set": {"otp": otp, "expires_at": expires_at}},
        upsert=True
    )
    
    if settings.RESEND_API_KEY and settings.MAIL_ADDRESS:
        try:
            resend.Emails.send({
                "from": f"Newmeric Compass <{settings.MAIL_ADDRESS}>",
                "to": email,
                "subject": "Your Verification Code",
                "html": f"<p>Hello {name},</p><p>Your verification code is: <strong>{otp}</strong></p><p>This code will expire in 10 minutes.</p>"
            })
        except Exception as e:
            print(f"Failed to send email: {e}")


def _profile(doc: dict) -> UserProfile:
    doc = serialize_doc(dict(doc))
    return UserProfile(**{k: doc.get(k) for k in
                          ("id", "name", "email", "whatsapp", "phone", "is_premium", "status", "created_at")})


@router.post("/register", response_model=dict, status_code=201)
async def register(payload: UserRegister, db: AsyncIOMotorDatabase = Depends(get_database)):
    email = payload.email.lower().strip()
    existing_user = await db[USERS].find_one({"email": email})
    
    if existing_user:
        if existing_user.get("status") == "unverified":
            # Resend OTP if unverified
            await _generate_and_send_otp(db, email, existing_user.get("name", ""))
            return {"message": "OTP resent. Please verify your email."}
        raise HTTPException(status_code=409, detail="An account with this email already exists")
        
    doc = {
        "name": payload.name.strip(),
        "email": email,
        "whatsapp": payload.whatsapp,
        "phone": None,
        "hashed_password": get_password_hash(payload.password),
        "is_premium": False,
        "status": "unverified",
        "role": "user",
        "created_at": now_utc(),
    }
    await db[USERS].insert_one(doc)
    await _generate_and_send_otp(db, email, payload.name.strip())
    
    return {"message": "OTP sent. Please verify your email."}


@router.post("/login", response_model=AuthResponse)
async def login(payload: UserLogin, db: AsyncIOMotorDatabase = Depends(get_database)):
    email = payload.email.lower().strip()
    user = await db[USERS].find_one({"email": email})
    if not user or not verify_password(payload.password, user.get("hashed_password", "")):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if user.get("status") == "unverified":
        raise HTTPException(status_code=403, detail="unverified_email")
    if user.get("status") == "blocked":
        raise HTTPException(status_code=403, detail="Account disabled")
    return AuthResponse(access_token=_token_for(email), user=_profile(user))

@router.post("/verify-otp", response_model=AuthResponse)
async def verify_otp(payload: VerifyOTPRequest, db: AsyncIOMotorDatabase = Depends(get_database)):
    email = payload.email.lower().strip()
    otp_record = await db["otps"].find_one({"email": email, "otp": payload.otp})
    
    if not otp_record:
        raise HTTPException(status_code=400, detail="Invalid OTP")
        
    if otp_record.get("expires_at", now_utc()) < now_utc():
        raise HTTPException(status_code=400, detail="OTP has expired")
        
    user = await db[USERS].find_one_and_update(
        {"email": email},
        {"$set": {"status": "active"}},
        return_document=True
    )
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    await db["otps"].delete_one({"email": email})
    
    return AuthResponse(access_token=_token_for(email), user=_profile(user))

@router.post("/resend-otp", response_model=dict)
async def resend_otp(payload: ResendOTPRequest, db: AsyncIOMotorDatabase = Depends(get_database)):
    email = payload.email.lower().strip()
    user = await db[USERS].find_one({"email": email})
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    if user.get("status") != "unverified":
        raise HTTPException(status_code=400, detail="User is already verified or blocked")
        
    await _generate_and_send_otp(db, email, user.get("name", ""))
    return {"message": "OTP resent successfully"}


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

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
from app.schemas.user import (
    AuthResponse, UserLogin, UserProfile, UserRegister, UserUpdate, VerifyOTPRequest,
    ResendOTPRequest, ForgotPasswordRequest, ResetPasswordRequest,
    SignupStartRequest, SignupCompleteRequest,
)

import random
import jwt

from app.services.email_service import send_otp_email

# Same secret/algorithm the rest of the auth stack uses.
_SIGNUP_SECRET = settings.SECRET_KEY or "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"


def _signup_token_for(email: str) -> str:
    """Short-lived proof that this email's OTP was just verified."""
    return create_access_token(
        data={"sub": email, "scope": "signup"},
        expires_delta=timedelta(minutes=20),
    )


def _email_from_signup_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, _SIGNUP_SECRET, algorithms=[settings.ALGORITHM])
    except jwt.PyJWTError:
        return None
    if payload.get("scope") != "signup":
        return None
    return (payload.get("sub") or "").lower().strip()

router = APIRouter()
USERS = "users"
OTP_TTL_MINUTES = 10


def _token_for(email: str) -> str:
    return create_access_token(
        data={"sub": email, "role": "user"},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )

async def _generate_and_send_otp(db: AsyncIOMotorDatabase, email: str, name: str, purpose: str = "verify"):
    """Store a fresh OTP and mail it out. `purpose` picks the template copy."""
    otp = str(random.randint(100000, 999999))
    expires_at = now_utc() + timedelta(minutes=OTP_TTL_MINUTES)
    
    await db["otps"].update_one(
        {"email": email},
        {"$set": {"otp": otp, "expires_at": expires_at}},
        upsert=True
    )
    
    send_otp_email(to=email, otp=otp, name=name, purpose=purpose, minutes=OTP_TTL_MINUTES)


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


# --- Email-first signup (email → OTP → password → profile) ------------------

@router.post("/signup/start", response_model=dict, status_code=201)
async def signup_start(payload: SignupStartRequest, db: AsyncIOMotorDatabase = Depends(get_database)):
    """Step 1 — take just an email and send a verification OTP."""
    email = payload.email.lower().strip()
    if not email or "@" not in email:
        raise HTTPException(status_code=422, detail="Please enter a valid email.")

    existing = await db[USERS].find_one({"email": email})
    if existing and existing.get("status") == "active":
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    # Upsert a placeholder we can complete later; never clobber an in-progress one's history.
    await db[USERS].update_one(
        {"email": email},
        {
            "$set": {"email": email, "status": "pending", "email_verified": False},
            "$setOnInsert": {
                "name": "", "whatsapp": None, "phone": None,
                "is_premium": False, "role": "user", "created_at": now_utc(),
            },
        },
        upsert=True,
    )
    await _generate_and_send_otp(db, email, "")
    return {"message": "A verification code has been sent to your email."}


@router.post("/signup/verify-otp", response_model=dict)
async def signup_verify_otp(payload: VerifyOTPRequest, db: AsyncIOMotorDatabase = Depends(get_database)):
    """Step 2 — check the OTP and hand back a short-lived signup token."""
    email = payload.email.lower().strip()
    otp_record = await db["otps"].find_one({"email": email, "otp": payload.otp})
    if not otp_record:
        raise HTTPException(status_code=400, detail="Invalid OTP")
    if otp_record.get("expires_at", now_utc()) < now_utc():
        raise HTTPException(status_code=400, detail="OTP has expired")

    await db[USERS].update_one({"email": email}, {"$set": {"email_verified": True}})
    await db["otps"].delete_one({"email": email})
    return {"verified": True, "signup_token": _signup_token_for(email)}


@router.post("/signup/complete", response_model=AuthResponse)
async def signup_complete(payload: SignupCompleteRequest, db: AsyncIOMotorDatabase = Depends(get_database)):
    """Step 3 — set password + profile on a verified email and sign the user in."""
    email = payload.email.lower().strip()
    token_email = _email_from_signup_token(payload.signup_token)
    if not token_email or token_email != email:
        raise HTTPException(status_code=401, detail="Verification expired. Please verify your email again.")
    if not payload.name.strip():
        raise HTTPException(status_code=422, detail="Please enter your name.")
    if len(payload.password) < 6:
        raise HTTPException(status_code=422, detail="Password must be at least 6 characters.")

    user = await db[USERS].find_one({"email": email})
    if not user or not user.get("email_verified"):
        raise HTTPException(status_code=400, detail="Please verify your email first.")
    if user.get("status") == "active":
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    user = await db[USERS].find_one_and_update(
        {"email": email},
        {"$set": {
            "name": payload.name.strip(),
            "whatsapp": (payload.whatsapp or "").strip() or None,
            "hashed_password": get_password_hash(payload.password),
            "status": "active",
        }},
        return_document=True,
    )
    return AuthResponse(access_token=_token_for(email), user=_profile(user))


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

@router.post("/forgot-password", response_model=dict)
async def forgot_password(payload: ForgotPasswordRequest, db: AsyncIOMotorDatabase = Depends(get_database)):
    email = payload.email.lower().strip()
    user = await db[USERS].find_one({"email": email})
    
    # We return a generic success message to prevent email enumeration,
    # but we only actually send the email if the user exists and is active.
    if user and user.get("status") != "blocked":
        await _generate_and_send_otp(db, email, user.get("name", ""), purpose="reset")
        
    return {"message": "If an account with that email exists, a password reset code has been sent."}

@router.post("/reset-password", response_model=dict)
async def reset_password(payload: ResetPasswordRequest, db: AsyncIOMotorDatabase = Depends(get_database)):
    email = payload.email.lower().strip()
    otp_record = await db["otps"].find_one({"email": email, "otp": payload.otp})
    
    if not otp_record:
        raise HTTPException(status_code=400, detail="Invalid OTP")
        
    if otp_record.get("expires_at", now_utc()) < now_utc():
        raise HTTPException(status_code=400, detail="OTP has expired")
        
    user = await db[USERS].find_one({"email": email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    await db[USERS].update_one(
        {"email": email},
        {"$set": {"hashed_password": get_password_hash(payload.new_password)}}
    )
    
    await db["otps"].delete_one({"email": email})
    
    return {"message": "Password reset successfully"}


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

"""App user auth: register, login, profile (required for Vastu Analysis)."""

from datetime import timedelta

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.core.database import get_database
from app.core.security import TokenData, create_access_token, get_current_user, get_password_hash, verify_password
from app.schemas.common import as_utc, now_utc, serialize_doc, serialize_docs
from app.schemas.submission import SubmissionResponse
from app.schemas.user import (
    AuthResponse, UserLogin, UserProfile, UserRegister, UserUpdate, VerifyOTPRequest,
    ResendOTPRequest, ForgotPasswordRequest, ResetPasswordRequest,
    SignupStartRequest, SignupCompleteRequest,
    PhoneStartRequest, PhoneVerifyRequest, PhoneSignupCompleteRequest, PhoneLoginRequest,
)

import random
import jwt

from app.services.email_service import send_otp_email
from app.services import whatsapp_service

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


async def _consume_otp(db: AsyncIOMotorDatabase, email: str, otp: str) -> None:
    """Validate an OTP or raise. Callers delete it once the action succeeds."""
    record = await db["otps"].find_one({"email": email, "otp": otp})
    if not record:
        raise HTTPException(status_code=400, detail="Invalid OTP")
    expires_at = as_utc(record.get("expires_at"))
    if expires_at and expires_at < now_utc():
        raise HTTPException(status_code=400, detail="OTP has expired")


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
    await _consume_otp(db, email, payload.otp)

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
    await _consume_otp(db, email, payload.otp)

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

# --- Mobile signup and login, verified over WhatsApp -------------------------
#
# The account is still keyed on an email everywhere else in this API — tokens,
# entitlements, payments and submissions all carry one — so a mobile-only
# signup is given a settled identity address of its own rather than a second
# kind of account the rest of the system would have to learn about. The app
# shows the number; the address is internal and the user can add a real one
# later from their profile.

PHONE_DOMAIN = "wa.newmericcompass.in"
#: A code cannot be asked for again before this many seconds have passed.
PHONE_RESEND_SECONDS = 60
#: Wrong guesses allowed before the code has to be sent again.
PHONE_MAX_ATTEMPTS = 5


def _identity_email(phone: str) -> str:
    return f"{phone}@{PHONE_DOMAIN}"


def is_identity_email(email: str | None) -> bool:
    """True for the address a mobile signup was given rather than typed."""
    return bool(email) and email.lower().endswith(f"@{PHONE_DOMAIN}")


def _phone_token_for(phone: str) -> str:
    """Short-lived proof that this number's code was just verified."""
    return create_access_token(
        data={"sub": phone, "scope": "signup_phone"},
        expires_delta=timedelta(minutes=20),
    )


def _phone_from_signup_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, _SIGNUP_SECRET, algorithms=[settings.ALGORITHM])
    except jwt.PyJWTError:
        return None
    if payload.get("scope") != "signup_phone":
        return None
    return (payload.get("sub") or "").strip() or None


def _clean_phone(raw: str) -> str:
    phone = whatsapp_service.normalise_mobile(raw)
    if not phone:
        raise HTTPException(status_code=422, detail="Please enter a valid WhatsApp number.")
    return phone


async def _send_phone_otp(db: AsyncIOMotorDatabase, phone: str) -> int:
    """Send a fresh code, or report how long is left before one may be sent.

    The wait is kept on the server as well as in the app: the app's own timer
    is a courtesy, and this is what actually stops a number being messaged
    over and over.
    """
    if not whatsapp_service.is_configured():
        raise HTTPException(status_code=503, detail="WhatsApp sign-in is not available right now.")

    record = await db["otps"].find_one({"phone": phone})
    if record:
        sent_at = as_utc(record.get("sent_at"))
        if sent_at:
            waited = (now_utc() - sent_at).total_seconds()
            if waited < PHONE_RESEND_SECONDS:
                raise HTTPException(
                    status_code=429,
                    detail=f"Please wait {int(PHONE_RESEND_SECONDS - waited)}s before asking for another code.",
                )

    otp = str(random.randint(100000, 999999))
    try:
        await whatsapp_service.send_otp_whatsapp(phone, otp)
    except whatsapp_service.WhatsAppError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    await db["otps"].update_one(
        {"phone": phone},
        {"$set": {
            "phone": phone,
            "otp": otp,
            "attempts": 0,
            "sent_at": now_utc(),
            "expires_at": now_utc() + timedelta(minutes=OTP_TTL_MINUTES),
        }},
        upsert=True,
    )
    return PHONE_RESEND_SECONDS


async def _consume_phone_otp(db: AsyncIOMotorDatabase, phone: str, otp: str) -> None:
    """Check a code, counting the wrong guesses so it cannot be brute-forced."""
    record = await db["otps"].find_one({"phone": phone})
    if not record:
        raise HTTPException(status_code=400, detail="Ask for a code first.")

    expires_at = as_utc(record.get("expires_at"))
    if expires_at and expires_at < now_utc():
        raise HTTPException(status_code=400, detail="That code has expired. Send a new one.")

    if int(record.get("attempts") or 0) >= PHONE_MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Too many wrong codes. Send a new one.")

    if str(record.get("otp")) != otp.strip():
        await db["otps"].update_one({"phone": phone}, {"$inc": {"attempts": 1}})
        raise HTTPException(status_code=400, detail="That code is not right.")


@router.post("/phone/start", response_model=dict, status_code=201)
async def phone_start(payload: PhoneStartRequest, db: AsyncIOMotorDatabase = Depends(get_database)):
    """Step 1 — send a code to this WhatsApp number."""
    phone = _clean_phone(payload.phone)

    existing = await db[USERS].find_one({"phone": phone, "status": "active"})
    if existing:
        raise HTTPException(
            status_code=409,
            detail="This number already has an account. Please log in with it instead.",
        )

    retry_after = await _send_phone_otp(db, phone)
    return {"message": "A code has been sent to your WhatsApp.", "phone": phone, "retry_after": retry_after}


@router.post("/phone/resend", response_model=dict)
async def phone_resend(payload: PhoneStartRequest, db: AsyncIOMotorDatabase = Depends(get_database)):
    phone = _clean_phone(payload.phone)
    retry_after = await _send_phone_otp(db, phone)
    return {"message": "A new code is on its way.", "retry_after": retry_after}


@router.post("/phone/verify", response_model=dict)
async def phone_verify(payload: PhoneVerifyRequest, db: AsyncIOMotorDatabase = Depends(get_database)):
    """Step 2 — check the code and hand back a short-lived signup token."""
    phone = _clean_phone(payload.phone)
    await _consume_phone_otp(db, phone, payload.otp)
    await db["otps"].delete_one({"phone": phone})
    return {"verified": True, "signup_token": _phone_token_for(phone)}


@router.post("/phone/complete", response_model=AuthResponse)
async def phone_complete(payload: PhoneSignupCompleteRequest, db: AsyncIOMotorDatabase = Depends(get_database)):
    """Step 3 — name and password on a verified number, and they are in."""
    phone = _clean_phone(payload.phone)
    if _phone_from_signup_token(payload.signup_token) != phone:
        raise HTTPException(status_code=401, detail="Verification expired. Please verify your number again.")
    if not payload.name.strip():
        raise HTTPException(status_code=422, detail="Please enter your name.")
    if len(payload.password) < 6:
        raise HTTPException(status_code=422, detail="Password must be at least 6 characters.")

    if await db[USERS].find_one({"phone": phone, "status": "active"}):
        raise HTTPException(status_code=409, detail="This number already has an account.")

    email = (payload.email or "").lower().strip()
    if email:
        if "@" not in email:
            raise HTTPException(status_code=422, detail="Please enter a valid email.")
        if await db[USERS].find_one({"email": email, "status": "active"}):
            raise HTTPException(status_code=409, detail="An account with this email already exists")
    else:
        email = _identity_email(phone)

    doc = {
        "name": payload.name.strip(),
        "email": email,
        "whatsapp": phone,
        "phone": phone,
        "phone_verified": True,
        "email_verified": bool(payload.email),
        "hashed_password": get_password_hash(payload.password),
        "is_premium": False,
        "status": "active",
        "role": "user",
        "created_at": now_utc(),
    }
    await db[USERS].update_one({"email": email}, {"$set": doc}, upsert=True)
    user = await db[USERS].find_one({"email": email})
    return AuthResponse(access_token=_token_for(email), user=_profile(user))


@router.post("/login/phone", response_model=AuthResponse)
async def login_with_phone(payload: PhoneLoginRequest, db: AsyncIOMotorDatabase = Depends(get_database)):
    """Log in with the WhatsApp number and the password set with it."""
    phone = _clean_phone(payload.phone)
    user = await db[USERS].find_one({"phone": phone})
    if not user or not verify_password(payload.password, user.get("hashed_password", "")):
        raise HTTPException(status_code=401, detail="Incorrect number or password")
    if user.get("status") == "blocked":
        raise HTTPException(status_code=403, detail="Account disabled")
    if user.get("status") != "active":
        raise HTTPException(status_code=403, detail="Please finish signing up with this number first.")
    return AuthResponse(access_token=_token_for(user["email"]), user=_profile(user))


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
    await _consume_otp(db, email, payload.otp)

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


@router.delete("/me", response_model=dict)
async def delete_me(
    current: TokenData = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Erase the signed-in user's account and everything attached to it.

    Google Play requires an in-app route to this for any app that lets people
    create an account. What goes: the profile, their submissions and photos'
    references, entitlements, push tokens and any pending OTP. What stays: the
    payment rows — the privacy policy says the fact and amount of a payment is
    kept for the period tax law requires — with the email scrubbed off them so
    they no longer point at a person.
    """
    email = (current.email or "").lower().strip()
    user = await db[USERS].find_one({"email": email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await db.submissions.delete_many({"user_email": email})
    await db["entitlements"].delete_many({"user_email": email})
    await db["push_tokens"].delete_many({"email": email})
    await db["otps"].delete_many({"email": email})
    # Keep the record, drop the person it points at.
    await db["payments"].update_many({"user_email": email}, {"$set": {"user_email": None, "deleted_user": True}})
    await db[USERS].delete_one({"email": email})

    return {"deleted": True}

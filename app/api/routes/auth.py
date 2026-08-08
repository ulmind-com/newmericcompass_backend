"""Admin authentication: login (OAuth2 password flow) and profile."""

import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.core.config import settings
from app.core.database import get_database
from app.core.security import (
    TokenData,
    create_access_token,
    get_current_admin,
    verify_password,
)
from app.schemas.admin import AdminProfile, Token
from pydantic import BaseModel
from datetime import datetime
from app.core.firebase import verify_firebase_token

logger = logging.getLogger(__name__)

router = APIRouter()

ADMINS_COLLECTION = "admins"


@router.post("/login", response_model=Token, summary="Admin login (email + password)")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """Authenticate an admin. The OAuth2 form field ``username`` carries the email."""
    db = get_database()
    admin = await db[ADMINS_COLLECTION].find_one({"email": form_data.username.lower()})

    if not admin or not verify_password(form_data.password, admin.get("hashed_password", "")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not admin.get("is_active", True):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    token = create_access_token(
        data={"sub": admin["email"], "role": admin.get("role", "admin")},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return Token(access_token=token, token_type="bearer")


@router.get("/me", response_model=AdminProfile, summary="Current admin profile")
async def me(current_admin: TokenData = Depends(get_current_admin)):
    db = get_database()
    admin = await db[ADMINS_COLLECTION].find_one({"email": current_admin.email})
    return AdminProfile(
        email=current_admin.email,
        name=(admin or {}).get("name"),
        role=current_admin.role or "admin",
    )

class GoogleLoginRequest(BaseModel):
    id_token: str

@router.post("/google", summary="User login via Firebase Google Auth")
async def google_login(request: GoogleLoginRequest):
    """Authenticates a user via Google Firebase ID Token."""
    decoded_token = verify_firebase_token(request.id_token)
    
    if not decoded_token:
        raise HTTPException(status_code=401, detail="Invalid Firebase ID token")

    email = decoded_token.get("email")
    name = decoded_token.get("name", "Unknown User")
    uid = decoded_token.get("uid")

    if not email:
        raise HTTPException(status_code=400, detail="Google account has no email")

    db = get_database()
    
    # Check if user exists
    user = await db.users.find_one({"email": email})
    
    if not user:
        # Create new user
        new_user = {
            "email": email,
            "name": name,
            "firebase_uid": uid,
            "created_at": datetime.utcnow(),
            "role": "user",
            "is_premium": False,
            "status": "active"
        }
        result = await db.users.insert_one(new_user)
        user_id = str(result.inserted_id)
        role = "user"
    else:
        # Update existing user if needed
        user_id = str(user["_id"])
        role = user.get("role", "user")
        
        # Check if they are blocked
        if user.get("status") == "blocked":
            raise HTTPException(status_code=403, detail="User account is blocked")

    # Generate our internal JWT token
    access_token = create_access_token(data={"sub": email, "role": role, "user_id": user_id})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user_id,
            "email": email,
            "name": name,
            "role": role
        }
    }

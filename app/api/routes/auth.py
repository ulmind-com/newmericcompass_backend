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

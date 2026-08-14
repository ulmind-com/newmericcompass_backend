from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class UserRegister(BaseModel):
    name: str
    email: str
    password: str
    whatsapp: Optional[str] = None


class UserLogin(BaseModel):
    email: str
    password: str


class UserProfile(BaseModel):
    id: str
    name: str
    email: str
    whatsapp: Optional[str] = None
    phone: Optional[str] = None
    is_premium: bool = False
    status: str = "active"
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class UserUpdate(BaseModel):
    name: Optional[str] = None
    whatsapp: Optional[str] = None
    phone: Optional[str] = None


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserProfile

class VerifyOTPRequest(BaseModel):
    email: str
    otp: str

class SignupStartRequest(BaseModel):
    """Step 1 of the email-first signup: just the email, to receive an OTP."""
    email: str

class SignupCompleteRequest(BaseModel):
    """Final step: a signup_token (from a verified OTP) plus the new profile."""
    email: str
    name: str
    password: str
    whatsapp: Optional[str] = None
    signup_token: str

class ResendOTPRequest(BaseModel):
    email: str

class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    email: str
    otp: str
    new_password: str

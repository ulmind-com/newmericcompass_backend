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
    #: An email added and verified after signing up with a number. The account
    #: is still keyed on `email`; this is the address the person actually uses.
    contact_email: Optional[str] = None
    phone_verified: bool = False
    email_verified: bool = False
    is_premium: bool = False
    status: str = "active"
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class UserUpdate(BaseModel):
    """What a user may change on their own.

    Not the number and not the email: both are how someone gets back into the
    account, so they only change through a code sent to them.
    """
    name: Optional[str] = None


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


# --- WhatsApp (mobile) signup and login -------------------------------------

class PhoneStartRequest(BaseModel):
    """Step 1 of the mobile signup: the number a code should go to."""
    phone: str


class PhoneVerifyRequest(BaseModel):
    phone: str
    otp: str


class PhoneSignupCompleteRequest(BaseModel):
    """Final step: the token from a verified code, plus the new profile.

    An email may be added here, but only with its own verification token —
    anyone can type an address they do not own.
    """
    phone: str
    name: str
    password: str
    email: Optional[str] = None
    email_token: Optional[str] = None
    signup_token: str


class PhoneLoginRequest(BaseModel):
    phone: str
    password: str

class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    email: str
    otp: str
    new_password: str


class ContactStartRequest(BaseModel):
    """Add or change the signed-in user's own email or number: step 1."""
    value: str


class ContactVerifyRequest(BaseModel):
    value: str
    otp: str

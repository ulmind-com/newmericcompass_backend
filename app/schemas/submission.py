from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class SubmissionItem(BaseModel):
    category_slug: str
    category_name: Optional[str] = None
    degree: float = Field(ge=0, le=360)
    pada_code: Optional[str] = None
    direction16: Optional[str] = None
    verdict: Optional[str] = None
    images: List[str] = Field(default_factory=list)  # Cloudinary URLs of the user's photos
    # Where the photo was taken, captured from the device at shutter time.
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    accuracy: Optional[float] = None


class SubmissionCreate(BaseModel):
    device_id: Optional[str] = None
    title: Optional[str] = "My Property"
    # Contact (from the logged-in user's profile) + property location.
    name: Optional[str] = None
    whatsapp: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    items: List[SubmissionItem] = Field(default_factory=list)


class SubmissionResponse(BaseModel):
    id: str
    device_id: Optional[str] = None
    title: Optional[str] = None
    name: Optional[str] = None
    whatsapp: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    user_email: Optional[str] = None
    status: Optional[str] = "new"
    items: List[SubmissionItem]
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

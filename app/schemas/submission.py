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


class SubmissionCreate(BaseModel):
    device_id: Optional[str] = None
    title: Optional[str] = "My Property"
    items: List[SubmissionItem] = Field(default_factory=list)


class SubmissionResponse(BaseModel):
    id: str
    device_id: Optional[str] = None
    title: Optional[str] = None
    items: List[SubmissionItem]
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class TipBase(BaseModel):
    title: str
    body: str
    category_slug: Optional[str] = None
    image_url: Optional[str] = None
    order: int = 0
    is_active: bool = True


class TipCreate(TipBase):
    # Adding a tip is the moment worth telling people about, so this defaults
    # on; the admin can uncheck it for a correction or a backfill.
    notify: bool = True


class TipUpdate(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    category_slug: Optional[str] = None
    image_url: Optional[str] = None
    order: Optional[int] = None
    is_active: Optional[bool] = None


class TipResponse(TipBase):
    id: str
    notified_at: Optional[datetime] = None
    notified_count: Optional[int] = None
    model_config = ConfigDict(from_attributes=True)

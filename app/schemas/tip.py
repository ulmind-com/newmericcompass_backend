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
    pass


class TipUpdate(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    category_slug: Optional[str] = None
    image_url: Optional[str] = None
    order: Optional[int] = None
    is_active: Optional[bool] = None


class TipResponse(TipBase):
    id: str
    model_config = ConfigDict(from_attributes=True)

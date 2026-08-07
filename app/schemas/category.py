from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class CategoryBase(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9-]+$", description="URL-safe unique key, e.g. 'main-entrance'")
    name: str
    icon_url: Optional[str] = None
    icon_key: Optional[str] = None  # local icon identifier used by the app
    order: int = 0
    is_active: bool = True


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    icon_url: Optional[str] = None
    icon_key: Optional[str] = None
    order: Optional[int] = None
    is_active: Optional[bool] = None


class CategoryResponse(CategoryBase):
    id: str
    model_config = ConfigDict(from_attributes=True)

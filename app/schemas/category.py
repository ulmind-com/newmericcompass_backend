from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


from typing import List


class CategoryBase(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9-]+$", description="URL-safe unique key, e.g. 'main-entrance'")
    name: str
    icon_url: Optional[str] = None
    icon_key: Optional[str] = None  # local icon identifier used by the app
    order: int = 0
    is_active: bool = True
    # 16-wind direction codes (e.g. ["NW","W"]) the vastu expert marks as the
    # ideal / to-avoid placement for this category. Drives the compass guidance.
    best_directions: List[str] = Field(default_factory=list)
    avoid_directions: List[str] = Field(default_factory=list)


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    icon_url: Optional[str] = None
    icon_key: Optional[str] = None
    order: Optional[int] = None
    is_active: Optional[bool] = None
    best_directions: Optional[List[str]] = None
    avoid_directions: Optional[List[str]] = None


class CategoryResponse(CategoryBase):
    id: str
    model_config = ConfigDict(from_attributes=True)

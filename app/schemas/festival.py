"""Seasonal themes — Independence Day, Republic Day, Diwali, a sale week.

The admin owns all of it: the dates it runs between, the colours it paints the
app in, and what the banner says. Nothing about a festival is compiled into the
app, so a new one is a panel entry rather than a release.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class FestivalBase(BaseModel):
    name: str
    starts_at: datetime
    ends_at: datetime
    # The kill switch. Dates decide *when*; this decides *whether* — so a
    # festival can be pulled without editing its dates and losing them.
    is_active: bool = True

    # Two or three stops. The app paints its headers with these.
    header_colors: List[str] = Field(default_factory=lambda: ["#4FC182", "#2E9E5B", "#186B3D"])
    accent: Optional[str] = None          # buttons and highlights during the run

    banner_title: Optional[str] = None
    banner_subtitle: Optional[str] = None
    banner_image_url: Optional[str] = None
    banner_emoji: Optional[str] = None


class FestivalCreate(FestivalBase):
    pass


class FestivalUpdate(BaseModel):
    name: Optional[str] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    is_active: Optional[bool] = None
    header_colors: Optional[List[str]] = None
    accent: Optional[str] = None
    banner_title: Optional[str] = None
    banner_subtitle: Optional[str] = None
    banner_image_url: Optional[str] = None
    banner_emoji: Optional[str] = None


class FestivalResponse(FestivalBase):
    id: str
    model_config = ConfigDict(from_attributes=True)

"""The day-wise remedial protocol: what to actually do, on which day.

Each weekday is governed by a planet and gets an objective, a checklist of
practical actions, and the reasoning behind them. All of it is admin-editable —
the seed only supplies the owner's starting text.
"""

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class DayProtocolBase(BaseModel):
    # 0 = Monday, matching Python's weekday() so "today" needs no lookup table.
    weekday: int = Field(ge=0, le=6)
    day_name: str
    planet: str
    energy: str                       # e.g. "Moon Energy"
    objective: str
    actions: List[str] = Field(default_factory=list)
    deep_logic: Optional[str] = None
    focus_zones: List[str] = Field(default_factory=list)   # 8-wind codes the day works on
    color: str = "#FF6A00"
    is_active: bool = True


class DayProtocolCreate(DayProtocolBase):
    pass


class DayProtocolUpdate(BaseModel):
    day_name: Optional[str] = None
    planet: Optional[str] = None
    energy: Optional[str] = None
    objective: Optional[str] = None
    actions: Optional[List[str]] = None
    deep_logic: Optional[str] = None
    focus_zones: Optional[List[str]] = None
    color: Optional[str] = None
    is_active: Optional[bool] = None


class DayProtocolResponse(DayProtocolBase):
    id: str
    model_config = ConfigDict(from_attributes=True)

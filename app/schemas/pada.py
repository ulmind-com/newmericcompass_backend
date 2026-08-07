from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, ConfigDict


class Verdict(StrEnum):
    EXCELLENT = "excellent"
    GOOD = "good"
    AVERAGE = "average"
    BAD = "bad"


class PadaBase(BaseModel):
    code: str
    index: int
    quadrant: str
    quadrant_index: int
    center_deg: float
    start_deg: float
    end_deg: float
    direction16: str
    direction16_full: str
    direction8: str
    name: Optional[str] = None
    element: Optional[str] = None
    dosha: Optional[str] = None
    organ: Optional[str] = None
    life_aspect: Optional[str] = None
    nakshatra: Optional[str] = None
    default_verdict: Verdict = Verdict.AVERAGE
    description: Optional[str] = None
    is_active: bool = True


class PadaResponse(PadaBase):
    id: str
    model_config = ConfigDict(from_attributes=True)


class PadaUpdate(BaseModel):
    """Admin-editable attributes of a pada (structural fields stay fixed)."""

    name: Optional[str] = None
    element: Optional[str] = None
    dosha: Optional[str] = None
    organ: Optional[str] = None
    life_aspect: Optional[str] = None
    nakshatra: Optional[str] = None
    default_verdict: Optional[Verdict] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

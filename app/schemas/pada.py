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
    color: Optional[str] = None
    # entrance pada: presiding deity (name), its challenges and its ranking
    entrance_challenge: Optional[str] = None
    entrance_rating: Optional[str] = None
    entrance_rating_label: Optional[str] = None
    entrance_rating_category: Optional[str] = None
    entrance_rating_color: Optional[str] = None
    # printed-chart ring colours
    life_color: Optional[str] = None
    dir_color: Optional[str] = None
    dir_text_color: Optional[str] = None
    pada_color: Optional[str] = None
    devata_color: Optional[str] = None
    nakshatra_color: Optional[str] = None
    brahma_name: Optional[str] = None
    brahma_color: Optional[str] = None
    # 7D NEXUS master code
    corner: Optional[str] = None
    lord: Optional[str] = None
    deity_english: Optional[str] = None
    vastu_association: Optional[str] = None
    planet: Optional[str] = None
    metal: Optional[str] = None
    shape: Optional[str] = None
    day: Optional[str] = None
    self_colour: Optional[str] = None
    destruct_colour: Optional[str] = None
    enhance_colour: Optional[str] = None
    exhaust_colour: Optional[str] = None
    acceptable_colour: Optional[str] = None
    relationship: Optional[str] = None
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
    color: Optional[str] = None
    entrance_challenge: Optional[str] = None
    entrance_rating: Optional[str] = None
    entrance_rating_label: Optional[str] = None
    entrance_rating_category: Optional[str] = None
    entrance_rating_color: Optional[str] = None
    life_color: Optional[str] = None
    dir_color: Optional[str] = None
    dir_text_color: Optional[str] = None
    pada_color: Optional[str] = None
    devata_color: Optional[str] = None
    nakshatra_color: Optional[str] = None
    brahma_name: Optional[str] = None
    brahma_color: Optional[str] = None
    corner: Optional[str] = None
    lord: Optional[str] = None
    deity_english: Optional[str] = None
    vastu_association: Optional[str] = None
    planet: Optional[str] = None
    metal: Optional[str] = None
    shape: Optional[str] = None
    day: Optional[str] = None
    self_colour: Optional[str] = None
    destruct_colour: Optional[str] = None
    enhance_colour: Optional[str] = None
    exhaust_colour: Optional[str] = None
    acceptable_colour: Optional[str] = None
    relationship: Optional[str] = None
    default_verdict: Optional[Verdict] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

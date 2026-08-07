from enum import StrEnum
from typing import Literal, Optional

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, field_validator


class Direction(StrEnum):
    NORTH = "North"
    NORTH_EAST = "North-East"
    EAST = "East"
    SOUTH_EAST = "South-East"
    SOUTH = "South"
    SOUTH_WEST = "South-West"
    WEST = "West"
    NORTH_WEST = "North-West"


class RoomType(StrEnum):
    KITCHEN = "Kitchen"
    MASTER_BEDROOM = "Master Bedroom"
    TOILET = "Toilet"
    ENTRANCE = "Entrance"
    PUJA_ROOM = "Puja Room"


class VastuStatus(StrEnum):
    EXCELLENT = "Excellent"
    GOOD = "Good"
    AVERAGE = "Average"
    MAJOR_DOSH = "Major Dosh"


RemedyType = Literal["Structural", "Color", "Object Placement", "Behavioral"]


class Remedy(BaseModel):
    """A theoretical corrective measure for a Vastu dosh."""

    title: str
    description: str
    remedy_type: RemedyType = "Object Placement"


class VastuRuleBase(BaseModel):
    """Shape shared by every Vastu rule document, independent of storage concerns."""

    room_type: RoomType
    direction: Direction
    score: int = Field(ge=0, le=100)
    status: VastuStatus
    remedy: Optional[Remedy] = None
    notes: Optional[str] = None


class VastuRuleInDB(VastuRuleBase):
    """Represents a `vastu_rules` document as read back from MongoDB."""

    id: str = Field(alias="_id")

    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

    @field_validator("id", mode="before")
    @classmethod
    def stringify_object_id(cls, value: object) -> str:
        return str(value) if isinstance(value, ObjectId) else value


class VastuAnalysisRequest(BaseModel):
    """Payload for `POST /api/vastu/analyze`."""

    property_id: str
    room_type: RoomType
    degree: float = Field(
        ge=0,
        le=360,
        description="Compass bearing of the room, measured clockwise from magnetic North (0-360).",
    )

    @field_validator("property_id")
    @classmethod
    def validate_property_id(cls, value: str) -> str:
        if not ObjectId.is_valid(value):
            raise ValueError("property_id must be a valid MongoDB ObjectId")
        return value


class VastuAnalysisResponse(BaseModel):
    """Response for `POST /api/vastu/analyze`."""

    property_id: str
    room_type: RoomType
    input_degree: float
    calculated_direction: Direction
    score: int
    status: VastuStatus
    remedy: Optional[Remedy] = None
    notes: Optional[str] = None

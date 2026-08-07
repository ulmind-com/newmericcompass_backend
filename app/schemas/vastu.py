"""Public Vastu lookup request/response schemas (32-pada N5 engine)."""

from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.pada import PadaBase, Verdict


class VastuLookupRequest(BaseModel):
    category: str = Field(description="Category slug, e.g. 'toilet'")
    degree: float = Field(ge=0, le=360, description="Compass bearing clockwise from North (0-360)")


class VastuLookupResponse(BaseModel):
    category: str
    degree: float
    pada: PadaBase
    direction16: str
    direction16_full: str
    verdict: Verdict
    score: int
    effects: List[str]
    treatments: List[str]
    notes: Optional[str] = None
    # True when the verdict came from a category-specific rule; False when it
    # was synthesized from the pada's default so the app never gets an empty result.
    is_configured: bool

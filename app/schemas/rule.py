from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.pada import Verdict


class RuleBase(BaseModel):
    """A Vastu verdict for a specific category placed in a specific pada."""

    category_slug: str
    pada_code: str
    verdict: Verdict = Verdict.AVERAGE
    score: int = Field(default=50, ge=0, le=100)
    effects: List[str] = Field(default_factory=list, description="Bullet points shown in the Effects tab")
    treatments: List[str] = Field(default_factory=list, description="Bullet points shown in the Treatment tab")
    notes: Optional[str] = None
    is_active: bool = True


class RuleCreate(RuleBase):
    pass


class RuleUpdate(BaseModel):
    verdict: Optional[Verdict] = None
    score: Optional[int] = Field(default=None, ge=0, le=100)
    effects: Optional[List[str]] = None
    treatments: Optional[List[str]] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class RuleResponse(RuleBase):
    id: str
    model_config = ConfigDict(from_attributes=True)

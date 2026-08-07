from pydantic import BaseModel, ConfigDict
from typing import Optional

class VastuRuleBase(BaseModel):
    room: str
    direction: str
    score: int
    status: str = "active"
    remedy: Optional[str] = None

class VastuRuleCreate(VastuRuleBase):
    pass

class VastuRuleUpdate(BaseModel):
    score: Optional[int] = None
    status: Optional[str] = None
    remedy: Optional[str] = None

class VastuRuleResponse(VastuRuleBase):
    id: str

    model_config = ConfigDict(from_attributes=True)

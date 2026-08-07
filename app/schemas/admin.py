from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None
    role: Optional[str] = None

class AdminLogin(BaseModel):
    email: EmailStr
    password: str

class DashboardStats(BaseModel):
    total_users: int
    total_scans: int
    premium_users: int
    revenue: float

class UserOverview(BaseModel):
    id: str
    email: str
    name: str
    created_at: datetime
    is_premium: bool
    status: str

class PaginatedUsersResponse(BaseModel):
    users: List[UserOverview]
    total_count: int
    page: int
    page_size: int

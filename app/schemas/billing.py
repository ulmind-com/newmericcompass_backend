"""Plans, entitlements and payments.

Three things the app charges for, each identified by a *feature* key:
  submissions - a subscription; how many placement reports it allows and for
                how long is entirely up to the plan
  analysis    - one-time unlock of the Analysis screen
  nexus       - one-time unlock of the 7D Nexus screen

Nothing about pricing, duration or quota is hardcoded: the admin creates and
edits plans, and can also grant any feature to a user for free.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class Feature(StrEnum):
    SUBMISSIONS = "submissions"
    ANALYSIS = "analysis"
    NEXUS = "nexus"


class PlanKind(StrEnum):
    SUBSCRIPTION = "subscription"
    ONE_TIME = "one_time"


class PlanBase(BaseModel):
    slug: str
    feature: Feature
    kind: PlanKind
    name: str
    description: Optional[str] = None
    # Stored in paise, the unit Razorpay works in, so no rounding ever creeps in.
    amount: int = Field(ge=0)
    currency: str = "INR"
    # None means lifetime.
    duration_days: Optional[int] = Field(default=None, ge=1)
    # None means unlimited submissions.
    submission_quota: Optional[int] = Field(default=None, ge=1)
    is_popular: bool = False
    is_active: bool = True
    order: int = 0


class PlanCreate(PlanBase):
    pass


class PlanUpdate(BaseModel):
    feature: Optional[Feature] = None
    kind: Optional[PlanKind] = None
    name: Optional[str] = None
    description: Optional[str] = None
    amount: Optional[int] = Field(default=None, ge=0)
    currency: Optional[str] = None
    duration_days: Optional[int] = None
    submission_quota: Optional[int] = None
    is_popular: Optional[bool] = None
    is_active: Optional[bool] = None
    order: Optional[int] = None


class PlanResponse(PlanBase):
    id: str
    model_config = ConfigDict(from_attributes=True)


class EntitlementSource(StrEnum):
    PAYMENT = "payment"
    ADMIN = "admin"


class EntitlementResponse(BaseModel):
    id: str
    user_email: str
    feature: Feature
    plan_slug: Optional[str] = None
    plan_name: Optional[str] = None
    source: EntitlementSource
    payment_id: Optional[str] = None
    granted_at: datetime
    expires_at: Optional[datetime] = None
    quota_total: Optional[int] = None
    quota_used: int = 0
    is_active: bool = True
    note: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class FeatureAccess(BaseModel):
    """What the app needs to decide whether to show a screen or a paywall."""

    feature: Feature
    allowed: bool
    source: Optional[EntitlementSource] = None
    plan_name: Optional[str] = None
    expires_at: Optional[datetime] = None
    quota_total: Optional[int] = None
    quota_used: int = 0
    quota_left: Optional[int] = None
    reason: Optional[str] = None


class MyAccessResponse(BaseModel):
    email: str
    features: List[FeatureAccess]


class OrderCreate(BaseModel):
    plan_slug: str


class OrderResponse(BaseModel):
    order_id: str
    amount: int
    currency: str
    key_id: str
    plan_slug: str
    plan_name: str
    feature: Feature
    checkout_url: str
    prefill_name: Optional[str] = None
    prefill_email: Optional[str] = None
    prefill_contact: Optional[str] = None


class PaymentVerify(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class PaymentResponse(BaseModel):
    id: str
    user_email: str
    user_name: Optional[str] = None
    user_contact: Optional[str] = None
    plan_slug: str
    plan_name: str
    feature: Feature
    kind: PlanKind
    amount: int
    currency: str
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: Optional[str] = None
    method: Optional[str] = None
    status: str = "paid"
    razorpay_raw: Optional[dict[str, Any]] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class AdminGrant(BaseModel):
    """Give a user a feature without a payment."""

    email: str
    feature: Feature
    duration_days: Optional[int] = None   # None -> lifetime
    submission_quota: Optional[int] = None  # None -> unlimited
    note: Optional[str] = None


class RevenueBucket(BaseModel):
    key: str
    label: Optional[str] = None
    amount: int = 0
    count: int = 0


class RevenueReport(BaseModel):
    currency: str = "INR"
    total_amount: int = 0
    total_payments: int = 0
    today_amount: int = 0
    month_amount: int = 0
    paying_users: int = 0
    by_feature: List[RevenueBucket] = Field(default_factory=list)
    by_plan: List[RevenueBucket] = Field(default_factory=list)
    by_month: List[RevenueBucket] = Field(default_factory=list)

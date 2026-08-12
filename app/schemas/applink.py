"""Links and share settings the side menu shows, all owned by the admin.

Two sections, one collection:
  essentials - the owner's Vastu videos on YouTube / Facebook
  social     - the follow-us row (Facebook, Instagram, YouTube, WhatsApp)

Nothing here is compiled into the app, so a new video or a changed handle is a
panel edit rather than a release.
"""

from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, ConfigDict


class LinkSection(StrEnum):
    ESSENTIALS = "essentials"
    SOCIAL = "social"


class Platform(StrEnum):
    YOUTUBE = "youtube"
    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"
    WHATSAPP = "whatsapp"
    WEB = "web"


class AppLinkBase(BaseModel):
    section: LinkSection
    platform: Platform
    title: str
    subtitle: Optional[str] = None
    url: str
    thumbnail_url: Optional[str] = None
    order: int = 0
    is_active: bool = True


class AppLinkCreate(AppLinkBase):
    pass


class AppLinkUpdate(BaseModel):
    section: Optional[LinkSection] = None
    platform: Optional[Platform] = None
    title: Optional[str] = None
    subtitle: Optional[str] = None
    url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    order: Optional[int] = None
    is_active: Optional[bool] = None


class AppLinkResponse(AppLinkBase):
    id: str
    model_config = ConfigDict(from_attributes=True)


class ShareSettings(BaseModel):
    """Sharing the app, and when to ask for a review.

    The prompt is gated on the user having paid and actually used the app,
    because asking a stranger for five stars is how you get one.
    """

    message: str = "Check out Newmeric Compass — a proper N5 Vastu compass in your pocket."
    android_url: str = ""
    ios_url: str = ""
    website_url: str = ""
    review_after_days: int = 3
    review_after_opens: int = 5
    review_requires_purchase: bool = True

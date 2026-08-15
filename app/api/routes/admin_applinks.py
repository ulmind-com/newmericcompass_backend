"""Admin CRUD for the side-menu links and the share / review settings."""

import html as _html
import re
from urllib.parse import urlparse

import httpx
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.database import get_database
from app.core.security import TokenData, get_current_active_admin
from app.schemas.applink import (
    AppLinkCreate, AppLinkResponse, AppLinkUpdate, LinkPreviewRequest, LinkPreviewResponse, ShareSettings,
)
from app.schemas.common import now_utc, serialize_doc, serialize_docs

router = APIRouter()

LINKS = "app_links"
SETTINGS = "app_settings"
SHARE_ID = "share"

# A bot user-agent: sites (Facebook especially) serve the same Open Graph card
# they give link-preview crawlers like WhatsApp, rather than a login wall.
_PREVIEW_UA = "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)"
_META_TAG = re.compile(r"<meta\b[^>]*>", re.I)
_ATTR = re.compile(r'([\w:-]+)\s*=\s*"([^"]*)"|' r"([\w:-]+)\s*=\s*'([^']*)'")
_TITLE_TAG = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)


def _oid(value: str) -> ObjectId:
    if not ObjectId.is_valid(value):
        raise HTTPException(status_code=400, detail="Invalid id")
    return ObjectId(value)


def _detect_platform(url: str) -> str:
    host = (urlparse(url).netloc or "").lower()
    if "youtube.com" in host or "youtu.be" in host:
        return "youtube"
    if "facebook.com" in host or "fb.watch" in host or "fb.com" in host:
        return "facebook"
    if "instagram.com" in host:
        return "instagram"
    if "wa.me" in host or "whatsapp.com" in host:
        return "whatsapp"
    return "web"


def _meta(html_text: str, keys: set[str]) -> str | None:
    """First <meta> whose property/name matches one of `keys`, returning its content."""
    for tag in _META_TAG.findall(html_text):
        attrs: dict[str, str] = {}
        for m in _ATTR.finditer(tag):
            name = (m.group(1) or m.group(3) or "").lower()
            val = m.group(2) if m.group(2) is not None else m.group(4)
            if name:
                attrs[name] = val or ""
        key = attrs.get("property") or attrs.get("name")
        if key and key.lower() in keys and attrs.get("content"):
            return _html.unescape(attrs["content"]).strip()
    return None


async def _scrape_og(url: str) -> dict:
    async with httpx.AsyncClient(follow_redirects=True, timeout=12.0) as client:
        res = await client.get(url, headers={"User-Agent": _PREVIEW_UA, "Accept-Language": "en"})
        text = res.text
    title = _meta(text, {"og:title", "twitter:title"})
    if not title:
        m = _TITLE_TAG.search(text)
        title = _html.unescape(m.group(1)).strip() if m else None
    return {
        "title": title,
        "image": _meta(text, {"og:image", "og:image:url", "twitter:image", "twitter:image:src"}),
        "description": _meta(text, {"og:description", "twitter:description", "description"}),
        "site_name": _meta(text, {"og:site_name"}),
    }


@router.post("/link-preview", response_model=LinkPreviewResponse, summary="Fetch a link's rich preview")
async def link_preview(
    payload: LinkPreviewRequest,
    _: TokenData = Depends(get_current_active_admin),
):
    """Scrape Open Graph / oEmbed data from a pasted URL to pre-fill the add-link form."""
    url = payload.url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    platform = _detect_platform(url)

    title = image = subtitle = site_name = None
    try:
        if platform == "youtube":
            async with httpx.AsyncClient(timeout=12.0) as client:
                r = await client.get(
                    "https://www.youtube.com/oembed", params={"url": url, "format": "json"}
                )
                if r.status_code == 200:
                    d = r.json()
                    title, image, subtitle = d.get("title"), d.get("thumbnail_url"), d.get("author_name")
        if not title or not image:
            og = await _scrape_og(url)
            title = title or og.get("title")
            image = image or og.get("image")
            site_name = og.get("site_name")
            subtitle = subtitle or site_name or og.get("description")
    except Exception:
        # Best-effort — return whatever we have (possibly just the platform) and
        # let the admin fill the rest in by hand.
        pass

    if subtitle and len(subtitle) > 120:
        subtitle = subtitle[:117].rstrip() + "…"
    return LinkPreviewResponse(
        platform=platform, title=title, subtitle=subtitle, thumbnail_url=image, site_name=site_name,
    )


@router.get("/links", response_model=list[AppLinkResponse], summary="All menu links")
async def list_links(
    _: TokenData = Depends(get_current_active_admin),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    cursor = db[LINKS].find({}).sort([("section", 1), ("order", 1)])
    return serialize_docs(await cursor.to_list(length=500))


@router.post("/links", response_model=AppLinkResponse, status_code=201, summary="Add a link")
async def create_link(
    payload: AppLinkCreate,
    _: TokenData = Depends(get_current_active_admin),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    doc = payload.model_dump()
    doc["created_at"] = now_utc()
    result = await db[LINKS].insert_one(doc)
    doc["_id"] = result.inserted_id
    return serialize_doc(doc)


@router.put("/links/{link_id}", response_model=AppLinkResponse, summary="Update a link")
async def update_link(
    link_id: str,
    payload: AppLinkUpdate,
    _: TokenData = Depends(get_current_active_admin),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    changes = payload.model_dump(exclude_unset=True)
    if changes:
        changes["updated_at"] = now_utc()
        await db[LINKS].update_one({"_id": _oid(link_id)}, {"$set": changes})
    doc = await db[LINKS].find_one({"_id": _oid(link_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Link not found")
    return serialize_doc(doc)


@router.delete("/links/{link_id}", status_code=204, summary="Delete a link")
async def delete_link(
    link_id: str,
    _: TokenData = Depends(get_current_active_admin),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    await db[LINKS].delete_one({"_id": _oid(link_id)})


@router.get("/share", response_model=ShareSettings, summary="Share & review settings")
async def get_share(
    _: TokenData = Depends(get_current_active_admin),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    doc = await db[SETTINGS].find_one({"_id": SHARE_ID}) or {}
    doc.pop("_id", None)
    return ShareSettings(**doc)


@router.put("/share", response_model=ShareSettings, summary="Update share & review settings")
async def update_share(
    payload: ShareSettings,
    _: TokenData = Depends(get_current_active_admin),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    await db[SETTINGS].update_one({"_id": SHARE_ID}, {"$set": payload.model_dump()}, upsert=True)
    return payload

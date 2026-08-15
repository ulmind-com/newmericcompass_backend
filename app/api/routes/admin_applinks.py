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
# Facebook serves its Open Graph card to link crawlers but a login wall to a
# plain browser — yet for some reels the crawler page omits og:image while the
# browser page keeps the thumbnail in its markup. So we try both and take the
# best of the two, plus a couple of non-OG fallbacks.
_CRAWLER_UA = "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)"
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)
_META_TAG = re.compile(r"<meta\b[^>]*>", re.I)
_ATTR = re.compile(r'([\w:-]+)\s*=\s*"([^"]*)"|' r"([\w:-]+)\s*=\s*'([^']*)'")
_TITLE_TAG = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_IMAGE_SRC = re.compile(r'<link[^>]+rel=["\']image_src["\'][^>]+href=["\']([^"\']+)', re.I)
# Last resort: a real *content* thumbnail in the page. Deliberately excludes
# Facebook's chrome CDN (static.*/rsrc.php — logos and icons), which a looser
# pattern would otherwise grab off a login wall.
_CDN_IMAGE = re.compile(
    r'https?://[^"\'\\ )]*?(?:scontent[\w.-]*\.fbcdn\.net|ytimg\.com|cdninstagram\.com)'
    r'[^"\'\\ )]+?\.(?:jpg|jpeg|png|webp)',
    re.I,
)
_IMG_KEYS = {"og:image", "og:image:url", "og:image:secure_url", "twitter:image", "twitter:image:src"}
# Facebook sometimes answers a crawler with its login page instead of the reel.
_LOGIN_WALL = re.compile(r"\blog in\b|\bsign up\b|log into facebook|you must log in", re.I)


def _looks_walled(title: str | None) -> bool:
    return bool(title and _LOGIN_WALL.search(title))


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


def _find_image(text: str) -> str | None:
    """og:image and friends, then <link rel=image_src>, then any CDN image URL."""
    img = _meta(text, _IMG_KEYS)
    if img:
        return img
    m = _IMAGE_SRC.search(text)
    if m:
        return _html.unescape(m.group(1))
    m = _CDN_IMAGE.search(text)
    return _html.unescape(m.group(0)) if m else None


async def _scrape_og(url: str) -> dict:
    """Read title + image robustly.

    Facebook flip-flops between the real Open Graph card and a login wall, so we
    try a few times across two user-agents, ignore anything that came back as a
    login page, and keep the best real values we saw.
    """
    out = {"title": None, "image": None, "description": None, "site_name": None}
    # crawler, browser, then crawler again — cheap retries beat FB's flakiness.
    attempts = (_CRAWLER_UA, _BROWSER_UA, _CRAWLER_UA)

    async with httpx.AsyncClient(follow_redirects=True, timeout=12.0) as client:
        for ua in attempts:
            try:
                res = await client.get(
                    url,
                    headers={
                        "User-Agent": ua,
                        "Accept-Language": "en-US,en;q=0.9",
                        "Accept": "text/html,application/xhtml+xml",
                    },
                )
                text = res.text
            except Exception:
                continue

            title = _meta(text, {"og:title", "twitter:title"})
            if not title:
                m = _TITLE_TAG.search(text)
                title = _html.unescape(m.group(1)).strip() if m else None
            if _looks_walled(title):
                continue  # a login page — try again, don't keep its title/image

            if not out["title"]:
                out["title"] = title
            if not out["image"]:
                out["image"] = _find_image(text)
            if not out["description"]:
                out["description"] = _meta(text, {"og:description", "twitter:description", "description"})
            if not out["site_name"]:
                out["site_name"] = _meta(text, {"og:site_name"})

            if out["title"] and out["image"]:
                break  # got everything we need
    return out


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

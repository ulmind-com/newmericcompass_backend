"""Logged-in app users upload property photos (stored on Cloudinary)."""

import filetype
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.core.security import TokenData, get_current_user
from app.services.cloudinary_service import upload_image

router = APIRouter()

_MAX_BYTES = 8 * 1024 * 1024  # 8 MB
_ALLOWED = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}


@router.post("/image", summary="Upload a property photo, returns a hosted URL")
async def upload(file: UploadFile = File(...), _: TokenData = Depends(get_current_user)):
    content = await file.read()
    if len(content) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 8 MB)")
    kind = filetype.guess(content)
    mime = kind.mime if kind else (file.content_type or "")
    if mime not in _ALLOWED:
        raise HTTPException(status_code=415, detail=f"Unsupported image type: {mime or 'unknown'}")
    url = await upload_image(content, file.filename or "photo", folder="submissions")
    if not url:
        raise HTTPException(status_code=502, detail="Image upload failed (check Cloudinary config)")
    return {"url": url}

"""Admin: image upload to Cloudinary (used for category icons, tip images)."""

import filetype
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.core.security import TokenData, get_current_admin
from app.services.cloudinary_service import upload_image

router = APIRouter()

_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
_ALLOWED = {"image/jpeg", "image/png", "image/webp", "image/svg+xml"}


@router.post("/image", summary="Upload an image, returns a hosted URL")
async def upload(
    file: UploadFile = File(...),
    folder: str = "newmericcompass",
    _: TokenData = Depends(get_current_admin),
):
    content = await file.read()
    if len(content) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 5 MB)")

    kind = filetype.guess(content)
    mime = kind.mime if kind else (file.content_type or "")
    if mime not in _ALLOWED:
        raise HTTPException(status_code=415, detail=f"Unsupported image type: {mime or 'unknown'}")

    url = await upload_image(content, file.filename or "upload", folder=folder)
    if not url:
        raise HTTPException(status_code=502, detail="Image upload failed (check Cloudinary config)")
    return {"url": url}

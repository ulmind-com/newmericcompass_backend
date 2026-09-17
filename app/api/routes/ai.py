"""Ask the app a question.

The route is thin on purpose. It identifies who is asking so a daily limit can
be applied, embeds the question, retrieves, checks the retrieval was good enough
to be worth answering from, and hands the passages to the model. Every decision
about what may be said lives in `services/ai/answer.py`.

Signing in is not required — the assistant is open to everyone — so an
unauthenticated caller is counted against their device instead.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.database import get_database
from app.core.security import TokenData, get_current_admin
from app.services.ai import answer as answering
from app.services.ai import embeddings, store

logger = logging.getLogger(__name__)
router = APIRouter()

USAGE = "ai_usage"
LANGS = {"en", "bn", "hi", "as"}


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    lang: str = "en"
    #: The screen the reader is on, when they asked from inside one.
    screen: Optional[str] = None


class SourceOut(BaseModel):
    n: int
    screen: str
    route: str
    heading: str
    excerpt: str


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceOut]
    #: False when the question fell outside what the app covers.
    answered: bool
    #: What is left of today's allowance, after this question.
    remaining: int


def _caller(authorization: Optional[str], device_id: Optional[str], request: Request) -> str:
    """Who to count this question against.

    A signed-in reader is counted by email so the limit follows them between
    devices. Everyone else is counted by the device id the app sends, and by IP
    if even that is missing — weaker, but it still costs something to get past.
    """
    if authorization and authorization.lower().startswith("bearer "):
        try:
            secret = settings.SECRET_KEY or "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"
            payload = jwt.decode(authorization[7:], secret, algorithms=[settings.ALGORITHM])
            if email := payload.get("sub"):
                return f"user:{str(email).strip().lower()}"
        except jwt.PyJWTError:
            pass
    if device_id:
        return f"device:{device_id[:64]}"
    return f"ip:{request.client.host if request.client else 'unknown'}"


async def _spend(db: AsyncIOMotorDatabase, caller: str) -> int:
    """Take one from today's allowance, or refuse. Returns what is left."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    key = f"{caller}:{today}"
    doc = await db[USAGE].find_one_and_update(
        {"_id": key},
        {
            "$inc": {"count": 1},
            "$setOnInsert": {"expires_at": datetime.now(timezone.utc) + timedelta(days=2)},
        },
        upsert=True,
        return_document=True,
    )
    used = (doc or {}).get("count", 1)
    if used > settings.AI_DAILY_LIMIT:
        raise HTTPException(
            status_code=429,
            detail=f"You have used today's {settings.AI_DAILY_LIMIT} questions. Please come back tomorrow.",
        )
    return max(settings.AI_DAILY_LIMIT - used, 0)


@router.post("/ask", response_model=AskResponse, summary="Ask a question about the app's content")
async def ask(
    payload: AskRequest,
    request: Request,
    db: Annotated[AsyncIOMotorDatabase, Depends(get_database)],
    authorization: Annotated[Optional[str], Header()] = None,
    x_device_id: Annotated[Optional[str], Header()] = None,
):
    if not answering.is_configured():
        raise HTTPException(status_code=503, detail="The assistant is not configured yet.")

    index = await store.load(db)
    if index is None:
        raise HTTPException(status_code=503, detail="The assistant is still being prepared.")

    lang = payload.lang if payload.lang in LANGS else "en"
    remaining = await _spend(db, _caller(authorization, x_device_id, request))

    question = payload.question.strip()

    # A question the embedding service cannot handle is still answerable from
    # the keyword half, so a Gemini outage degrades the assistant rather than
    # taking it down.
    vector: list[float] | None = None
    if embeddings.is_configured():
        try:
            vector = await embeddings.embed_query(question)
        except embeddings.EmbeddingError as exc:
            logger.warning("Falling back to keyword-only retrieval: %s", exc)

    rel = index.relevance(question, vector)
    if not answering.should_answer(rel):
        logger.info(
            "Off-topic question refused (coverage=%.2f lex=%.2f dense=%.2f unknown=%s): %r",
            rel.coverage, rel.lexical, rel.dense, rel.unknown[:5], question[:120],
        )
        result = answering.refusal(lang)
        return AskResponse(answer=result.text, sources=[], answered=False, remaining=remaining)

    hits = index.search(question, vector, k=8)
    result = await answering.answer(question, hits, lang, payload.screen)

    return AskResponse(
        answer=result.text,
        sources=[SourceOut(**vars(s)) for s in result.sources],
        answered=result.answered,
        remaining=remaining,
    )


@router.post("/reindex", summary="Rebuild the assistant's index (admin)")
async def reindex(
    db: Annotated[AsyncIOMotorDatabase, Depends(get_database)],
    _: Annotated[TokenData, Depends(get_current_admin)],
    force: bool = False,
):
    """Re-read the corpus and embed whatever changed.

    Run this after editing rules, tips, categories or day protocols in the admin
    panel, and after shipping new app content. Unchanged passages keep the
    vectors they have, so this is cheap unless `force` is set.
    """
    try:
        return await store.build(db, force=force)
    except embeddings.EmbeddingError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/status", summary="What the assistant currently knows (admin)")
async def status(
    db: Annotated[AsyncIOMotorDatabase, Depends(get_database)],
    _: Annotated[TokenData, Depends(get_current_admin)],
):
    meta = await db[store.META].find_one({"_id": "index"}) or {}
    return {
        "passages": await db[store.COLLECTION].count_documents({}),
        "embeddings_configured": embeddings.is_configured(),
        "answering_configured": answering.is_configured(),
        "daily_limit": settings.AI_DAILY_LIMIT,
        "last_build": {k: v for k, v in meta.items() if k != "_id"},
    }

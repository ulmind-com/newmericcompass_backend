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
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

import jwt
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.database import get_database
from app.core.security import TokenData, get_current_admin
from app.services.ai import answer as answering
from app.services.ai import embeddings, retrieve, store

logger = logging.getLogger(__name__)
router = APIRouter()

USAGE = "ai_usage"
LANGS = {"en", "bn", "hi", "as"}


class HistoryTurn(BaseModel):
    """One earlier exchange in the same chat."""

    question: str = Field(max_length=500)
    answer: str = Field(max_length=4000)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    lang: str = "en"
    #: The screen the reader is on, when they asked from inside one.
    screen: Optional[str] = None
    #: The conversation so far, oldest first. The server keeps none of it —
    #: the chat lives on the reader's phone and comes with each question.
    history: list[HistoryTurn] = Field(default_factory=list, max_length=20)


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
    #: What is left of today's allowance, after this question. None when there
    #: is no allowance to run out of.
    remaining: Optional[int] = None


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


async def _spend(db: AsyncIOMotorDatabase, caller: str) -> Optional[int]:
    """Take one from today's allowance, or refuse. Returns what is left.

    With no limit configured there is nothing to count, so nothing is written:
    None goes back and the app shows no counter.
    """
    if settings.AI_DAILY_LIMIT <= 0:
        return None
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
    question = payload.question.strip()
    history = [answering.Turn(t.question, t.answer) for t in payload.history][-answering.HISTORY_TURNS:]
    remaining = await _spend(db, _caller(authorization, x_device_id, request))

    unavailable = HTTPException(
        status_code=503,
        detail="The assistant is unavailable right now. Please try again shortly.",
    )

    # Attempts to talk the assistant out of being the assistant are refused
    # before anything else sees them.
    if answering.looks_like_injection(question):
        return _reply(answering.refusal(lang), remaining)

    async def decide(query: str) -> answering.Route:
        try:
            return await answering.route(query, lang, history)
        except answering.AnswerError as exc:
            logger.error("Routing failed: %s", exc)
            raise unavailable from exc

    # What gets searched for. Usually the question as asked; mid-conversation,
    # the question restated so it stands on its own.
    search = question
    decided: answering.Route | None = None

    if history:
        # In a conversation the message has to be read against what came
        # before, whatever it looks like: "what about the bedroom?" is a Vastu
        # question only because of the one before it. So the model always
        # reads it — and restates it, so the search has something to find.
        decided = await decide(question)
        if decided.intent == "vastu" and decided.question:
            search = decided.question

    # A question the embedding service cannot handle is still answerable from
    # the keyword half, so a Gemini outage degrades the assistant rather than
    # taking it down.
    vector: list[float] | None = None
    if embeddings.is_configured():
        try:
            vector = await embeddings.embed_query(search)
        except embeddings.EmbeddingError as exc:
            logger.warning("Falling back to keyword-only retrieval: %s", exc)

    # Two ways in. A message the keyword gate is sure about is a Vastu question
    # and goes straight to the search — the common case, one model call. Anything
    # the gate is unsure of goes to the model to decide what it is. Nothing about
    # greetings or small talk is listed here: the model reads the message the
    # way a person would.
    rel = index.relevance(search, vector)
    confident = answering.should_answer(rel)

    if decided is None and not confident:
        decided = await decide(question)

    if decided is not None:
        logger.info(
            "Routed %r as %s%s (coverage=%.2f heading_terms=%d)",
            question[:80], decided.intent,
            f" -> {search[:80]!r}" if search != question else "",
            rel.coverage, rel.heading_terms,
        )
        if decided.intent == "chat":
            return _reply(answering.Answer(decided.reply, [], True), remaining)
        if decided.intent == "off_topic":
            text = decided.reply or answering.refusal(lang).text
            return _reply(answering.Answer(text, [], False), remaining)
        # "vastu": answered exactly like any other question — from the
        # passages, with citations checked — so the model's call here decides
        # that an answer is attempted, never what the answer says.

    hits = index.search(search, vector, k=8)
    try:
        result = await answering.answer(search, hits, lang, payload.screen)
    except answering.AnswerError as exc:
        # The reason belongs in the log, not in a reader's face.
        logger.error("Answering failed: %s", exc)
        raise unavailable from exc

    # The gate can be sure of something it has misread. "What is your name"
    # contains one word that happens to appear in a heading, so the gate sent
    # it to the search, the search had nothing to say, and the reader was told
    # their question was out of scope. When a search the gate was sure of comes
    # back empty-handed, the model reads the message before anyone is refused.
    if decided is None and confident and not result.answered:
        try:
            second = await answering.route(question, lang, history)
        except answering.AnswerError:
            return _reply(result, remaining)
        if second.intent == "chat":
            return _reply(answering.Answer(second.reply, [], True), remaining)
        if second.intent == "off_topic" and second.reply:
            return _reply(answering.Answer(second.reply, [], False), remaining)

    return _reply(result, remaining)


def _reply(result: answering.Answer, remaining: Optional[int]) -> AskResponse:
    return AskResponse(
        answer=result.text,
        sources=[SourceOut(**asdict(s)) for s in result.sources],
        answered=result.answered,
        remaining=remaining,
    )


@router.post("/reindex", summary="Rebuild the assistant's index (admin)")
async def reindex(
    background: BackgroundTasks,
    db: Annotated[AsyncIOMotorDatabase, Depends(get_database)],
    _: Annotated[TokenData, Depends(get_current_admin)],
    force: bool = False,
):
    """Start re-reading the corpus and embedding whatever changed.

    Returns as soon as the work is started, because embedding several hundred
    passages against a rate-limited API takes minutes and no proxy will hold a
    request open that long. Watch `/ai/status` for progress.

    Run this after editing rules, tips, categories or day protocols in the admin
    panel, and after shipping new app content. Unchanged passages keep the
    vectors they have, so this is cheap unless `force` is set.
    """
    if not embeddings.is_configured():
        raise HTTPException(status_code=503, detail="GEMINI_API_KEY is not set.")
    if store.progress().get("running"):
        return {"started": False, "reason": "A build is already running.", "progress": store.progress()}
    background.add_task(store.build_in_background, db, force=force)
    return {"started": True, "watch": "/api/ai/status"}


@router.get("/models", summary="Embedding models this Gemini key can use (admin)")
async def models(_: Annotated[TokenData, Depends(get_current_admin)]):
    """What the key actually serves, and which one would be chosen.

    Here because the model name is not ours to know: Google retires them, and
    when embedding starts answering 404 this is the first thing to look at.
    """
    try:
        found = await embeddings.list_models()
    except embeddings.EmbeddingError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    usable = [
        m["name"] for m in found
        if "embedContent" in (m.get("supportedGenerationMethods") or [])
    ]
    return {
        "embedding_models": usable,
        "chosen": await embeddings.resolve_model() if usable else None,
        "configured_override": settings.GEMINI_EMBED_MODEL,
    }


@router.get("/diagnose", summary="Try the whole chain and report what broke (admin)")
async def diagnose(
    db: Annotated[AsyncIOMotorDatabase, Depends(get_database)],
    _: Annotated[TokenData, Depends(get_current_admin)],
    q: Optional[str] = None,
):
    """Exercise retrieval, embedding and answering, and say what each one did.

    The friendly message a reader gets when something breaks is no use for
    fixing it, so the real errors are reported here instead of only in the log.
    """
    report: dict[str, object] = {}

    index = await store.load(db)
    report["index"] = (
        {"passages": len(index.passages), "semantic_search": index.has_vectors}
        if index else "empty"
    )

    try:
        report["embedding_model"] = await embeddings.resolve_model()
        vector = await embeddings.embed_query("kitchen in the south east")
        report["embed_query"] = f"ok, {len(vector)} dimensions"
    except Exception as exc:  # noqa: BLE001 — reporting is the point
        report["embed_query"] = f"FAILED: {exc}"

    try:
        report["answering_models"] = (await answering.list_models())[:20]
        report["answering_model"] = await answering.resolve_model()
    except Exception as exc:  # noqa: BLE001
        report["answering_model"] = f"FAILED: {exc}"

    # Why one particular question was accepted or refused. The gate reads four
    # numbers and the answer is obvious once you can see them; without this
    # they can only be guessed at from outside.
    if index and q:
        rel = index.relevance(q, None)
        heads = [h.passage.heading for h in index.search(q, None, k=3)]
        return {
            "question": q,
            "terms": sorted(set(retrieve.tokenize(q))),
            "coverage": round(rel.coverage, 2),
            "unknown": rel.unknown,
            "heading_terms": rel.heading_terms,
            "distinct_terms": rel.terms,
            "heading_subject": rel.heading_subject,
            "lexical": round(rel.lexical, 2),
            "would_answer": answering.should_answer(rel),
            "injection": answering.looks_like_injection(q),
            "top": heads,
        }

    if index:
        rel = index.relevance("where should the kitchen go", None)
        report["relevance_keyword_only"] = {
            "coverage": round(rel.coverage, 2),
            "lexical": round(rel.lexical, 2),
            "would_answer": answering.should_answer(rel),
        }
        hits = index.search("where should the kitchen go", None, k=4)
        report["retrieved"] = [h.passage.heading for h in hits]

        # The model's reply before any checking, because "it refused" and "it
        # answered but did not cite" look identical from the outside and need
        # opposite fixes.
        try:
            report["model_said"] = (
                await answering.ask_model("Where should the kitchen go?", hits, "en", None)
            )[:1200]
        except Exception as exc:  # noqa: BLE001
            report["model_said"] = f"FAILED: {exc}"

        try:
            answer = await answering.answer("Where should the kitchen go?", hits, "en")
            report["end_to_end"] = {
                "answered": answer.answered,
                "sources": len(answer.sources),
                "preview": answer.text[:200],
            }
        except Exception as exc:  # noqa: BLE001
            report["end_to_end"] = f"FAILED: {exc}"

    return report


@router.get("/status", summary="What the assistant currently knows (admin)")
async def status(
    db: Annotated[AsyncIOMotorDatabase, Depends(get_database)],
    _: Annotated[TokenData, Depends(get_current_admin)],
):
    meta = await db[store.META].find_one({"_id": "index"}) or {}
    return {
        "building": store.progress(),
        "passages": await db[store.COLLECTION].count_documents({}),
        "embeddings_configured": embeddings.is_configured(),
        "answering_configured": answering.is_configured(),
        "daily_limit": settings.AI_DAILY_LIMIT,
        "last_build": {k: v for k, v in meta.items() if k != "_id"},
    }

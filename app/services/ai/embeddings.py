"""Turning passages and questions into vectors, with Gemini.

Groq runs the answering model but does not serve embeddings, so the two halves
of the assistant come from two places. Only this module knows that.

The model is discovered rather than written down. Google retires embedding
model names on its own schedule — text-embedding-004 was hardcoded here and
started answering 404 — so the first call asks the API which models it actually
serves and picks one, preferring the newest known name and falling back to
whatever else supports embedding. Setting GEMINI_EMBED_MODEL overrides the
choice when a specific model is wanted.

Passages and questions are embedded with different task types on purpose —
Gemini asks for it, and a question embedded as if it were a document retrieves
noticeably worse.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

BASE = "https://generativelanguage.googleapis.com/v1beta"
#: Gemini allows 100 per batchEmbedContents call, but the free tier's real
#: limit is tokens per minute, not requests: 100 passages at once is around
#: 60k tokens and is refused outright. Twenty keeps each call inside it.
BATCH = 20
#: Breathing room between batches, for the same reason.
PACE_SECONDS = 1.5

#: How long to keep trying. A build runs in the background and can afford to
#: wait out a rate-limit window; a question cannot. Embedding a question with
#: the build's patience made every question take three minutes once the daily
#: quota ran out, which is worse than not embedding it at all.
BUILD_WAITS = (5, 20, 45, 90)
QUERY_WAITS = (1,)
QUERY_TIMEOUT = 10.0

#: When the quota is gone it is gone for the rest of the day, so questions stop
#: asking for a while rather than paying the timeout every time. Retrieval falls
#: back to keywords, which is what this window is for.
_COOLDOWN_SECONDS = 900
_unavailable_until = 0.0

#: Tried in this order when the API offers more than one. Newest first; the
#: list is a preference, not a requirement, and an unknown model that supports
#: embedContent is used rather than failing.
PREFERRED = (
    "models/gemini-embedding-001",
    "models/text-embedding-005",
    "models/text-embedding-004",
    "models/embedding-001",
)

_model: str | None = None
_lock = asyncio.Lock()


class EmbeddingError(RuntimeError):
    pass


def is_configured() -> bool:
    return bool(settings.GEMINI_API_KEY)


def _require_key() -> str:
    if not settings.GEMINI_API_KEY:
        raise EmbeddingError("GEMINI_API_KEY is not set, so nothing can be embedded.")
    return settings.GEMINI_API_KEY


async def list_models() -> list[dict]:
    """Every model this key can see, with what each one supports."""
    key = _require_key()
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE}/models?key={key}&pageSize=200", timeout=60)
        if r.status_code >= 400:
            raise EmbeddingError(f"Gemini would not list models ({r.status_code}): {r.text[:200]}")
        return r.json().get("models", [])


async def resolve_model() -> str:
    """Which model to embed with, worked out once and remembered."""
    global _model
    if _model:
        return _model

    async with _lock:
        if _model:
            return _model

        if override := settings.GEMINI_EMBED_MODEL:
            _model = override if override.startswith("models/") else f"models/{override}"
            logger.info("Embedding model set by configuration: %s", _model)
            return _model

        models = await list_models()
        usable = {
            m["name"]
            for m in models
            if "embedContent" in (m.get("supportedGenerationMethods") or [])
        }
        if not usable:
            raise EmbeddingError(
                "This Gemini key serves no embedding model. Models seen: "
                + ", ".join(sorted(m.get("name", "?") for m in models)[:10])
            )

        for name in PREFERRED:
            if name in usable:
                _model = name
                break
        else:
            _model = sorted(usable)[0]

        logger.info("Embedding with %s (%d embedding models available)", _model, len(usable))
        return _model


async def _post(
    client: httpx.AsyncClient,
    model: str,
    method: str,
    body: dict,
    *,
    waits: tuple[int, ...] = BUILD_WAITS,
    timeout: float = 120.0,
) -> dict:
    """One call, retried on the failures that are worth retrying.

    Rate limits and 5xx are transient; a bad key or a malformed request is not,
    and retrying those only delays the error. `waits` is how patient to be — a
    rate limit is measured per minute, so a build's waits cross a minute
    boundary rather than failing four times inside the same window.
    """
    key = _require_key()
    detail = "no response"
    for attempt, wait in enumerate(waits):
        try:
            r = await client.post(f"{BASE}/{model}:{method}?key={key}", json=body, timeout=timeout)
        except httpx.HTTPError as exc:
            detail = f"{type(exc).__name__}: {exc}"
            await asyncio.sleep(wait)
            continue

        if r.status_code < 400:
            return r.json()

        detail = f"HTTP {r.status_code}: {r.text[:300]}"
        if r.status_code not in (429, 500, 502, 503, 504):
            raise EmbeddingError(f"Gemini rejected the request ({detail})")

        # Honour the server's own retry hint when it gives one.
        retry_after = r.headers.get("retry-after")
        delay = wait
        if retry_after and retry_after.isdigit():
            delay = max(wait, min(int(retry_after), 120))
        logger.warning("Gemini %s; waiting %ss (attempt %d/%d)", detail, delay, attempt + 1, len(waits))
        await asyncio.sleep(delay)

    raise EmbeddingError(f"Gemini did not answer after {len(waits)} attempts. Last: {detail}")


async def embed_documents(
    texts: list[str],
    progress: Callable[[int, int], None] | None = None,
) -> list[list[float]]:
    """Embed the corpus. Batched, because it is run over hundreds of passages."""
    model = await resolve_model()
    out: list[list[float]] = []
    async with httpx.AsyncClient() as client:
        for start in range(0, len(texts), BATCH):
            chunk = texts[start:start + BATCH]
            try:
                data = await _post(client, model, "batchEmbedContents", {
                    "requests": [
                        {
                            "model": model,
                            "content": {"parts": [{"text": t}]},
                            "taskType": "RETRIEVAL_DOCUMENT",
                        }
                        for t in chunk
                    ],
                })
                got = [e["values"] for e in data.get("embeddings", [])]
                if len(got) != len(chunk):
                    raise EmbeddingError(f"Asked for {len(chunk)} vectors, got {len(got)}.")
            except EmbeddingError:
                # Not every embedding model takes a batch. Falling back one at a
                # time is slower but it is the difference between a slow build
                # and no assistant at all.
                logger.warning("Batch embedding refused by %s; falling back to one at a time", model)
                got = []
                for t in chunk:
                    single = await _post(client, model, "embedContent", {
                        "model": model,
                        "content": {"parts": [{"text": t}]},
                        "taskType": "RETRIEVAL_DOCUMENT",
                    })
                    values = single.get("embedding", {}).get("values")
                    if not values:
                        raise EmbeddingError("Gemini returned no vector for a passage.")
                    got.append(values)
            out.extend(got)
            logger.info("Embedded %d/%d passages", len(out), len(texts))
            if progress:
                progress(len(out), len(texts))
            if start + BATCH < len(texts):
                await asyncio.sleep(PACE_SECONDS)
    return out


async def embed_query(text: str) -> list[float]:
    """Embed one question, as a question — quickly, or not at all.

    A person is waiting on this, so there is one attempt and a short timeout.
    If it fails the caller falls back to keyword search, and the service is
    left alone for a while rather than being asked again on every question.
    """
    global _unavailable_until
    if time.monotonic() < _unavailable_until:
        raise EmbeddingError("Embedding is in cooldown after a quota or rate-limit failure.")

    try:
        model = await resolve_model()
        async with httpx.AsyncClient() as client:
            data = await _post(
                client, model, "embedContent",
                {
                    "model": model,
                    "content": {"parts": [{"text": text}]},
                    "taskType": "RETRIEVAL_QUERY",
                },
                waits=QUERY_WAITS,
                timeout=QUERY_TIMEOUT,
            )
    except EmbeddingError:
        _unavailable_until = time.monotonic() + _COOLDOWN_SECONDS
        logger.warning(
            "Embedding unavailable; questions will use keyword search for the next %d minutes",
            _COOLDOWN_SECONDS // 60,
        )
        raise

    values = data.get("embedding", {}).get("values")
    if not values:
        raise EmbeddingError("Gemini returned no vector for the question.")
    return values

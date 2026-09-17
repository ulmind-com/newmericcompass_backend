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

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

BASE = "https://generativelanguage.googleapis.com/v1beta"
#: Gemini's own cap on one batchEmbedContents call.
BATCH = 100

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


async def _post(client: httpx.AsyncClient, model: str, method: str, body: dict) -> dict:
    """One call, retried on the failures that are worth retrying.

    Rate limits and 5xx are transient; a bad key or a malformed request is not,
    and retrying those only delays the error.
    """
    key = _require_key()
    last: Exception | None = None
    for attempt in range(4):
        try:
            r = await client.post(f"{BASE}/{model}:{method}?key={key}", json=body, timeout=90)
            if r.status_code in (429, 500, 502, 503, 504):
                raise httpx.HTTPStatusError("transient", request=r.request, response=r)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as exc:
            last = exc
            if exc.response is not None and exc.response.status_code not in (429, 500, 502, 503, 504):
                raise EmbeddingError(
                    f"Gemini rejected the request ({exc.response.status_code}): {exc.response.text[:300]}"
                ) from exc
            await asyncio.sleep(2 ** attempt)
        except httpx.HTTPError as exc:
            last = exc
            await asyncio.sleep(2 ** attempt)
    raise EmbeddingError(f"Gemini did not answer after 4 attempts: {last}")


async def embed_documents(texts: list[str]) -> list[list[float]]:
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
    return out


async def embed_query(text: str) -> list[float]:
    """Embed one question, as a question."""
    model = await resolve_model()
    async with httpx.AsyncClient() as client:
        data = await _post(client, model, "embedContent", {
            "model": model,
            "content": {"parts": [{"text": text}]},
            "taskType": "RETRIEVAL_QUERY",
        })
    values = data.get("embedding", {}).get("values")
    if not values:
        raise EmbeddingError("Gemini returned no vector for the question.")
    return values

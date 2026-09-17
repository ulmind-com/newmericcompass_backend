"""Turning passages and questions into vectors, with Gemini.

Groq runs the answering model but does not serve embeddings, so the two halves
of the assistant come from two places. Only this module knows that.

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

MODEL = "models/text-embedding-004"
ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/{MODEL}"
#: Gemini's own cap on one batchEmbedContents call.
BATCH = 100
DIMS = 768


class EmbeddingError(RuntimeError):
    pass


def is_configured() -> bool:
    return bool(settings.GEMINI_API_KEY)


def _require_key() -> str:
    if not settings.GEMINI_API_KEY:
        raise EmbeddingError("GEMINI_API_KEY is not set, so nothing can be embedded.")
    return settings.GEMINI_API_KEY


async def _post(client: httpx.AsyncClient, path: str, body: dict) -> dict:
    """One call, retried on the failures that are worth retrying.

    Rate limits and 5xx are transient; a bad key or a malformed request is not,
    and retrying those only delays the error.
    """
    key = _require_key()
    last: Exception | None = None
    for attempt in range(4):
        try:
            r = await client.post(f"{ENDPOINT}:{path}?key={key}", json=body, timeout=60)
            if r.status_code in (429, 500, 502, 503, 504):
                raise httpx.HTTPStatusError("transient", request=r.request, response=r)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as exc:
            last = exc
            if exc.response is not None and exc.response.status_code not in (429, 500, 502, 503, 504):
                raise EmbeddingError(
                    f"Gemini rejected the request ({exc.response.status_code}): {exc.response.text[:200]}"
                ) from exc
            await asyncio.sleep(2 ** attempt)
        except httpx.HTTPError as exc:
            last = exc
            await asyncio.sleep(2 ** attempt)
    raise EmbeddingError(f"Gemini did not answer after 4 attempts: {last}")


async def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed the corpus. Batched, because it is run over hundreds of passages."""
    out: list[list[float]] = []
    async with httpx.AsyncClient() as client:
        for start in range(0, len(texts), BATCH):
            chunk = texts[start:start + BATCH]
            body = {
                "requests": [
                    {
                        "model": MODEL,
                        "content": {"parts": [{"text": t}]},
                        "taskType": "RETRIEVAL_DOCUMENT",
                    }
                    for t in chunk
                ]
            }
            data = await _post(client, "batchEmbedContents", body)
            got = [e["values"] for e in data.get("embeddings", [])]
            if len(got) != len(chunk):
                raise EmbeddingError(f"Asked for {len(chunk)} vectors, got {len(got)}.")
            out.extend(got)
            logger.info("Embedded %d/%d passages", len(out), len(texts))
    return out


async def embed_query(text: str) -> list[float]:
    """Embed one question, as a question."""
    async with httpx.AsyncClient() as client:
        data = await _post(client, "embedContent", {
            "model": MODEL,
            "content": {"parts": [{"text": text}]},
            "taskType": "RETRIEVAL_QUERY",
        })
    values = data.get("embedding", {}).get("values")
    if not values:
        raise EmbeddingError("Gemini returned no vector for the question.")
    return values

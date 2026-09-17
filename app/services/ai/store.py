"""Where the index lives, and how it is built and loaded.

Embedding costs an API call, so vectors are kept in Mongo and a restart loads
them back rather than paying again. The build is content-addressed: a passage
whose text has not changed keeps the vector it already had, so reindexing after
an admin edits one rule embeds one passage, not a thousand.

The build writes as it goes. The first real build embedded 900 of 1,272
passages, hit the day's quota, and threw all 900 away because nothing was saved
until the end. Now the passages are stored first and each batch's vectors are
written as they arrive, so a build that stops halfway has banked its work and
the next one picks up where it left off.

Until every passage has a vector, searching falls back to keywords alone. That
is deliberate: ranking half the corpus by meaning and the other half by word
overlap would quietly favour whichever half happened to be embedded first.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import UpdateOne

from app.services.ai import corpus, embeddings
from app.services.ai.corpus import Passage
from app.services.ai.retrieve import Index

logger = logging.getLogger(__name__)

COLLECTION = "ai_passages"
META = "ai_index_meta"

#: Written to Mongo in one go; embedded in batches of this many.
WRITE_CHUNK = 200

#: Held between requests. Rebuilt on demand, never per request.
_index: Index | None = None

#: What the current or last build is doing. A build embeds hundreds of passages
#: against a rate-limited API, which takes minutes — far longer than a request
#: should be held open — so it runs in the background and reports here.
_progress: dict[str, Any] = {"running": False}


def progress() -> dict[str, Any]:
    return dict(_progress)


def digest(p: Passage) -> str:
    return hashlib.sha256(p.for_embedding().encode()).hexdigest()[:32]


async def _store_passages(db: AsyncIOMotorDatabase, passages: list[Passage]) -> None:
    """Put the corpus in Mongo, vectors or not.

    Replaces wholesale, because a passage that has left the corpus must not
    survive in the index and go on being cited.
    """
    await db[COLLECTION].delete_many({})
    for start in range(0, len(passages), WRITE_CHUNK):
        chunk = passages[start:start + WRITE_CHUNK]
        await db[COLLECTION].insert_many([{**p.to_doc(), "hash": digest(p)} for p in chunk])


async def _save_vectors(db: AsyncIOMotorDatabase, batch: list[Passage]) -> None:
    """Bank the vectors this batch just earned."""
    if not batch:
        return
    await db[COLLECTION].bulk_write(
        [UpdateOne({"_id": p.id}, {"$set": {"vector": p.vector}}) for p in batch],
        ordered=False,
    )


async def build(db: AsyncIOMotorDatabase, *, force: bool = False) -> dict[str, Any]:
    """Re-read the corpus, embed whatever still needs it, and store as it goes."""
    if not embeddings.is_configured():
        raise embeddings.EmbeddingError("GEMINI_API_KEY is not set, so the index cannot be built.")

    passages = await corpus.load_all(db)
    model = await embeddings.resolve_model()

    # Vectors from two different models cannot be compared, and they are not
    # even the same length. When the model changes — which it does on Google's
    # schedule, not ours — everything is re-embedded rather than mixed.
    meta = await db[META].find_one({"_id": "index"}) or {}
    if meta.get("model") and meta["model"] != model:
        logger.info("Embedding model changed from %s to %s; rebuilding in full", meta["model"], model)
        force = True

    existing = {
        d["_id"]: d
        for d in await db[COLLECTION].find({}, {"vector": 1, "hash": 1}).to_list(length=20000)
    }

    pending: list[Passage] = []
    reused = 0
    for p in passages:
        prior = existing.get(p.id)
        if not force and prior and prior.get("hash") == digest(p) and prior.get("vector"):
            p.vector = prior["vector"]
            reused += 1
        else:
            pending.append(p)

    # Stored before any embedding, so the assistant can answer from keywords
    # immediately and a build that fails later still leaves a usable index.
    await _store_passages(db, passages)
    global _index
    _index = Index(passages)

    embedded = 0
    failure: str | None = None
    if pending:
        logger.info("Embedding %d passages (%d already had vectors)", len(pending), reused)
        try:
            for start in range(0, len(pending), embeddings.BATCH):
                batch = pending[start:start + embeddings.BATCH]
                vectors = await embeddings.embed_documents([p.for_embedding() for p in batch])
                for p, v in zip(batch, vectors, strict=True):
                    p.vector = v
                await _save_vectors(db, batch)
                embedded += len(batch)
                _progress.update(embedded=embedded + reused, to_embed=len(passages))
                # The pacing lives here now that this loop, not embed_documents,
                # decides the batch boundaries.
                if start + embeddings.BATCH < len(pending):
                    await asyncio.sleep(embeddings.PACE_SECONDS)
        except Exception as exc:  # noqa: BLE001 — banked work is kept, the reason is reported
            failure = str(exc)[:500]
            logger.warning("Embedding stopped after %d passages: %s", embedded, failure)

    complete = reused + embedded == len(passages)
    await db[META].update_one(
        {"_id": "index"},
        {"$set": {
            "passages": len(passages),
            "with_vectors": reused + embedded,
            "complete": complete,
            "model": model,
            "dims": len(pending[0].vector) if pending and pending[0].vector else meta.get("dims", 0),
            "built_at": datetime.now(timezone.utc),
            "last_error": failure,
        }},
        upsert=True,
    )

    # Rebuild in memory now that the vectors are on the passages.
    _index = Index(passages)
    logger.info(
        "Index built: %d passages, %d with vectors, semantic search %s",
        len(passages), reused + embedded, "on" if _index.has_vectors else "off (keyword only)",
    )

    result = {
        "passages": len(passages),
        "with_vectors": reused + embedded,
        "newly_embedded": embedded,
        "reused": reused,
        "complete": complete,
        "semantic_search": _index.has_vectors,
        "model": model,
    }
    if failure:
        result["stopped_because"] = failure
    return result


async def build_in_background(db: AsyncIOMotorDatabase, *, force: bool = False) -> None:
    """Run a build without anyone waiting on the HTTP request.

    Progress and the outcome land in `_progress`, which `/ai/status` reports, so
    a failure halfway through is visible rather than silent.
    """
    if _progress.get("running"):
        logger.info("A build is already running; ignoring the request to start another")
        return

    _progress.clear()
    _progress.update(running=True, started_at=datetime.now(timezone.utc), embedded=0, to_embed=0)
    try:
        result = await build(db, force=force)
        _progress.update(running=False, ok=True, finished_at=datetime.now(timezone.utc), **result)
    except Exception as exc:  # noqa: BLE001 — the point is to report it, not raise into nothing
        logger.exception("Index build failed")
        _progress.update(
            running=False, ok=False, error=str(exc)[:500],
            finished_at=datetime.now(timezone.utc),
        )


async def load(db: AsyncIOMotorDatabase) -> Index | None:
    """The index, from memory if it is there and from Mongo if it is not."""
    global _index
    if _index is not None:
        return _index
    docs = await db[COLLECTION].find({}).to_list(length=20000)
    if not docs:
        return None
    _index = Index([Passage.from_doc(d) for d in docs])
    logger.info(
        "Index loaded from Mongo: %d passages, semantic search %s",
        len(docs), "on" if _index.has_vectors else "off (keyword only)",
    )
    return _index


def forget() -> None:
    """Drop the in-memory copy, so the next request reloads it."""
    global _index
    _index = None

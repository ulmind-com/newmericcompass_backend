"""Where the index lives, and how it is built and loaded.

Embedding the corpus costs an API call per hundred passages, so it is done once
and the vectors are kept in Mongo. A dyno restart loads them back; it does not
re-embed.

The build is content-addressed: a passage whose text has not changed keeps the
vector it already had. Rebuilding after an admin edits one rule therefore costs
one passage's worth of embedding, not six hundred.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.services.ai import corpus, embeddings
from app.services.ai.corpus import Passage
from app.services.ai.retrieve import Index

logger = logging.getLogger(__name__)

COLLECTION = "ai_passages"
META = "ai_index_meta"

#: Held between requests. Rebuilt on demand, never per request.
_index: Index | None = None


def digest(p: Passage) -> str:
    return hashlib.sha256(p.for_embedding().encode()).hexdigest()[:32]


async def build(db: AsyncIOMotorDatabase, *, force: bool = False) -> dict[str, Any]:
    """Re-read the corpus, embed what changed, and store it."""
    if not embeddings.is_configured():
        raise embeddings.EmbeddingError("GEMINI_API_KEY is not set, so the index cannot be built.")

    passages = await corpus.load_all(db)
    existing = {
        d["_id"]: d
        for d in await db[COLLECTION].find({}, {"vector": 1, "hash": 1}).to_list(length=20000)
    }

    fresh: list[Passage] = []
    reused = 0
    for p in passages:
        h = digest(p)
        prior = existing.get(p.id)
        if not force and prior and prior.get("hash") == h and prior.get("vector"):
            p.vector = prior["vector"]
            reused += 1
        else:
            fresh.append(p)

    if fresh:
        logger.info("Embedding %d new or changed passages (%d reused)", len(fresh), reused)
        vectors = await embeddings.embed_documents([p.for_embedding() for p in fresh])
        for p, v in zip(fresh, vectors, strict=True):
            p.vector = v

    # Replace wholesale: a passage that no longer exists in the corpus must not
    # survive in the index and go on being cited.
    await db[COLLECTION].delete_many({})
    if passages:
        await db[COLLECTION].insert_many(
            [{**p.to_doc(), "hash": digest(p)} for p in passages]
        )

    await db[META].update_one(
        {"_id": "index"},
        {"$set": {"passages": len(passages), "embedded": len(fresh), "reused": reused}},
        upsert=True,
    )

    global _index
    _index = Index(passages)
    logger.info("Index built: %d passages", len(passages))
    return {"passages": len(passages), "embedded": len(fresh), "reused": reused}


async def load(db: AsyncIOMotorDatabase) -> Index | None:
    """The index, from memory if it is there and from Mongo if it is not."""
    global _index
    if _index is not None:
        return _index
    docs = await db[COLLECTION].find({}).to_list(length=20000)
    if not docs:
        return None
    _index = Index([Passage.from_doc(d) for d in docs])
    logger.info("Index loaded from Mongo: %d passages", len(docs))
    return _index


def forget() -> None:
    """Drop the in-memory copy, so the next request reloads it."""
    global _index
    _index = None

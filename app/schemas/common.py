"""Shared schema helpers."""

from datetime import datetime, timezone


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def serialize_doc(doc: dict | None) -> dict | None:
    """Convert a MongoDB document's ``_id`` to a string ``id`` field, in place."""
    if not doc:
        return doc
    if "_id" in doc:
        doc["id"] = str(doc.pop("_id"))
    return doc


def serialize_docs(docs: list[dict]) -> list[dict]:
    return [serialize_doc(d) for d in docs]

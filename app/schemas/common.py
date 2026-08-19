"""Shared schema helpers."""

from datetime import datetime, timezone


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: datetime | None) -> datetime | None:
    """Treat a naive datetime as the UTC it was stored as.

    Documents written before the client was made ``tz_aware`` still come back
    naive, so anything that compares stored times goes through this.
    """
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def serialize_doc(doc: dict | None) -> dict | None:
    """Convert a MongoDB document's ``_id`` to a string ``id`` field, in place."""
    if not doc:
        return doc
    if "_id" in doc:
        doc["id"] = str(doc.pop("_id"))
    return doc


def serialize_docs(docs: list[dict]) -> list[dict]:
    return [serialize_doc(d) for d in docs]

"""Seed the database with the 32 padas, default categories and sample rules.

Idempotent -- safe to run repeatedly. Run with:

    uv run scripts/seed_all.py

(The backend also auto-seeds on startup; this script forces a full re-seed.)
"""

import asyncio
import logging

from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings
from app.db.seed import ensure_seed_data

logging.basicConfig(level=logging.INFO)


async def main() -> None:
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.DATABASE_NAME]
    await ensure_seed_data(db, force=True)
    client.close()


if __name__ == "__main__":
    asyncio.run(main())

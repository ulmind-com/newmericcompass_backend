"""Populate the `vastu_rules` collection from app/db/seed/vastu_rules_seed.json.

Run with: uv run scripts/seed_vastu_rules.py
"""

import asyncio
import json
import logging
from pathlib import Path

from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SEED_FILE = Path(__file__).resolve().parent.parent / "app" / "db" / "seed" / "vastu_rules_seed.json"


async def seed_vastu_rules() -> None:
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.DATABASE_NAME]
    collection = db["vastu_rules"]

    await collection.create_index([("room_type", 1), ("direction", 1)], unique=True)

    rules = json.loads(SEED_FILE.read_text())

    for rule in rules:
        await collection.update_one(
            {"room_type": rule["room_type"], "direction": rule["direction"]},
            {"$set": rule},
            upsert=True,
        )

    logger.info("Seeded %d Vastu rules into '%s.vastu_rules'.", len(rules), settings.DATABASE_NAME)
    client.close()


if __name__ == "__main__":
    asyncio.run(seed_vastu_rules())

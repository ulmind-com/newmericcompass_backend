"""Create or update an admin account.

Usage:
    uv run scripts/create_admin.py <email> <password> [name]

Or set ADMIN_EMAIL / ADMIN_PASSWORD / ADMIN_NAME env vars and run with no args.
"""

import asyncio
import logging
import os
import sys

from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings
from app.core.security import get_password_hash

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def create_admin(email: str, password: str, name: str) -> None:
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.DATABASE_NAME]
    await db.admins.create_index("email", unique=True)

    await db.admins.update_one(
        {"email": email.lower()},
        {"$set": {
            "email": email.lower(),
            "name": name,
            "hashed_password": get_password_hash(password),
            "role": "admin",
            "is_active": True,
        }},
        upsert=True,
    )
    logger.info("Admin ready: %s", email.lower())
    client.close()


if __name__ == "__main__":
    if len(sys.argv) >= 3:
        email, password = sys.argv[1], sys.argv[2]
        name = sys.argv[3] if len(sys.argv) > 3 else "Administrator"
    else:
        email = os.getenv("ADMIN_EMAIL")
        password = os.getenv("ADMIN_PASSWORD")
        name = os.getenv("ADMIN_NAME", "Administrator")
        if not email or not password:
            raise SystemExit(
                "Provide <email> <password> as args or ADMIN_EMAIL/ADMIN_PASSWORD env vars."
            )
    asyncio.run(create_admin(email, password, name))

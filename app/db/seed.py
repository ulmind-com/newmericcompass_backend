"""Idempotent database seeding for padas, categories, sample rules and admin.

Used both by the startup auto-seed (see app.main lifespan) and the standalone
`scripts/seed_all.py`. Safe to run repeatedly: structural pada fields are always
refreshed, while editable content is only set on insert so admin edits survive.
"""

import logging
import os

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.security import get_password_hash
from app.domain.padas import all_padas

logger = logging.getLogger(__name__)

# icon_key maps to a bundled icon in the mobile app.
CATEGORIES = [
    ("main-entrance", "Main Entrance", "door"),
    ("bedroom", "Bedroom", "bed"),
    ("kitchen", "Kitchen", "kitchen"),
    ("toilet", "Toilet", "toilet"),
    ("washing-area", "Washing Area", "washing"),
    ("dustbin", "Dustbin", "dustbin"),
    ("temple", "Temple", "temple"),
    ("study-room", "Study Room", "study"),
    ("guest-room", "Guest Room", "guest"),
    ("drawing-room", "Drawing Room", "drawing"),
    ("dining-hall", "Dining Hall", "dining"),
    ("living-room", "Living Room", "living"),
    ("kids-room", "Kids Room", "kids"),
    ("store-room", "Store Room", "store"),
    ("staircase", "Staircase", "stairs"),
    ("inverter", "Inverter", "inverter"),
    ("heater", "Heater", "heater"),
    ("ac", "AC", "ac"),
    ("water-tank", "Water Tank", "water-tank"),
    ("safe-locker", "Safe / Locker", "safe"),
]

# (category_slug, pada_code, verdict, score, [effects], [treatments])
SAMPLE_RULES = [
    ("main-entrance", "N5", "good", 78,
     ["An entrance in the North attracts new money opportunities and career growth.",
      "Occupants tend to value relationships and financial stability."],
     ["Keep this entrance clutter-free and well-lit.",
      "Use shades of blue or green near the doorway."]),
    ("main-entrance", "E5", "excellent", 92,
     ["An East entrance brings social recognition and strong connections.",
      "Supports clarity of thought and good health for the family."],
     ["Maintain an open, bright approach to the door.",
      "Avoid heavy storage around this entrance."]),
    ("main-entrance", "S1", "bad", 28,
     ["A South-East main door can raise conflict and impulsive spending.",
      "Excess fire energy may cause irritability among occupants."],
     ["Place a brass Vastu pyramid above the door frame.",
      "Avoid red tones; introduce cooling greens."]),
    ("toilet", "N5", "bad", 24,
     ["A toilet in the North drains money and career opportunities.",
      "Can create obstacles in cash flow and professional growth."],
     ["Keep the toilet door closed at all times.",
      "Place a sea-salt bowl inside and replace it weekly.",
      "Use light grey / white tiles, avoid dark colours."]),
    ("toilet", "W5", "good", 72,
     ["A toilet in the West is largely neutral and supports gains.",
      "Minimal negative impact when kept clean and dry."],
     ["Ensure good ventilation and keep the space dry."]),
    ("kitchen", "S1", "excellent", 95,
     ["The South-East (Agni) corner is the ideal placement for the kitchen.",
      "Supports health, digestion and financial energy."],
     ["Position the cooking stove so the cook faces East."]),
    ("kitchen", "N5", "bad", 20,
     ["A kitchen in the North weakens money-attraction energy.",
      "The fire element conflicts with the water zone of the North."],
     ["Relocate if possible; otherwise add earth-element decor.",
      "Avoid a blue colour scheme in a North kitchen."]),
    ("temple", "N8", "excellent", 98,
     ["The North-East (Ishanya) is the most auspicious spot for a temple.",
      "Enhances clarity, devotion and positive energy in the home."],
     ["Keep idols facing West so worshippers face East.",
      "Keep the zone spotless and free of storage."]),
    ("bedroom", "W1", "excellent", 90,
     ["The South-West master bedroom grants stability and strong relationships.",
      "Promotes restful sleep and authority for the head of the family."],
     ["Sleep with the head towards the South.",
      "Use heavy, earthy furniture in this room."]),
    ("bedroom", "N8", "bad", 26,
     ["A bedroom in the North-East disturbs mental clarity and sleep.",
      "This spiritual zone is better left open and lightly used."],
     ["Keep the North-East corner uncluttered and airy.",
      "Prefer light furnishings; sleep head towards South."]),
]


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    await db.padas.create_index("code", unique=True)
    await db.padas.create_index("index", unique=True)
    await db.categories.create_index("slug", unique=True)
    await db.vastu_rules.create_index([("category_slug", 1), ("pada_code", 1)], unique=True)
    await db.submissions.create_index("created_at")
    await db.admins.create_index("email", unique=True)


_STRUCTURAL = {"index", "quadrant", "quadrant_index", "center_deg", "start_deg",
               "end_deg", "direction16", "direction16_full", "direction8"}


async def _seed_padas(db: AsyncIOMotorDatabase) -> None:
    for pada in all_padas():
        code = pada["code"]
        set_fields = {k: v for k, v in pada.items() if k in _STRUCTURAL}
        insert_fields = {k: v for k, v in pada.items() if k not in _STRUCTURAL and k != "code"}
        await db.padas.update_one(
            {"code": code}, {"$set": set_fields, "$setOnInsert": insert_fields}, upsert=True
        )


async def _seed_categories(db: AsyncIOMotorDatabase) -> None:
    for order, (slug, name, icon_key) in enumerate(CATEGORIES):
        await db.categories.update_one(
            {"slug": slug},
            {"$set": {"name": name, "icon_key": icon_key, "order": order, "is_active": True},
             "$setOnInsert": {"slug": slug, "icon_url": None}},
            upsert=True,
        )


async def _seed_rules(db: AsyncIOMotorDatabase) -> None:
    for slug, pada, verdict, score, effects, treatments in SAMPLE_RULES:
        await db.vastu_rules.update_one(
            {"category_slug": slug, "pada_code": pada},
            {"$set": {"verdict": verdict, "score": score, "effects": effects,
                      "treatments": treatments, "is_active": True},
             "$setOnInsert": {"category_slug": slug, "pada_code": pada, "notes": None}},
            upsert=True,
        )


async def _seed_admin_from_env(db: AsyncIOMotorDatabase) -> None:
    email = os.getenv("ADMIN_EMAIL")
    password = os.getenv("ADMIN_PASSWORD")
    if not email or not password:
        return
    if await db.admins.find_one({"email": email.lower()}):
        return
    await db.admins.insert_one({
        "email": email.lower(),
        "name": os.getenv("ADMIN_NAME", "Administrator"),
        "hashed_password": get_password_hash(password),
        "role": "admin",
        "is_active": True,
    })
    logger.info("Auto-created admin %s", email.lower())


async def ensure_seed_data(db: AsyncIOMotorDatabase, force: bool = False) -> None:
    """Seed if empty (or force). Idempotent; preserves admin edits."""
    await ensure_indexes(db)
    pada_count = await db.padas.count_documents({})
    cat_count = await db.categories.count_documents({})

    if force or pada_count < 32 or cat_count == 0:
        await _seed_padas(db)
        await _seed_categories(db)
        await _seed_rules(db)
        logger.info("Seed complete: 32 padas, %d categories, %d sample rules.",
                    len(CATEGORIES), len(SAMPLE_RULES))
    else:
        logger.info("Seed skipped (already populated: %d padas, %d categories).", pada_count, cat_count)

    await _seed_admin_from_env(db)

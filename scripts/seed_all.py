"""Seed the database with the 32 padas, default categories and sample rules.

Idempotent -- safe to run repeatedly. Run with:

    uv run scripts/seed_all.py         # or: python -m scripts.seed_all
"""

import asyncio
import logging

from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings
from app.domain.padas import all_padas

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Default category grid (mirrors a typical Vastu compass app). icon_key maps to
# a bundled icon in the mobile app; icon_url can override it from the admin panel.
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

# A representative set of rules so the app shows rich content out of the box.
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


async def seed():
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.DATABASE_NAME]

    # Indexes
    await db.padas.create_index("code", unique=True)
    await db.padas.create_index("index", unique=True)
    await db.categories.create_index("slug", unique=True)
    await db.vastu_rules.create_index([("category_slug", 1), ("pada_code", 1)], unique=True)
    await db.submissions.create_index("created_at")
    await db.admins.create_index("email", unique=True)

    # Padas -- upsert attributes but do not clobber admin edits blindly:
    # only $set the immutable structural fields, $setOnInsert the editable ones.
    structural = {"index", "quadrant", "quadrant_index", "center_deg", "start_deg",
                  "end_deg", "direction16", "direction16_full", "direction8"}
    for pada in all_padas():
        code = pada["code"]
        set_fields = {k: v for k, v in pada.items() if k in structural}
        insert_fields = {k: v for k, v in pada.items() if k not in structural and k != "code"}
        await db.padas.update_one(
            {"code": code},
            {"$set": set_fields, "$setOnInsert": insert_fields},
            upsert=True,
        )
    logger.info("Seeded 32 padas.")

    # Categories
    for order, (slug, name, icon_key) in enumerate(CATEGORIES):
        await db.categories.update_one(
            {"slug": slug},
            {"$set": {"name": name, "icon_key": icon_key, "order": order, "is_active": True},
             "$setOnInsert": {"slug": slug, "icon_url": None}},
            upsert=True,
        )
    logger.info("Seeded %d categories.", len(CATEGORIES))

    # Sample rules
    for slug, pada, verdict, score, effects, treatments in SAMPLE_RULES:
        await db.vastu_rules.update_one(
            {"category_slug": slug, "pada_code": pada},
            {"$set": {"verdict": verdict, "score": score, "effects": effects,
                      "treatments": treatments, "is_active": True},
             "$setOnInsert": {"category_slug": slug, "pada_code": pada, "notes": None}},
            upsert=True,
        )
    logger.info("Seeded %d sample rules.", len(SAMPLE_RULES))

    client.close()
    logger.info("Done.")


if __name__ == "__main__":
    asyncio.run(seed())

"""Idempotent database seeding: padas, categories (with best/avoid directions),
a full set of category x direction rules, and an admin from env.

Used by the startup auto-seed (app.main lifespan) and scripts/seed_all.py.
Structural pada fields are always refreshed; editable content is only set on
insert so admin edits survive re-runs.
"""

import logging
import os
from datetime import datetime, timedelta, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.security import get_password_hash
from app.domain.padas import DIRECTION_16, DIRECTION_16_FULL, all_padas

logger = logging.getLogger(__name__)

# --- Categories: (slug, name, icon_key) ---
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

# Nearest 8-wind parent for each 16-wind direction.
MAP16TO8 = {
    "N": "N", "NNE": "NE", "NE": "NE", "ENE": "E", "E": "E", "ESE": "SE",
    "SE": "SE", "SSE": "S", "S": "S", "SSW": "SW", "SW": "SW", "WSW": "W",
    "W": "W", "WNW": "NW", "NW": "NW", "NNW": "N",
}
# Representative pada (its 16-wind zone centre) for each direction.
REP = {
    "N": "N5", "NNE": "N7", "NE": "E1", "ENE": "E3", "E": "E5", "ESE": "E7",
    "SE": "S1", "SSE": "S3", "S": "S5", "SSW": "S7", "SW": "W1", "WSW": "W3",
    "W": "W5", "WNW": "W7", "NW": "N1", "NNW": "N3",
}

# Per-category Vastu profile (8-wind sets) + flavour text.
# best -> excellent, good -> good, bad -> bad, everything else -> average.
PROFILES = {
    "main-entrance": (["N", "E", "NE"], ["NW", "W"], ["SW", "S"],
                      "money, opportunities and career growth",
                      "Place a brass Vastu pyramid or a Swastik above the door and keep the entry brightly lit."),
    "bedroom": (["SW"], ["S", "W"], ["NE", "SE"],
                "stability, sound sleep and strong relationships",
                "Sleep with the head to the South; add a heavy earth-element item in the SW."),
    "kitchen": (["SE"], ["NW", "S"], ["NE", "N", "SW"],
                "health, digestion and financial energy",
                "Position the stove so the cook faces East; avoid a blue colour scheme."),
    "toilet": (["NW"], ["W"], ["NE", "N", "E", "SW", "SE"],
               "money flow and health",
               "Keep the door shut, place a sea-salt bowl inside, and use light grey/white tiles."),
    "washing-area": (["NW", "W"], ["SE"], ["NE", "SW"],
                     "smooth daily routines and hygiene",
                     "Keep drainage flowing towards the North-East and the area dry."),
    "dustbin": (["S", "SW", "W"], ["NW"], ["NE", "N", "E"],
                "disposal of negativity and waste",
                "Use a covered bin and empty it daily; never keep waste in the NE."),
    "temple": (["NE"], ["N", "E"], ["S", "SW", "W"],
               "clarity, devotion and positive energy",
               "Keep idols facing West (worshipper faces East) and the zone spotless."),
    "study-room": (["NE", "E", "N"], ["W"], ["SE", "S", "SW"],
                   "concentration, memory and academic success",
                   "Sit facing East or North while studying; keep the desk clutter-free."),
    "guest-room": (["NW"], ["W", "S"], ["NE", "SE"],
                   "hospitality and short, pleasant stays",
                   "Use light furnishings and keep the NE corner of the room open."),
    "drawing-room": (["N", "E", "NE"], ["NW"], ["SW", "SE"],
                     "social connections and reputation",
                     "Seat the head of the family facing East/North; keep the centre open."),
    "dining-hall": (["W"], ["E", "S"], ["NE", "SW"],
                    "health, bonding and good appetite",
                    "Face East or West while eating; avoid a toilet adjacent to it."),
    "living-room": (["N", "E", "NE"], ["NW", "W"], ["SW"],
                    "harmony, guests and positive vibes",
                    "Keep heavy furniture in the South/West and the NE light and open."),
    "kids-room": (["W", "NW"], ["N", "E"], ["SW", "S"],
                  "growth, focus and good sleep for children",
                  "Let children sleep with the head to the East/South; study facing East."),
    "store-room": (["SW", "S", "W"], ["NW"], ["NE", "E"],
                   "stability and orderly storage",
                   "Store heavy goods in the SW; never store in the NE."),
    "staircase": (["SW", "S", "W"], ["NW", "SE"], ["NE", "N", "E"],
                  "steady progress without draining energy",
                  "Build stairs clockwise in the South/West; keep the NE free of stairs."),
    "inverter": (["SE"], ["S", "NW"], ["NE", "N"],
                 "reliable power and fire-element balance",
                 "Place electrical/fire equipment in the SE; keep it off the NE."),
    "heater": (["SE"], ["S"], ["NE", "N", "NW"],
               "warmth and fire-element balance",
               "Keep heating appliances in the SE (Agni) corner."),
    "ac": (["W", "NW"], ["N", "E"], ["SE"],
           "comfort and cool air flow",
           "Mount the AC on the West/North wall; avoid the fiery SE."),
    "water-tank": (["NE"], ["N", "E"], ["SW", "S", "SE"],
                   "wealth and health from the water element",
                   "Keep underground water in the NE; overhead tanks in the SW/W."),
    "safe-locker": (["SW", "S"], ["N"], ["NE", "E"],
                    "wealth accumulation and savings",
                    "Place the locker in the SW so it opens towards the North."),
}

_SCORE = {"excellent": 92, "good": 76, "average": 50, "bad": 24}


def _rule_content(name: str, dir16: str, verdict: str, benefit: str, remedy: str):
    full = DIRECTION_16_FULL[dir16]
    if verdict == "excellent":
        return ([f"The {full} is an ideal, auspicious location for the {name} — one of the best placements in Vastu.",
                 f"Strongly enhances {benefit}."],
                ["Keep this zone clean, well-lit and clutter-free to preserve the positive energy."])
    if verdict == "good":
        return ([f"The {name} in the {full} is favourable and works well with a little care.",
                 f"Gently supports {benefit}."],
                ["Maintain the area tidy and well-ventilated."])
    if verdict == "bad":
        return ([f"A {name} in the {full} creates a Vastu dosh and can cause obstacles.",
                 f"May weaken {benefit} and household harmony."],
                [remedy, "Keep the area closed/covered when not in use and free of clutter."])
    return ([f"A {name} in the {full} is broadly neutral — neither strongly beneficial nor harmful.",
             "Its effect depends on the overall layout."],
            ["No major remedy needed; simply keep the space clean and organised."])


def _verdict_for(dir16: str, best, good, bad) -> str:
    p = MAP16TO8[dir16]
    if p in best:
        return "excellent"
    if p in good:
        return "good"
    if p in bad:
        return "bad"
    return "average"


def build_category_rules():
    """Yield (slug, name, best_dirs, avoid_dirs, [rule_dicts]) for every category."""
    name_by_slug = {slug: name for slug, name, _ in CATEGORIES}
    for slug, (best, good, bad, benefit, remedy) in PROFILES.items():
        name = name_by_slug.get(slug, slug.title())
        best_dirs = [d for d in DIRECTION_16 if MAP16TO8[d] in best]
        avoid_dirs = [d for d in DIRECTION_16 if MAP16TO8[d] in bad]
        rules = []
        for dir16 in DIRECTION_16:
            verdict = _verdict_for(dir16, best, good, bad)
            effects, treatments = _rule_content(name, dir16, verdict, benefit, remedy)
            rules.append({
                "category_slug": slug, "pada_code": REP[dir16], "verdict": verdict,
                "score": _SCORE[verdict], "effects": effects,
                "treatments": treatments,
                "is_active": True, "notes": None,
            })
        yield slug, name, best_dirs, avoid_dirs, rules


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    await db.padas.create_index("code", unique=True)
    await db.padas.create_index("index", unique=True)
    await db.categories.create_index("slug", unique=True)
    await db.vastu_rules.create_index([("category_slug", 1), ("pada_code", 1)], unique=True)
    await db.submissions.create_index("created_at")
    await db.admins.create_index("email", unique=True)
    await db.users.create_index("email", unique=True)


_STRUCTURAL = {"index", "quadrant", "quadrant_index", "center_deg", "start_deg",
               "end_deg", "direction16", "direction16_full", "direction8"}


async def _seed_padas(db: AsyncIOMotorDatabase) -> None:
    # Full refresh of the pada master (runs only on first seed or SEED_VERSION bump).
    for pada in all_padas():
        code = pada["code"]
        fields = {k: v for k, v in pada.items() if k != "code"}
        await db.padas.update_one({"code": code}, {"$set": fields}, upsert=True)


async def _seed_categories_and_rules(db: AsyncIOMotorDatabase) -> None:
    order = 0
    icon_by_slug = {slug: icon for slug, _, icon in CATEGORIES}
    rule_count = 0
    for slug, name, best_dirs, avoid_dirs, rules in build_category_rules():
        await db.categories.update_one(
            {"slug": slug},
            {"$set": {"name": name, "icon_key": icon_by_slug.get(slug), "order": order,
                      "is_active": True, "best_directions": best_dirs, "avoid_directions": avoid_dirs},
             "$setOnInsert": {"slug": slug, "icon_url": None}},
            upsert=True,
        )
        order += 1
        for r in rules:
            await db.vastu_rules.update_one(
                {"category_slug": r["category_slug"], "pada_code": r["pada_code"]},
                {"$set": {k: r[k] for k in ("verdict", "score", "effects", "treatments", "is_active")},
                 "$setOnInsert": {"category_slug": r["category_slug"], "pada_code": r["pada_code"], "notes": None}},
                upsert=True,
            )
            rule_count += 1
    logger.info("Seeded %d categories and %d rules.", len(PROFILES), rule_count)


# Starter pricing so the app has something to show on day one. The admin edits
# these from the panel; they are only inserted when the collection is empty, so
# a live price is never overwritten by a redeploy.
STARTER_PLANS = [
    {"slug": "submissions-monthly", "feature": "submissions", "kind": "subscription",
     "name": "Monthly", "description": "Send placement reports for a month.",
     "amount": 49900, "currency": "INR", "duration_days": 30, "submission_quota": 25,
     "is_popular": False, "is_active": True, "order": 0},
    {"slug": "submissions-yearly", "feature": "submissions", "kind": "subscription",
     "name": "Yearly", "description": "A year of reports, at a better rate.",
     "amount": 399900, "currency": "INR", "duration_days": 365, "submission_quota": 400,
     "is_popular": True, "is_active": True, "order": 1},
    {"slug": "submissions-lifetime", "feature": "submissions", "kind": "subscription",
     "name": "Lifetime", "description": "Unlimited reports, no renewal.",
     "amount": 999900, "currency": "INR", "duration_days": None, "submission_quota": None,
     "is_popular": False, "is_active": True, "order": 2},
    {"slug": "analysis-unlock", "feature": "analysis", "kind": "one_time",
     "name": "Unlock Analysis", "description": "Zone verdicts, effects and treatments. One payment, forever.",
     "amount": 29900, "currency": "INR", "duration_days": None, "submission_quota": None,
     "is_popular": False, "is_active": True, "order": 0},
    {"slug": "nexus-unlock", "feature": "nexus", "kind": "one_time",
     "name": "Unlock 7D Nexus", "description": "The full master code: lord, planet, metal, shape and colour remedies.",
     "amount": 49900, "currency": "INR", "duration_days": None, "submission_quota": None,
     "is_popular": False, "is_active": True, "order": 0},
]


async def _seed_plans(db: AsyncIOMotorDatabase) -> None:
    if await db.plans.count_documents({}) > 0:
        logger.info("Plans already present; leaving pricing alone.")
        return
    await db.plans.insert_many([{**p, "created_at": datetime.now(timezone.utc)} for p in STARTER_PLANS])
    logger.info("Seeded %d starter plans.", len(STARTER_PLANS))


# Placeholder menu links so the side menu is not empty before the owner fills
# in their real channels. Only inserted when the collection is empty.
STARTER_LINKS = [
    {"section": "social", "platform": "facebook", "title": "Facebook",
     "subtitle": "Follow the page", "url": "https://facebook.com/", "order": 0, "is_active": True},
    {"section": "social", "platform": "instagram", "title": "Instagram",
     "subtitle": "Follow us", "url": "https://instagram.com/", "order": 1, "is_active": True},
    {"section": "social", "platform": "youtube", "title": "YouTube",
     "subtitle": "Subscribe", "url": "https://youtube.com/", "order": 2, "is_active": True},
    {"section": "social", "platform": "whatsapp", "title": "WhatsApp",
     "subtitle": "Message us", "url": "https://wa.me/", "order": 3, "is_active": True},
]


async def _seed_app_links(db: AsyncIOMotorDatabase) -> None:
    if await db.app_links.count_documents({}) > 0:
        return
    await db.app_links.insert_many([{**l, "created_at": datetime.now(timezone.utc)} for l in STARTER_LINKS])
    logger.info("Seeded %d placeholder menu links.", len(STARTER_LINKS))


async def _seed_demo(db: AsyncIOMotorDatabase) -> None:
    """Insert demo users / submissions / tips so every admin page has data.
    Each collection is only touched when empty, so real sign-ups are never lost."""
    now = datetime.now(timezone.utc)

    if await db.users.count_documents({}) == 0:
        pw = get_password_hash("demo1234")
        demo = [
            ("Aarav Sharma", "aarav@example.com", "+91 98000 00001", True, "active", 2),
            ("Diya Patel", "diya@example.com", "+91 98000 00002", False, "active", 6),
            ("Vihaan Gupta", "vihaan@example.com", "+91 98000 00003", True, "active", 9),
            ("Ananya Singh", "ananya@example.com", "+91 98000 00004", False, "active", 13),
            ("Kabir Mehta", "kabir@example.com", "+91 98000 00005", False, "blocked", 20),
            ("Isha Reddy", "isha@example.com", "+91 98000 00006", True, "active", 27),
            ("Rohan Nair", "rohan@example.com", "+91 98000 00007", False, "active", 34),
            ("Sara Khan", "sara@example.com", "+91 98000 00008", False, "active", 41),
        ]
        await db.users.insert_many([
            {"name": n, "email": e, "whatsapp": w, "phone": None, "hashed_password": pw,
             "is_premium": prem, "status": st, "role": "user", "created_at": now - timedelta(days=days)}
            for n, e, w, prem, st, days in demo
        ])

    if await db.submissions.count_documents({}) == 0:
        await db.submissions.insert_many([
            {"device_id": None, "title": "3BHK Flat — Kolkata", "name": "Aarav Sharma",
             "whatsapp": "+91 98000 00001", "email": "aarav@example.com",
             "items": [{"category_slug": "main-entrance", "category_name": "Main Entrance", "degree": 46.0, "pada_code": "E1", "direction16": "NE", "verdict": "excellent"},
                       {"category_slug": "kitchen", "category_name": "Kitchen", "degree": 135.0, "pada_code": "S1", "direction16": "SE", "verdict": "excellent"},
                       {"category_slug": "toilet", "category_name": "Toilet", "degree": 4.0, "pada_code": "N5", "direction16": "N", "verdict": "bad"}],
             "created_at": now - timedelta(days=1)},
            {"device_id": None, "title": "Villa — Pune", "name": "Isha Reddy",
             "whatsapp": "+91 98000 00006", "email": "isha@example.com",
             "items": [{"category_slug": "temple", "category_name": "Temple", "degree": 45.0, "pada_code": "E1", "direction16": "NE", "verdict": "excellent"},
                       {"category_slug": "bedroom", "category_name": "Bedroom", "degree": 225.0, "pada_code": "W1", "direction16": "SW", "verdict": "excellent"}],
             "created_at": now - timedelta(days=3)},
            {"device_id": None, "title": "Office — Mumbai", "name": "Vihaan Gupta",
             "whatsapp": "+91 98000 00003", "email": "vihaan@example.com",
             "items": [{"category_slug": "safe-locker", "category_name": "Safe / Locker", "degree": 225.0, "pada_code": "W1", "direction16": "SW", "verdict": "excellent"}],
             "created_at": now - timedelta(days=5)},
        ])

    if await db.tips.count_documents({}) == 0:
        await db.tips.insert_many([
            {"title": "Keep the North-East light", "body": "The NE (Ishanya) should stay open, clean and clutter-free to invite positive energy and clarity.", "category_slug": None, "image_url": None, "order": 0, "is_active": True},
            {"title": "Cook facing East", "body": "Place the stove in the South-East so the cook faces East — it supports health and prosperity.", "category_slug": "kitchen", "image_url": None, "order": 1, "is_active": True},
            {"title": "Sleep head to the South", "body": "In the master bedroom (South-West), sleep with your head towards the South for restful, stable sleep.", "category_slug": "bedroom", "image_url": None, "order": 2, "is_active": True},
            {"title": "Toilet doors shut", "body": "Always keep toilet doors closed and add a sea-salt bowl to neutralise negative energy.", "category_slug": "toilet", "image_url": None, "order": 3, "is_active": True},
        ])
    logger.info("Demo data ensured (users/submissions/tips).")


async def _seed_admin_from_env(db: AsyncIOMotorDatabase) -> None:
    email = os.getenv("ADMIN_EMAIL")
    password = os.getenv("ADMIN_PASSWORD")
    if not email or not password or await db.admins.find_one({"email": email.lower()}):
        return
    await db.admins.insert_one({
        "email": email.lower(), "name": os.getenv("ADMIN_NAME", "Administrator"),
        "hashed_password": get_password_hash(password), "role": "admin", "is_active": True,
    })
    logger.info("Auto-created admin %s", email.lower())


# Bump this whenever the seed content changes so already-populated deployments
# pick up the new data automatically on their next startup.
SEED_VERSION = 11


async def ensure_seed_data(db: AsyncIOMotorDatabase, force: bool = False) -> None:
    """Seed on first run or when SEED_VERSION advances (or force). Idempotent."""
    await ensure_indexes(db)
    meta = await db.meta.find_one({"_id": "seed"})
    current = (meta or {}).get("version", 0)

    if force or current < SEED_VERSION:
        await _seed_padas(db)
        await _seed_categories_and_rules(db)
        await _seed_plans(db)
        await _seed_app_links(db)
        await _seed_demo(db)
        await db.meta.update_one({"_id": "seed"}, {"$set": {"version": SEED_VERSION}}, upsert=True)
        logger.info("Seed complete (version %d).", SEED_VERSION)
    else:
        logger.info("Seed skipped (already at version %d).", current)

    await _seed_admin_from_env(db)

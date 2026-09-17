"""Everything the assistant is allowed to know, as retrievable passages.

Two sources, one shape. The reading screens ship their text inside the app, and
`app_content.json` is that text exported passage by passage. The rest — rules,
padas, categories, tips, day protocols — lives in Mongo and is edited from the
admin panel, so it is read fresh every time the index is built.

Both arrive as `Passage`, and nothing else is ever put in front of the model.
That is the whole guarantee: the assistant cannot answer from outside the app,
because outside the app was never loaded.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

STATIC_CORPUS = Path(__file__).resolve().parents[2] / "data" / "app_content.json"


@dataclass(slots=True)
class Passage:
    """One citable piece of the app."""

    id: str
    screen: str
    route: str
    trail: list[str]
    text: str
    #: Set when the index is built; not part of the passage's identity.
    vector: list[float] = field(default_factory=list)

    @property
    def heading(self) -> str:
        return " — ".join(self.trail)

    def for_embedding(self) -> str:
        """The heading trail rides along with the text.

        A zone passage says "Remedy: keep the compressor in SE" without ever
        naming the category, because on screen the category is the page title.
        Embedded without its trail it would never come back for "air
        conditioner remedy".
        """
        return f"{self.heading}\n{self.text}"

    def to_doc(self) -> dict[str, Any]:
        return {
            "_id": self.id,
            "screen": self.screen,
            "route": self.route,
            "trail": self.trail,
            "text": self.text,
            "vector": self.vector,
        }

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "Passage":
        return cls(
            id=doc["_id"],
            screen=doc["screen"],
            route=doc["route"],
            trail=doc.get("trail") or [],
            text=doc["text"],
            vector=doc.get("vector") or [],
        )


def load_static() -> list[Passage]:
    """The reading screens, as exported from the app repo."""
    if not STATIC_CORPUS.exists():
        logger.warning("No static corpus at %s", STATIC_CORPUS)
        return []
    raw = json.loads(STATIC_CORPUS.read_text())
    return [
        Passage(id=p["id"], screen=p["screen"], route=p["route"], trail=p["trail"], text=p["text"])
        for p in raw
    ]


def _clean(value: Any) -> str:
    return str(value).strip() if value not in (None, "") else ""


def _join(lines: list[str]) -> str:
    return "\n".join(line for line in lines if line)


async def load_dynamic(db: AsyncIOMotorDatabase) -> list[Passage]:
    """The content the admin panel owns, read at index time.

    Kept separate from the static half so that editing a rule and rebuilding the
    index is enough — the app does not have to ship again for the assistant to
    know about the change.
    """
    out: list[Passage] = []

    categories = await db.categories.find({"is_active": True}).to_list(length=200)
    by_slug = {c["slug"]: c for c in categories}
    for c in categories:
        out.append(Passage(
            id=f"category:{c['slug']}",
            screen="Compass — categories",
            route="/compass",
            trail=["Categories", c["name"]],
            text=_join([
                f"{c['name']} is one of the placement categories you can analyse.",
                f"Best directions: {', '.join(c.get('best_directions') or []) or 'not specified'}.",
                f"Directions to avoid: {', '.join(c.get('avoid_directions') or []) or 'not specified'}.",
            ]),
        ))

    padas = await db.padas.find({}).sort("index", 1).to_list(length=64)
    by_pada = {p["code"]: p for p in padas}
    for p in padas:
        out.append(Passage(
            id=f"pada:{p['code']}",
            screen="Compass — padas",
            route="/compass",
            trail=["The 32 padas", f"{p['code']}{f' — {p['name']}' if p.get('name') else ''}"],
            text=_join([
                f"Pada {p['code']} is number {p.get('index')} of the 32, in the {_clean(p.get('quadrant'))} quadrant.",
                f"It spans {p.get('start_deg')}° to {p.get('end_deg')}°, centred on {p.get('center_deg')}°.",
                f"Name: {_clean(p.get('name'))}." if p.get("name") else "",
                f"Element: {_clean(p.get('element'))}." if p.get("element") else "",
                f"Dosha: {_clean(p.get('dosha'))}." if p.get("dosha") else "",
                f"Organ: {_clean(p.get('organ'))}." if p.get("organ") else "",
                f"Life aspect: {_clean(p.get('life_aspect'))}." if p.get("life_aspect") else "",
                f"Nakshatra: {_clean(p.get('nakshatra'))}." if p.get("nakshatra") else "",
            ]),
        ))

    rules = await db.vastu_rules.find({"is_active": True}).to_list(length=5000)
    for r in rules:
        cat = by_slug.get(r["category_slug"], {})
        pada = by_pada.get(r["pada_code"], {})
        name = cat.get("name") or r["category_slug"]
        pada_name = f"{r['pada_code']}{f' ({pada['name']})' if pada.get('name') else ''}"
        out.append(Passage(
            id=f"rule:{r['category_slug']}:{r['pada_code']}",
            screen="Placement verdict",
            route="/compass",
            trail=["Placement verdicts", f"{name} in pada {pada_name}"],
            text=_join([
                f"{name} placed in pada {pada_name}: verdict {_clean(r.get('verdict'))}, score {r.get('score')} out of 100.",
                ("Effects:\n" + "\n".join(f"• {e}" for e in r["effects"])) if r.get("effects") else "",
                ("Treatment:\n" + "\n".join(f"• {t}" for t in r["treatments"])) if r.get("treatments") else "",
                _clean(r.get("notes")),
            ]),
        ))

    days = await db.day_protocols.find({"is_active": True}).sort("weekday", 1).to_list(length=14)
    for d in days:
        out.append(Passage(
            id=f"day:{d['weekday']}",
            screen="Day-Wise Remedy",
            route="/days",
            trail=["Day-Wise Remedy", f"{d['day_name']} — {d.get('planet', '')}".strip(" —")],
            text=_join([
                f"{d['day_name']} is governed by {_clean(d.get('planet'))} and carries {_clean(d.get('energy'))}.",
                f"Objective: {_clean(d.get('objective'))}.",
                ("Actions for the day:\n" + "\n".join(f"• {a}" for a in d["actions"])) if d.get("actions") else "",
                f"Zones this day works on: {', '.join(d.get('focus_zones') or [])}." if d.get("focus_zones") else "",
                _clean(d.get("deep_logic")),
            ]),
        ))

    tips = await db.tips.find({"is_active": True}).sort("order", 1).to_list(length=500)
    for i, t in enumerate(tips):
        out.append(Passage(
            id=f"tip:{t.get('_id', i)}",
            screen="Vastu Essentials",
            route="/tips",
            trail=["Vastu Essentials", _clean(t.get("title"))],
            text=_join([_clean(t.get("title")), _clean(t.get("body"))]),
        ))

    return [p for p in out if len(p.text.strip()) >= 20]


async def load_all(db: AsyncIOMotorDatabase) -> list[Passage]:
    static = load_static()
    dynamic = await load_dynamic(db)
    logger.info("Corpus: %d static + %d dynamic passages", len(static), len(dynamic))
    return static + dynamic

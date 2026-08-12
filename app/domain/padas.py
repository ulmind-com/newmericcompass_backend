"""Single source of truth for the Newmeric Compass 32-pada (N5) system.

The compass is divided into 32 padas of 11.25 degrees each, grouped into four
quadrants of eight padas: N1-N8, E1-E8, S1-S8, W1-W8.

The system is anchored so that **N5 sits exactly on due North (0 degrees)** -- this
is where the "N5" branding comes from. Consequently E5 = East (90), S5 = South
(180) and W5 = West (270), while the quadrant-starting padas fall on the
inter-cardinals: N1 = NW (315), E1 = NE (45), S1 = SE (135), W1 = SW (225).

Every pada carries the attributes rendered by the app compass and configurable
from the admin panel: the 16-wind direction, the 8-wind direction, the Vastu
element (Panchabhuta), the Ayurvedic dosha, the associated body organ, the life
aspect (life area governed by the zone), an optional nakshatra, and a default
verdict used as a fallback when no category-specific rule is configured.
"""

from __future__ import annotations

PADA_SPAN = 11.25  # 360 / 32

DIRECTION_16 = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
]
DIRECTION_16_FULL = {
    "N": "North", "NNE": "North-North-East", "NE": "North-East", "ENE": "East-North-East",
    "E": "East", "ESE": "East-South-East", "SE": "South-East", "SSE": "South-South-East",
    "S": "South", "SSW": "South-South-West", "SW": "South-West", "WSW": "West-South-West",
    "W": "West", "WNW": "West-North-West", "NW": "North-West", "NNW": "North-North-West",
}
DIRECTION_8 = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]

# Per-16-wind-zone attributes (MahaVastu-aligned; fully editable from admin).
ZONE_ATTRS = {
    "N":   {"life_aspect": "Money & Opportunities",   "organ": "Kidney",       "element": "Water", "dosha": "Kapha"},
    "NNE": {"life_aspect": "Health & Immunity",       "organ": "Pericardium",  "element": "Water", "dosha": "Kapha"},
    "NE":  {"life_aspect": "Ideas & Vision",          "organ": "Head",         "element": "Water", "dosha": "Kapha"},
    "ENE": {"life_aspect": "Leisure & Joy",           "organ": "Nervous",      "element": "Air",   "dosha": "Kapha"},
    "E":   {"life_aspect": "Social Associations",     "organ": "Liver",        "element": "Air",   "dosha": "Tamas"},
    "ESE": {"life_aspect": "Analysis & Churning",     "organ": "Gall Bladder", "element": "Fire",  "dosha": "Tamas"},
    "SE":  {"life_aspect": "Cash Liquidity",          "organ": "Gall Bladder", "element": "Fire",  "dosha": "Pitta"},
    "SSE": {"life_aspect": "Power & Confidence",      "organ": "Spleen",       "element": "Fire",  "dosha": "Pitta"},
    "S":   {"life_aspect": "Fame & Relaxation",       "organ": "Stomach",      "element": "Fire",  "dosha": "Rajas"},
    "SSW": {"life_aspect": "Disposal & Spending",     "organ": "Stomach",      "element": "Earth", "dosha": "Rajas"},
    "SW":  {"life_aspect": "Relationship & Skills",   "organ": "Heart",        "element": "Earth", "dosha": "Rajas"},
    "WSW": {"life_aspect": "Education & Savings",     "organ": "Heart",        "element": "Earth", "dosha": "Vata"},
    "W":   {"life_aspect": "Gains & Fulfillment",     "organ": "Large Intestine", "element": "Air", "dosha": "Vata"},
    "WNW": {"life_aspect": "Depression & Detox",      "organ": "Colon",        "element": "Air",   "dosha": "Vata"},
    "NW":  {"life_aspect": "Bank & Support",          "organ": "Intestine",    "element": "Air",   "dosha": "Vata"},
    "NNW": {"life_aspect": "Sex & Attraction",        "organ": "Bladder",      "element": "Water", "dosha": "Kapha"},
}

# Pastel element/zone colour per 16-wind zone (matches the Newmeric Compass chart).
ZONE_COLOR = {
    "N": "#CFE8F5", "NNE": "#CFE8F5", "NE": "#CFE9C6", "ENE": "#C9E7B0",
    "E": "#C4E4A6", "ESE": "#D8E9A6", "SE": "#F4C8D6", "SSE": "#F2BCCB",
    "S": "#F3C2CB", "SSW": "#F3E6A6", "SW": "#EFE296", "WSW": "#ECE6AE",
    "W": "#DDCFEC", "WNW": "#D9C8E9", "NW": "#ECE0C6", "NNW": "#D0E6EC",
}

# --- Per-ring colours of the printed N5 chart (each one admin-editable) ---

# Ring 2: pastel band behind the life-aspect wording.
LIFE_COLOR = {
    "N": "#CDE9EF", "NNE": "#CDE9EF", "NE": "#CDE9EF", "ENE": "#DCEFC0",
    "E": "#DCEFC0", "ESE": "#DCEFC0", "SE": "#F7D9E4", "SSE": "#F7D9E4",
    "S": "#F7D9E4", "SSW": "#F9EEC4", "SW": "#F9EEC4", "WSW": "#F9EEC4",
    "W": "#EFE7D6", "WNW": "#EFE7D6", "NW": "#EFE7D6", "NNW": "#CDE9EF",
}

# Ring 4: strong band behind the 16-wind direction names.
DIR_COLOR = {
    "N": "#2D6FB8", "NNE": "#9E9E9E", "NE": "#EFE6D2", "ENE": "#4E9A2F",
    "E": "#E56AA0", "ESE": "#C9E29B", "SE": "#7CB342", "SSE": "#9E9E9E",
    "S": "#C62828", "SSW": "#F4A9C4", "SW": "#F2CE5B", "WSW": "#EFE6D2",
    "W": "#9E9E9E", "WNW": "#8D8D8D", "NW": "#EFE6D2", "NNW": "#F2CE5B",
}
# Legible ink on top of DIR_COLOR.
DIR_TEXT_COLOR = {
    "N": "#FFFFFF", "S": "#FFFFFF", "ENE": "#FFFFFF", "SE": "#FFFFFF",
}

# Ring 5: pastel band behind the pada codes (N1..W8) — a lighter tint of the zone.
PADA_BAND_COLOR = {
    "N": "#E7F4F8", "NNE": "#E7F4F8", "NE": "#E7F4F8", "ENE": "#EDF7DC",
    "E": "#EDF7DC", "ESE": "#EDF7DC", "SE": "#FCECF2", "SSE": "#FCECF2",
    "S": "#FCECF2", "SSW": "#FDF7E2", "SW": "#FDF7E2", "WSW": "#FDF7E2",
    "W": "#F7F2E7", "WNW": "#F7F2E7", "NW": "#F7F2E7", "NNW": "#E7F4F8",
}

# Rings 6 & 7: the devata / nakshatra bands alternate pastel per pada on the
# printed chart. Cycle is indexed by pada order so neighbours never repeat.
PADA_ALT_COLORS = ["#FBFAF5", "#F8DDE7", "#FBFAF5", "#DCEAF2"]

# Ring 8: the four inner Vastu Purusha Mandala lords around the Brahmasthan.
BRAHMA_QUADRANT = {
    "N": {"name": "BHUDHAR", "color": "#CDE9EF"},
    "E": {"name": "ARYAAMA", "color": "#F2C94C"},
    "S": {"name": "NYASVAN", "color": "#F08BB0"},
    "W": {"name": "MITRA", "color": "#F08BB0"},
}

# Fixed chart furniture (paper, ink, centre medallion) served through /config so
# the app never hardcodes it and the admin can restyle the whole wheel.
COMPASS_CHART = {
    "paper": "#F6EFE0",
    "line": "#C9B88F",
    "ink": "#241C12",
    "organ_color": "#D0021B",
    "needle_color": "#D0021B",
    "center_symbol": "श्री",
    "center_label": "Brahm Sthan",
    "center_bg": "#FFFFFF",
}

# The 27 nakshatras (lunar mansions). Each pada is assigned the nakshatra that
# governs its arc; the offset aligns Rohini/Pushya near North as on the chart.
NAKSHATRA_27 = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra", "Punarvasu",
    "Pushya", "Ashlesha", "Magha", "Purva Phalguni", "Uttara Phalguni", "Hasta",
    "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha", "Mula", "Purva Ashadha",
    "Uttara Ashadha", "Shravana", "Dhanishta", "Shatabhisha", "Purva Bhadrapada",
    "Uttara Bhadrapada", "Revati",
]


def _nakshatra_for(center_deg: float) -> str:
    return NAKSHATRA_27[(int(center_deg // (360 / 27)) + 7) % 27]


# Corner / zone name (Kon) per 8-wind direction. Admin-editable.
CORNER_8 = {
    "N":  "Uttar Disha (Kubera Sthan)",
    "NE": "Ishanya Kon (ईशान्य कोण)",
    "E":  "Purva Disha (Indra Sthan)",
    "SE": "Agneya Kon (आग्नेय कोण / Fire Corner)",
    "S":  "Dakshin Disha (Yama Sthan)",
    "SW": "Nairitya Kon (नैऋत्य कोण)",
    "W":  "Paschim Disha (Varuna Sthan)",
    "NW": "Vayavya Kon (वायव्य कोण / Air Corner)",
}

# --- The 8 Asta Dikpala (guardian deities), exactly as the owner supplied ---
# Each 8-wind direction has a guardian, its English identification, and the
# Vastu quality that direction governs. Seeded from this table and editable
# per pada from the admin panel.
DIR8_ATTRS = {
    "E":  {"lord": "Indra",              "deity_english": "Lord Indra",
           "vastu_association": "Power, authority, prosperity, leadership",
           "planet": "Sun",     "day": "Sunday",    "metal": "Gold"},
    "SE": {"lord": "Agni",               "deity_english": "God of Fire",
           "vastu_association": "Fire, energy, transformation",
           "planet": "Venus",   "day": "Friday",    "metal": "Silver"},
    "S":  {"lord": "Yama",               "deity_english": "Lord of Dharma & Death",
           "vastu_association": "Discipline, justice, restraint",
           "planet": "Mars",    "day": "Tuesday",   "metal": "Copper"},
    "SW": {"lord": "Nairṛitya",          "deity_english": "Deity of dissolution / protection",
           "vastu_association": "Stability, protection, containment",
           "planet": "Rahu",    "day": "Saturday",  "metal": "Lead"},
    "W":  {"lord": "Varuna",             "deity_english": "Lord of Cosmic Waters",
           "vastu_association": "Water, depth, law, flow",
           "planet": "Saturn",  "day": "Saturday",  "metal": "Stainless Steel"},
    "NW": {"lord": "Vaayu / Vayavya Kon", "deity_english": "God of Wind",
           "vastu_association": "Movement, circulation, change",
           "planet": "Moon",    "day": "Monday",    "metal": "Silver"},
    "N":  {"lord": "Kubera",             "deity_english": "Lord of Wealth",
           "vastu_association": "Wealth, finance, abundance",
           "planet": "Mercury", "day": "Wednesday", "metal": "Brass"},
    "NE": {"lord": "Isanya / Shiva",     "deity_english": "Divine aspect of Lord Shiva",
           "vastu_association": "Spirituality, wisdom, purity, divine energy",
           "planet": "Jupiter", "day": "Thursday",  "metal": "Gold"},
}

# Colour remedies derived from the five-element (Panch-Tattva) cycle.
ELEMENT_COLOURS = {
    "Water": {"self": "Blue",  "destruct": "Yellow",        "enhance": "White or Grey", "exhaust": "Green",         "acceptable": "White or Grey or Blue or Black"},
    "Air":   {"self": "Green", "destruct": "Grey or White", "enhance": "Blue",          "exhaust": "Red",           "acceptable": "Blue or Black"},
    "Fire":  {"self": "Red",   "destruct": "Blue",          "enhance": "Green",         "exhaust": "Yellow",        "acceptable": "Green or Red"},
    "Earth": {"self": "Yellow", "destruct": "Green",        "enhance": "Red",           "exhaust": "White or Grey", "acceptable": "Red or Yellow"},
}
ELEMENT_SHAPE = {"Water": "Rectangle", "Air": "Rectangle", "Fire": "Triangle", "Earth": "Square"}

# Relationship / life-area detail per 16-wind zone (dummy defaults, admin-editable).
RELATIONSHIP_16 = {
    "N": "Career, Business Deals", "NNE": "Doctors, Wellness", "NE": "Mentors, Gurus",
    "ENE": "Friends, Recreation", "E": "Social Circle, Networking", "ESE": "Advisors, Critics",
    "SE": "Bankers, Cash Flow", "SSE": "Authority, Leadership", "S": "Public, Reputation",
    "SSW": "Letting Go, Expenses", "SW": "Spouse, Life Partner", "WSW": "Teachers, Students",
    "W": "Clients, Profits", "WNW": "Isolation, Detox", "NW": "Support, Helpers",
    "NNW": "Sex-Partner, Extra Marital Affair",
}


# 32 boundary devatas / nakshatra-style names of the Vastu Purusha Mandala,
# best-effort clockwise order starting at N5 (due North). Admin-editable.
PADA_NAMES = [
    "Mukhya", "Bhallat", "Soma", "Bhujag",          # N5, N6, N7, N8
    "Aditi", "Diti", "Shikhi", "Parjanya",           # E1, E2, E3, E4
    "Jayant", "Indra", "Surya", "Satya",             # E5, E6, E7, E8
    "Bhrisha", "Antariksha", "Anila", "Pusha",       # S1, S2, S3, S4
    "Vitatha", "Grihakshat", "Yama", "Gandharva",    # S5, S6, S7, S8
    "Bhringraj", "Mriga", "Pitra", "Dauvarik",       # W1, W2, W3, W4
    "Sugriva", "Pushpdant", "Varun", "Asur",         # W5, W6, W7, W8
    "Shosha", "Papyakshma", "Roga", "Ahi",           # N1, N2, N3, N4
]


def _quadrant_codes() -> list[str]:
    """Pada codes ordered by center degree, starting at N5 (0 deg), clockwise."""
    codes: list[str] = []
    codes += [f"N{i}" for i in range(5, 9)]   # N5..N8  -> centers 0,11.25,22.5,33.75
    codes += [f"E{i}" for i in range(1, 9)]   # E1..E8  -> 45..123.75
    codes += [f"S{i}" for i in range(1, 9)]   # S1..S8  -> 135..213.75
    codes += [f"W{i}" for i in range(1, 9)]   # W1..W8  -> 225..303.75
    codes += [f"N{i}" for i in range(1, 5)]   # N1..N4  -> 315..348.75
    return codes


def build_padas() -> list[dict]:
    """Return the full 32-pada master list as plain dicts (index order 1..32)."""
    ordered = _quadrant_codes()
    padas: list[dict] = []
    for i, code in enumerate(ordered):
        center = round((i * PADA_SPAN) % 360.0, 4)
        start = round((center - PADA_SPAN / 2) % 360.0, 4)
        end = round((center + PADA_SPAN / 2) % 360.0, 4)
        d16 = DIRECTION_16[int(((center + PADA_SPAN) % 360) // 22.5) % 16]
        d8 = DIRECTION_8[int(((center + 22.5) % 360) // 45) % 8]
        attrs = ZONE_ATTRS[d16]
        # Pada display index within its quadrant (the digit in the code, e.g. N5 -> 5)
        digit = int(code[1:])
        padas.append({
            "code": code,
            "index": i + 1,
            "quadrant": code[0],
            "quadrant_index": digit,
            "center_deg": center,
            "start_deg": start,
            "end_deg": end,
            "direction16": d16,
            "direction16_full": DIRECTION_16_FULL[d16],
            "direction8": d8,
            "name": PADA_NAMES[i],
            "element": attrs["element"],
            "dosha": attrs["dosha"],
            "organ": attrs["organ"],
            "life_aspect": attrs["life_aspect"],
            "nakshatra": _nakshatra_for(center),
            "color": ZONE_COLOR[d16],
            # ---- printed-chart ring colours (all admin-editable) ----
            "life_color": LIFE_COLOR[d16],
            "dir_color": DIR_COLOR[d16],
            "dir_text_color": DIR_TEXT_COLOR.get(d16, "#241C12"),
            "pada_color": PADA_BAND_COLOR[d16],
            "devata_color": PADA_ALT_COLORS[i % len(PADA_ALT_COLORS)],
            "nakshatra_color": PADA_ALT_COLORS[(i + 2) % len(PADA_ALT_COLORS)],
            "brahma_name": BRAHMA_QUADRANT[code[0]]["name"],
            "brahma_color": BRAHMA_QUADRANT[code[0]]["color"],
            # ---- 7D NEXUS master code ----
            "corner": CORNER_8[d8],
            "lord": DIR8_ATTRS[d8]["lord"],
            "deity_english": DIR8_ATTRS[d8]["deity_english"],
            "vastu_association": DIR8_ATTRS[d8]["vastu_association"],
            "planet": DIR8_ATTRS[d8]["planet"],
            "day": DIR8_ATTRS[d8]["day"],
            "metal": DIR8_ATTRS[d8]["metal"],
            "shape": ELEMENT_SHAPE.get(attrs["element"], "Rectangle"),
            "self_colour": ELEMENT_COLOURS[attrs["element"]]["self"],
            "destruct_colour": ELEMENT_COLOURS[attrs["element"]]["destruct"],
            "enhance_colour": ELEMENT_COLOURS[attrs["element"]]["enhance"],
            "exhaust_colour": ELEMENT_COLOURS[attrs["element"]]["exhaust"],
            "acceptable_colour": ELEMENT_COLOURS[attrs["element"]]["acceptable"],
            "relationship": RELATIONSHIP_16[d16],
            "default_verdict": "average",
            "description": None,
            "is_active": True,
        })
    return padas


# Precomputed lookup structures ------------------------------------------------

_PADAS = build_padas()
_BY_INDEX = {p["index"]: p for p in _PADAS}
_BY_CODE = {p["code"]: p for p in _PADAS}


def pada_for_degree(degree: float) -> dict:
    """Map a compass bearing (degrees clockwise from North) to its pada dict.

    Accepts any real value; normalizes to [0, 360). N5 is centered on 0, so the
    boundary is offset by half a pada.
    """
    normalized = degree % 360.0
    idx = int(((normalized + PADA_SPAN / 2) % 360.0) // PADA_SPAN)  # 0..31
    return _BY_INDEX[idx + 1]


def get_pada_by_code(code: str) -> dict | None:
    return _BY_CODE.get(code)


def all_padas() -> list[dict]:
    return [dict(p) for p in _PADAS]

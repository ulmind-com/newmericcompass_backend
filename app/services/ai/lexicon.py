"""The words a reader uses, mapped to the words the app wrote down.

The assistant runs on the free tier, which means keyword search does most of
the work and has to be good at it. What stops a keyword search on this corpus
is almost never cleverness — it is vocabulary. A reader says "fridge", the
corpus says "Refrigerator". A reader says "stairs", it says "Staircase". A
reader says "rasoi" or "mandir", and the corpus has never heard of either.

So the gap is closed here, by hand, in the one place it can be read and added
to. Three kinds of entry:

- `ALIASES` — a word or phrase and the corpus words it should also search for.
  Written one way round (reader → corpus) because that is the direction the
  problem runs.
- `DIRECTIONS` — compass words and the sixteen-wind codes the corpus uses.
- `SUFFIXES` — the endings stripped so "colours", "colour" and "coloured" are
  one term.

Everything is lower case, and multi-word keys are matched as phrases.
"""

from __future__ import annotations

# --- Compass ---------------------------------------------------------------
# The corpus writes zones as codes: N, NNE, NE, ENE and so on. A reader writes
# them out, or uses the Sanskrit name, or both.

DIRECTIONS: dict[str, str] = {
    "north": "n",
    "south": "s",
    "east": "e",
    "west": "w",
    "north east": "ne", "northeast": "ne", "ne": "ne",
    "ishan": "ne", "ishanya": "ne", "eshan": "ne",
    "south east": "se", "southeast": "se", "se": "se",
    "agni": "se", "agneya": "se", "aagneya": "se",
    "south west": "sw", "southwest": "sw", "sw": "sw",
    "nairutya": "sw", "nairitya": "sw", "nairrutya": "sw",
    "north west": "nw", "northwest": "nw", "nw": "nw",
    "vayavya": "nw", "vayu": "nw", "vaayavya": "nw",
    "north north east": "nne", "nne": "nne",
    "east north east": "ene", "ene": "ene",
    "east south east": "ese", "ese": "ese",
    "south south east": "sse", "sse": "sse",
    "south south west": "ssw", "ssw": "ssw",
    "west south west": "wsw", "wsw": "wsw",
    "west north west": "wnw", "wnw": "wnw",
    "north north west": "nnw", "nnw": "nnw",
    "centre": "brahmasthan", "center": "brahmasthan", "middle": "brahmasthan",
    "brahmasthan": "brahmasthan", "brahmsthan": "brahmasthan",
}

# --- What things are called -------------------------------------------------
# Reader's word on the left, the corpus's words on the right. Transliterations
# are here too: the app is used in Bengali, Hindi and Assamese, and a question
# typed in Latin script arrives as "rasoi ghar", not "kitchen".

ALIASES: dict[str, tuple[str, ...]] = {
    # Rooms and fixtures
    "fridge": ("refrigerator", "freezer"),
    "freezer": ("refrigerator",),
    "stairs": ("staircase",),
    "stair": ("staircase",),
    "steps": ("staircase",),
    "loo": ("toilet",),
    "washroom": ("toilet", "bathroom"),
    "restroom": ("toilet", "bathroom"),
    "bath": ("bathroom",),
    "almirah": ("wardrobe",),
    "almari": ("wardrobe",),
    "cupboard": ("wardrobe",),
    "closet": ("wardrobe",),
    "safe": ("locker",),
    "vault": ("locker",),
    "cash": ("locker", "cash counter", "wealth"),
    "till": ("cash counter",),
    "counter": ("cash counter",),
    "temple": ("puja", "puja room", "pooja"),
    "mandir": ("puja", "puja room", "temple"),
    "pooja": ("puja",),
    "prayer": ("puja", "puja room"),
    "shrine": ("puja", "puja room"),
    "ac": ("air conditioner", "ac"),
    "air conditioner": ("ac",),
    "aircon": ("ac",),
    "geyser": ("heater",),
    "water heater": ("heater",),
    "tv": ("television",),
    "television": ("television", "music system"),
    "sofa": ("sofa", "living room"),
    "couch": ("sofa",),
    "settee": ("sofa",),
    "cot": ("bed",),
    "mattress": ("bed",),
    "sink": ("wash basin", "washing area"),
    "basin": ("wash basin", "washing area"),
    "tap": ("water",),
    "borewell": ("borewell", "water"),
    "bore well": ("borewell",),
    "tubewell": ("borewell",),
    "well": ("borewell", "water"),
    "tank": ("water tank", "overhead water tank", "septic tank"),
    "overhead tank": ("overhead water tank",),
    "sump": ("water tank",),
    "soak pit": ("septic tank",),
    "sewage": ("septic tank",),
    "septic": ("septic tank",),
    "dustbin": ("dustbin", "waste"),
    "bin": ("dustbin",),
    "garbage": ("dustbin", "waste"),
    "trash": ("dustbin", "waste"),
    "rubbish": ("dustbin", "waste"),
    "inverter": ("inverter", "electric meter"),
    "ups": ("inverter",),
    "generator": ("inverter",),
    "meter": ("electric meter",),
    "fusebox": ("electric meter",),
    "study": ("study room", "office room"),
    "desk": ("workstation", "office room"),
    "workstation": ("workstation", "office room"),
    "office": ("office room",),
    "cabin": ("office room",),
    "shop": ("commercial", "cash counter"),
    "store": ("store room",),
    "storeroom": ("store room",),
    "pantry": ("store room", "kitchen"),
    "godown": ("store room",),
    "warehouse": ("store room",),
    "garage": ("garage", "parking"),
    "parking": ("garage",),
    "balcony": ("balcony", "verandah"),
    "veranda": ("balcony", "verandah"),
    "terrace": ("balcony", "terrace"),
    "lift": ("lift", "engineering"),
    "elevator": ("lift",),
    "gym": ("gym", "exercise"),
    "exercise": ("gym",),
    "guest": ("guest room",),
    "kids": ("children", "childrens room", "kids room"),
    "kid": ("children", "childrens room"),
    "child": ("children", "childrens room"),
    "children": ("childrens room",),
    "nursery": ("childrens room",),
    "baby": ("children", "childrens room"),
    "parents": ("elders", "elders parents room"),
    "elders": ("elders parents room",),
    "elderly": ("elders", "elders parents room"),
    "grandparents": ("elders", "elders parents room"),
    "servant": ("staff", "staff servants"),
    "maid": ("staff", "staff servants"),
    "staff": ("staff servants",),
    "drawing": ("drawing room", "living room"),
    "hall": ("living room", "dining hall"),
    "lounge": ("living room",),
    "dining": ("dining hall",),
    "bar": ("bar",),
    "mirror": ("mirror", "dressing table"),
    "dressing": ("dressing table",),
    "vanity": ("dressing table",),
    "washing machine": ("washing area", "washing machine"),
    "laundry": ("washing area",),
    "instrument": ("musical instrument",),
    "piano": ("musical instrument",),
    "guitar": ("musical instrument",),
    "harmonium": ("musical instrument",),
    "window": ("window",),
    "door": ("main entrance", "entrance", "door"),
    "entrance": ("main entrance",),
    "gate": ("main entrance", "entrance"),
    "entry": ("main entrance", "entrance"),
    "swimming pool": ("swimming pool", "water"),
    "pool": ("swimming pool",),
    "pond": ("water",),
    "fountain": ("water",),

    # Rooms, in transliteration
    "rasoi": ("kitchen",),
    "rannaghar": ("kitchen",),
    "ranna ghar": ("kitchen",),
    "randhanghar": ("kitchen",),
    "shouchalay": ("toilet",),
    "sauchalay": ("toilet",),
    "bathrum": ("bathroom",),
    "shoyar ghar": ("bedroom",),
    "shoyonkokkho": ("bedroom",),
    "bedrum": ("bedroom",),
    "bari": ("house", "home"),
    "makan": ("house", "home"),
    "kamra": ("room",),
    "sirhi": ("staircase",),
    "sidhi": ("staircase",),
    "darwaza": ("main entrance", "door"),
    "dorja": ("main entrance", "door"),
    "khirki": ("window",),
    "janala": ("window",),

    # What people actually ask about
    "money": ("wealth", "financial", "income"),
    "income": ("wealth", "income"),
    "salary": ("income", "wealth"),
    "wealth": ("wealth", "prosperity"),
    "rich": ("wealth", "prosperity"),
    "prosperity": ("prosperity", "wealth"),
    "savings": ("wealth", "savings"),
    "loss": ("loss", "expenditure"),
    "expense": ("expenditure",),
    "expenses": ("expenditure",),
    "debt": ("loss", "financial"),
    "loan": ("financial", "loss"),
    "business": ("commercial", "business"),
    "job": ("career", "job"),
    "career": ("career", "job"),
    "promotion": ("career", "growth"),
    "work": ("career", "work"),
    "study": ("study room", "education", "concentration"),
    "exam": ("education", "concentration", "study room"),
    "education": ("education", "study room"),
    "marriage": ("marriage", "relationship"),
    "wedding": ("marriage",),
    "husband": ("marriage", "relationship"),
    "wife": ("marriage", "relationship"),
    "couple": ("marriage", "relationship"),
    "relationship": ("relationship", "relations"),
    "fight": ("discord", "conflict", "quarrel"),
    "fights": ("discord", "conflict", "quarrel"),
    "quarrel": ("discord", "conflict"),
    "argument": ("discord", "conflict"),
    "tension": ("stress", "anxiety"),
    "stress": ("stress", "anxiety"),
    "anxiety": ("anxiety", "stress"),
    "depression": ("depression", "mental"),
    "sleep": ("sleep", "rest", "bedroom"),
    "insomnia": ("sleep", "rest"),
    "health": ("health", "immunity"),
    "illness": ("health", "disease"),
    "disease": ("health", "disease", "immunity"),
    "sick": ("health", "disease"),
    "immunity": ("immunity", "health"),
    "child birth": ("children", "progeny"),
    "pregnancy": ("children", "progeny"),
    "baby boy": ("children", "progeny"),
    "progeny": ("children", "progeny"),
    "fame": ("fame", "recognition"),
    "respect": ("fame", "recognition"),
    "clarity": ("clarity", "mental"),
    "focus": ("concentration", "clarity"),
    "concentration": ("concentration",),
    "luck": ("fortune", "prosperity"),
    "fortune": ("fortune",),
    "growth": ("growth", "opportunity"),
    "opportunity": ("opportunity", "growth"),

    # The vocabulary of the remedies themselves
    "remedy": ("remedy", "remedial", "correction", "treatment"),
    "remedies": ("remedy", "remedial", "correction", "treatment"),
    "solution": ("remedy", "solution", "correction"),
    "fix": ("remedy", "correction", "treatment"),
    "cure": ("remedy", "treatment"),
    "upay": ("remedy", "treatment"),
    "pratikar": ("remedy", "treatment"),
    "totka": ("remedy",),
    "correct": ("correction", "remedy"),
    "defect": ("dosh", "defect", "flaw"),
    "dosh": ("dosh", "defect"),
    "dosha": ("dosh", "dosha"),
    "problem": ("problem", "defect", "dosh"),
    "colour": ("colour", "color"),
    "color": ("colour", "color"),
    "paint": ("colour", "paint"),
    "shade": ("colour",),
    "element": ("element", "panchabhuta"),
    "elements": ("element", "panchabhuta"),
    "panchabhuta": ("element", "panchabhuta"),
    "zone": ("zone", "direction"),
    "direction": ("direction", "zone"),
    "disha": ("direction", "zone"),
    "dishe": ("direction", "zone"),
    "dishay": ("direction", "zone"),
    "dike": ("direction", "zone"),
    "dikey": ("direction", "zone"),
    "dik": ("direction", "zone"),
    "pada": ("pada",),
    "vastu": ("vastu",),
    "vaastu": ("vastu",),
    "bastu": ("vastu",),
    "pitra": ("pitra", "ancestor", "ancestral"),
    "pitru": ("pitra", "ancestor"),
    "ancestor": ("pitra", "ancestor", "ancestral"),
    "ancestors": ("pitra", "ancestor", "ancestral"),
    "purvaj": ("pitra", "ancestor"),
    "tarpan": ("pitra", "tarpan", "ancestor"),
    "shradh": ("pitra", "shradh", "ancestor"),
    "pind daan": ("pitra", "ancestor"),
    "placement": ("placement", "position"),
    "place": ("placement", "position"),
    "keep": ("placement", "position"),
    "put": ("placement", "position"),
    "position": ("position", "placement"),
    "face": ("facing", "direction"),
    "facing": ("facing", "direction"),
}

# --- Endings ---------------------------------------------------------------
# Two passes, because plurals and the heavier endings need different rules.

#: Endings removed whole, longest first. Applied only to longer words: the
#: sixteen-wind codes are one to three letters and stripping anything off
#: "sse" or "ese" would destroy them.
SUFFIXES: tuple[str, ...] = (
    "ational", "iveness", "fulness", "ousness", "ization",
    "ements", "ement", "ations", "ation", "ingly", "ively",
    "ments", "ment", "ness", "ings", "ing", "ers", "ed",
)

#: Words whose ending only looks like a suffix. Stemming these makes them
#: something else, and two of them are the names of screens.
NEVER_STEM = {
    "brahmasthan", "vishwakarma", "prakash", "nexus", "dosh",
    "dosha", "pitra", "puja", "pooja", "agni", "vayu", "ishan", "address",
    "business", "illness", "stress", "access", "process", "success",
    "premises", "series", "species", "always", "analysis", "basis", "gas",
    "was", "his", "this", "yes", "plus", "focus", "bonus", "status",
}

#: A plural may be four letters ("beds"); the heavier endings need more room
#: before they are worth stripping.
MIN_PLURAL_LENGTH = 4
MIN_STEM_LENGTH = 5


def _singular(word: str) -> str:
    """Make a plural singular, following the shape of the ending.

    Removing "es" before trying "s" turned "zones" into "zon", which then met
    nothing: "zone" is four letters and is never stemmed. These four cases are
    the standard ones and they get "zones", "remedies" and "illnesses" all
    right.
    """
    if len(word) < MIN_PLURAL_LENGTH:
        return word
    if word.endswith("sses"):
        return word[:-2]
    if word.endswith("ies") and len(word) > 4:
        return f"{word[:-3]}y"
    if word.endswith("ss"):
        return word
    if word.endswith("s") and not word.endswith("us"):
        return word[:-1]
    return word


def stem(word: str) -> str:
    """Reduce one ending, when it is safe to.

    Deliberately crude. A real stemmer would conflate more, and on a corpus
    this size and this specific the cost of over-stemming — "bed", "bedding"
    and "bedroom" running together — is worse than the odd missed match.
    """
    if word in NEVER_STEM:
        return word

    word = _singular(word)
    if word in NEVER_STEM or len(word) < MIN_STEM_LENGTH:
        return word

    if word.endswith("ied") and len(word) > 4:
        return f"{word[:-3]}y"
    for suffix in SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


#: The longest phrase, in words, that any key here spans.
MAX_PHRASE = max(
    len(k.split()) for k in list(ALIASES) + list(DIRECTIONS)
)

"""Finding the passages that can answer a question.

Two searches, because neither is enough on its own.

Vastu vocabulary is full of short exact tokens — NNE, SE, Ishan, Brahmasthan,
pada P17 — and a dense vector treats those as near-synonyms of each other; ask
about the north-east and you get the south-west. A keyword search keeps them
apart. But a keyword search cannot connect "where should I keep my fridge" to a
passage that only ever says "refrigerator", and a vector can.

So both run, and their rankings are merged. A passage both searches like rises
above one that only one of them liked, which is exactly the passage worth
showing.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

import numpy as np

from app.services.ai import lexicon
from app.services.ai.corpus import Passage
from app.services.ai.lexicon import stem

#: Words that match everything and therefore distinguish nothing.
#:
#: The Hinglish and Bengali function words are here for a reason. Questions
#: arrive as "rasoi ghar kon dishe hobe", and the Pitra Kripa chapters are
#: written in the same romanised register — so "ghar", "kon" and "ki" matched
#: those chapters strongly and buried the kitchen passage the question was
#: actually about.
STOP = {
    # English
    "a", "an", "and", "any", "are", "as", "at", "be", "been", "but", "by",
    "can", "did", "do", "does", "for", "from", "get", "give", "go", "goes",
    "had", "has", "have", "he", "her", "him", "his", "how", "i", "if", "in",
    "into", "is", "it", "its", "just", "know", "me", "much", "must", "my",
    "need", "of", "on", "one", "or", "our", "out", "please", "say", "she",
    "should", "so", "some", "suit", "suits", "tell", "than", "that", "the",
    "their", "them", "then", "there", "these", "they", "this", "to", "too",
    "us", "very", "want", "was", "we", "were", "what", "when", "where",
    "which", "while", "who", "why", "will", "with", "would", "you", "your",
    # Romanised Hindi / Bengali function words
    # "e" is missing on purpose: it is the East zone's code.
    "aar", "ache", "achhe", "ar", "aur", "bhai", "chahiye", "ei", "eita",
    "er", "eta", "ghar", "hai",
    "hain", "hobe", "hoy", "hota", "hoti", "honi", "hona", "jodi", "ka",
    "kahan", "kaise", "ke", "keno", "ki", "kina", "ko", "kon", "kona",
    "konta", "kothay", "koto", "kya", "me", "mein", "na", "nahi", "par",
    "ta", "tha", "the", "to", "uchit", "ye", "yeh",
    # Verbs and vague nouns that carry no subject. Left in, a short question
    # like "tarpan ka mahatva" scored half its words unknown and was refused
    # for a word that was never the point.
    "bhalo", "bolo", "bujhte", "chai", "dorkar", "ghore", "janai", "jane",
    "jante", "jonno", "jonne", "kharap", "kore", "korte", "kori", "lagbe",
    "mahatva", "moto", "niye", "rakha", "rakhbo", "rakhe", "rakhna", "rakhte",
    "thake", "bare", "bishoy", "somporke", "kotha", "katha", "oi", "ota",
    "tai", "tao", "eto", "ebong", "kintu", "thakbe", "thakbo", "korbo",
    "korbe", "dao", "dibo", "debo", "pabo", "bolo", "bol", "koro",
}

_NATIVE_CHARS = re.compile(r"[\u0900-\u097F\u0980-\u09FF]")

#: Latin letters and digits, or a run of Devanagari, Bengali or Assamese.
#: The old pattern was [a-z0-9]+, which silently discarded every character of a
#: question typed in the app's own scripts — the whole question came out empty
#: and was refused for having no words the app knew.
_TOKEN = re.compile(r"[a-z0-9]+|[\u0900-\u097F\u0980-\u09FF]+")


def _words(text: str) -> list[str]:
    """Words, with single-character Indic fragments dropped.

    An apostrophe inside an Assamese verb — "হ'ব" — splits it into two
    one-letter pieces. They mean nothing on their own, and counted as words the
    app does not know they were enough to fail the coverage test on a short
    question.
    """
    return [
        w for w in _TOKEN.findall(text.lower())
        if not (len(w) == 1 and _NATIVE_CHARS.match(w))
    ]


def tokenize(text: str) -> list[str]:
    """Turn text into the terms the index is built and searched on.

    Four things happen, and the order matters:

    1. Phrases first. "north east", "washing machine" and "air conditioner"
       each mean one thing, and matching them word by word loses that — so the
       longest phrase in the lexicon is tried at each position before single
       words are.
    2. Compass words become the codes the corpus uses, because the corpus
       writes zones as NE and SSW and a reader writes them out.
    3. A reader's word brings the corpus's words with it: "fridge" also
       searches "refrigerator". Both are kept, so the reader's own word still
       matches where the corpus happens to use it too.
    4. Everything is stemmed, so "colours", "colour" and "coloured" are one
       term. Direction codes are too short to be stemmed and are left alone.

    Applied to both sides — the passages at index time and the question at
    search time — so the two always meet in the same vocabulary.
    """
    words = _words(text)
    out: list[str] = []
    i = 0
    while i < len(words):
        matched = False
        # Longest phrase first, so "north north east" beats "north east".
        for span in range(min(lexicon.MAX_PHRASE, len(words) - i), 0, -1):
            phrase = " ".join(words[i:i + span])
            joined = "".join(words[i:i + span])

            code = lexicon.DIRECTIONS.get(phrase) or (
                lexicon.DIRECTIONS.get(joined) if span > 1 else None
            )
            if code:
                # The code alone, deliberately. Emitting "southwest" as well
                # meant a heading reading "SOUTH-WEST — SW" matched a direction
                # twice while one reading "SW" matched it once, so every zone
                # heading outranked the colour chart on questions about colour.
                out.append(code)
                i += span
                matched = True
                break

            if native := lexicon.native_lookup(phrase):
                out.extend(stem(a) for a in _expand(native))
                i += span
                matched = True
                break

            if aliases := lexicon.ALIASES.get(phrase):
                out.extend(stem(a) for a in _expand(aliases))
                if span == 1:
                    out.append(stem(phrase))
                i += span
                matched = True
                break

        if matched:
            continue

        w = words[i]
        # A native word with no entry carries nothing the English corpus can
        # match, so it is dropped rather than added as a term nothing contains.
        if w not in STOP and not lexicon.is_native_stop(w) and not _is_native(w):
            out.append(stem(w))
        i += 1

    return out


def _is_native(word: str) -> bool:
    return bool(_NATIVE_CHARS.search(word))


def understood(text: str, vocab: set[str]) -> tuple[float, list[str]]:
    """What share of a question's words the app can make sense of.

    A word counts as understood if the corpus uses it, or if the lexicon knows
    what it means. That second half matters: "sirhi kahan honi chahiye" was
    refused because "sirhi" is not a word the corpus contains — even though the
    lexicon maps it to staircase and the search found the right passage.
    Understanding a word is not the same as having seen it.
    """
    words = _words(text)
    content = [w for w in words if w not in STOP and not lexicon.is_native_stop(w)]
    if not content:
        return 0.0, []

    known: list[bool] = []
    unknown: list[str] = []
    i = 0
    while i < len(content):
        hit = False
        for span in range(min(lexicon.MAX_PHRASE, len(content) - i), 0, -1):
            phrase = " ".join(content[i:i + span])
            joined = "".join(content[i:i + span])
            if (
                phrase in lexicon.DIRECTIONS
                or joined in lexicon.DIRECTIONS
                or phrase in lexicon.ALIASES
                or lexicon.native_lookup(phrase) is not None
            ):
                known.extend([True] * span)
                i += span
                hit = True
                break
        if hit:
            continue
        word = content[i]
        seen = stem(word) in vocab
        known.append(seen)
        if not seen:
            unknown.append(word)
        i += 1

    return sum(known) / len(known), unknown


def _expand(aliases: tuple[str, ...]) -> list[str]:
    """An alias may itself be a phrase; index its words, not the phrase."""
    out: list[str] = []
    for alias in aliases:
        parts = _words(alias)
        out.extend(p for p in parts if p not in STOP)
    return out


@dataclass(slots=True)
class Hit:
    passage: Passage
    score: float


@dataclass(slots=True)
class Relevance:
    """What the gate in front of the model gets to look at."""

    #: Share of the question's words that the corpus uses at all, 0 to 1.
    coverage: float
    #: Best BM25 score against any one passage.
    lexical: float
    #: Best BM25 score against any one passage's heading trail.
    #:
    #: A question about something the app covers names it, and the app names it
    #: in a heading. A question built from ordinary words the corpus happens to
    #: contain — "how to lose weight fast" — matches only in bodies.
    heading: float
    #: Best cosine similarity against any one passage; 0 without a vector.
    dense: float
    #: The question's words the corpus has never heard of.
    unknown: list[str]


def _idf(docs: list[list[str]]) -> dict[str, float]:
    """How much each term narrows things down, over the whole corpus.

    Computed once across heading and body together, and shared by both fields.
    Per-field idf was wrong in a way that took a while to see: "placement" is
    everywhere in the bodies but in only a few headings, so the heading field
    scored it as rare and one passage titled "Step-by-Step Placement Protocol"
    won every question containing the word "placement". A term's importance is
    a property of the corpus, not of the field it was found in.
    """
    df: Counter[str] = Counter()
    for d in docs:
        df.update(set(d))
    n = len(docs) or 1
    # Floored: a term in almost every passage must not be able to push a score
    # negative and bury a passage that genuinely matches.
    return {
        term: max(0.05, math.log(1 + (n - freq + 0.5) / (freq + 0.5)))
        for term, freq in df.items()
    }


class _Field:
    """One searchable field of the corpus, with its own length statistics.

    Its own lengths, because a heading is a handful of words and a body can be
    hundreds, and BM25 divides by length. A shared idf, for the reason above.
    """

    def __init__(self, docs: list[list[str]], idf: dict[str, float]):
        self.tf: list[Counter[str]] = [Counter(d) for d in docs]
        self.lengths = np.array([len(d) or 1 for d in docs], dtype=np.float32)
        self.avg_len = float(self.lengths.mean()) if len(self.lengths) else 1.0
        self.idf = idf

    def score(self, terms: list[str], k1: float = 1.5, b: float = 0.75) -> np.ndarray:
        scores = np.zeros(len(self.tf), dtype=np.float32)
        for term in set(terms):
            idf = self.idf.get(term)
            if idf is None:
                continue
            for i, tf in enumerate(self.tf):
                f = tf.get(term)
                if not f:
                    continue
                norm = f * (k1 + 1) / (f + k1 * (1 - b + b * self.lengths[i] / self.avg_len))
                scores[i] += idf * norm
        return scores


class Index:
    """The corpus, ready to search. Built once and held in memory.

    581-odd passages is small enough that both searches are a matrix multiply
    and a dictionary walk, so there is no vector database here and none needed.
    """

    def __init__(self, passages: list[Passage]):
        self.passages = passages
        self._build_lexical()
        self._build_dense()

    # --- keyword half (BM25) ---------------------------------------------

    #: How much a heading match counts against a body match.
    #:
    #: The heading trail is what says what a passage is *about*: "16 Zone
    #: Analysis — Kitchen — 7. SE". The body is what it says. Asked "kitchen in
    #: the south east", a Toilet passage that mentions kitchen in passing beats
    #: the Kitchen passage on body text alone — it is longer and says more — so
    #: the field that names the subject has to outweigh the one that discusses
    #: it.
    #:
    #: Two fields scored separately rather than one bag with the heading
    #: repeated: BM25 divides by document length, and padding a document with
    #: three copies of its own title distorts that for every other term in it.
    HEADING_WEIGHT = 2.5

    def _build_lexical(self) -> None:
        heads = [tokenize(p.heading) for p in self.passages]
        bodies = [tokenize(p.text) for p in self.passages]
        self.idf = _idf([h + b for h, b in zip(heads, bodies, strict=True)])
        self.head = _Field(heads, self.idf)
        self.body = _Field(bodies, self.idf)
        # The whole passage, for the relevance gate.
        self.tf = [h + b for h, b in zip(self.head.tf, self.body.tf, strict=True)]

    def _bm25(self, terms: list[str]) -> np.ndarray:
        """Both fields, the heading weighted above the body."""
        return self.body.score(terms) + self.HEADING_WEIGHT * self.head.score(terms)

    def _overlap(self, terms: list[str]) -> np.ndarray:
        """The share of the question's distinct terms present in each passage."""
        wanted = set(terms)
        if not wanted:
            return np.zeros(len(self.passages), dtype=np.float32)
        return np.array(
            [len(wanted & set(tf)) / len(wanted) for tf in self.tf],
            dtype=np.float32,
        )

    # --- vector half ------------------------------------------------------

    def _build_dense(self) -> None:
        vectors = [p.vector for p in self.passages if p.vector]
        self.has_vectors = len(vectors) == len(self.passages) and bool(vectors)
        # A half-built index, or one left over from a different embedding model,
        # would stack ragged rows and raise deep inside numpy. Searching by
        # keyword alone is the honest fallback.
        if self.has_vectors and len({len(v) for v in vectors}) != 1:
            self.has_vectors = False
        if not self.has_vectors:
            self.matrix = None
            return
        m = np.asarray(vectors, dtype=np.float32)
        norms = np.linalg.norm(m, axis=1, keepdims=True)
        self.matrix = m / np.clip(norms, 1e-9, None)

    def _cosine(self, query: list[float]) -> np.ndarray:
        if self.matrix is None:
            return np.zeros(len(self.passages), dtype=np.float32)
        q = np.asarray(query, dtype=np.float32)
        q /= max(float(np.linalg.norm(q)), 1e-9)
        return self.matrix @ q

    # --- the two, merged --------------------------------------------------

    def search(self, question: str, query_vector: list[float] | None, k: int = 8) -> list[Hit]:
        """Rank by both searches at once.

        The two scores are on different scales — BM25 is unbounded, cosine sits
        in [-1, 1] — so they are combined by rank rather than by value. A
        passage's score is the sum of 1/(60 + rank) from each search: the
        standard reciprocal-rank fusion, which needs no tuning per query and
        cannot be dominated by one search producing large numbers.
        """
        terms = tokenize(question)
        lexical = self._bm25(terms)
        dense = self._cosine(query_vector) if query_vector else np.zeros_like(lexical)

        fused = np.zeros(len(self.passages), dtype=np.float32)
        for scores, weight in ((lexical, 1.0), (dense, 1.0 if query_vector else 0.0)):
            if not weight:
                continue
            order = np.argsort(-scores)
            for rank, idx in enumerate(order):
                if scores[idx] <= 0:
                    break
                fused[idx] += weight / (60 + rank)

        top = np.argsort(-fused)[:k]
        return [Hit(self.passages[i], float(fused[i])) for i in top if fused[i] > 0]

    def relevance(self, question: str, query_vector: list[float] | None) -> "Relevance":
        """How much this question looks like something the app can answer.

        Fused ranks say which passage is best but never whether any of them is
        any good — the top of a list of bad matches still ranks first. These
        three numbers are what the gate reads instead.

        Coverage does most of the work, and it is the one signal that survives
        an embedding outage. A question about Vastu is written almost entirely
        in words the corpus itself uses; a question about cricket is not, and
        the words it does not share are exactly the ones carrying its meaning.
        """
        terms = tokenize(question)
        coverage, unknown = understood(question, set(self.idf))
        lexical = self._bm25(terms)
        heading = self.head.score(terms)
        dense = self._cosine(query_vector) if query_vector else np.zeros_like(lexical)
        return Relevance(
            coverage=coverage,
            lexical=float(lexical.max()) if len(lexical) else 0.0,
            heading=float(heading.max()) if len(heading) else 0.0,
            dense=float(dense.max()) if len(dense) else 0.0,
            unknown=unknown,
        )

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

from app.services.ai.corpus import Passage

#: Words that match everything and therefore distinguish nothing.
STOP = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "can", "do", "does",
    "for", "from", "has", "have", "how", "i", "if", "in", "is", "it", "its", "my",
    "of", "on", "or", "should", "that", "the", "their", "then", "there", "these",
    "this", "to", "was", "what", "when", "where", "which", "will", "with", "you",
    "your",
}

#: The compass words a question is likely to use, and the code the corpus uses.
#: Without this, "north east" never finds a passage that only says "NE".
DIRECTION_WORDS: dict[str, str] = {
    "north": "N", "south": "S", "east": "E", "west": "W",
    "northeast": "NE", "north-east": "NE", "ishan": "NE", "ishanya": "NE",
    "southeast": "SE", "south-east": "SE", "agni": "SE", "agneya": "SE",
    "southwest": "SW", "south-west": "SW", "nairutya": "SW", "nairitya": "SW",
    "northwest": "NW", "north-west": "NW", "vayavya": "NW", "vayu": "NW",
    "centre": "BRAHMASTHAN", "center": "BRAHMASTHAN", "brahmasthan": "BRAHMASTHAN",
}

_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """Lower-case words, stop words dropped, compass words expanded.

    "North-East" arrives as two tokens once split, so the compound forms are
    rejoined before lookup; otherwise "north east kitchen" would never reach NE.
    """
    words = _TOKEN.findall(text.lower())
    out: list[str] = []
    i = 0
    while i < len(words):
        pair = f"{words[i]}{words[i + 1]}" if i + 1 < len(words) else ""
        if pair in DIRECTION_WORDS:
            out.append(DIRECTION_WORDS[pair].lower())
            out.append(pair)
            i += 2
            continue
        w = words[i]
        if w in DIRECTION_WORDS:
            out.append(DIRECTION_WORDS[w].lower())
        if w not in STOP:
            out.append(w)
        i += 1
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
    #: Best cosine similarity against any one passage; 0 without a vector.
    dense: float
    #: The question's words the corpus has never heard of.
    unknown: list[str]


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

    def _build_lexical(self) -> None:
        self.docs = [tokenize(p.for_embedding()) for p in self.passages]
        self.lengths = np.array([len(d) or 1 for d in self.docs], dtype=np.float32)
        self.avg_len = float(self.lengths.mean()) if len(self.lengths) else 1.0
        self.tf: list[Counter[str]] = [Counter(d) for d in self.docs]

        df: Counter[str] = Counter()
        for d in self.docs:
            df.update(set(d))
        n = len(self.docs) or 1
        # BM25's idf, floored: a term in almost every passage must not be able
        # to push a score negative and bury a passage that genuinely matches.
        self.idf = {
            term: max(0.05, math.log(1 + (n - freq + 0.5) / (freq + 0.5)))
            for term, freq in df.items()
        }

    def _bm25(self, terms: list[str], k1: float = 1.5, b: float = 0.75) -> np.ndarray:
        scores = np.zeros(len(self.passages), dtype=np.float32)
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

    # --- vector half ------------------------------------------------------

    def _build_dense(self) -> None:
        vectors = [p.vector for p in self.passages if p.vector]
        self.has_vectors = len(vectors) == len(self.passages) and bool(vectors)
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
        known = [t for t in terms if t in self.idf]
        lexical = self._bm25(terms)
        dense = self._cosine(query_vector) if query_vector else np.zeros_like(lexical)
        return Relevance(
            coverage=len(known) / len(terms) if terms else 0.0,
            lexical=float(lexical.max()) if len(lexical) else 0.0,
            dense=float(dense.max()) if len(dense) else 0.0,
            unknown=[t for t in terms if t not in self.idf],
        )

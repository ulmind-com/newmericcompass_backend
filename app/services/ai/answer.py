"""Answering from the retrieved passages, and refusing when there are none.

Three things keep an answer honest, and all three are needed:

1. The model is given the passages and told, in the system prompt, that they are
   the only thing it may use.
2. It is asked to cite a passage number for every claim, which makes an
   invented claim conspicuous rather than fluent.
3. Its citations are checked against what was actually sent. A number it made
   up is dropped, and an answer left with no valid citation is not returned.

The gate in front of all of this matters most: when retrieval finds nothing that
looks like an answer, the model is never called. It cannot be tempted into
answering a question about the weather from a Vastu corpus if it is never asked.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

import httpx

from app.core.config import settings
from app.services.ai.retrieve import Hit, Relevance

logger = logging.getLogger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

LANG_NAMES = {
    "en": "English",
    "bn": "Bengali (Bangla script)",
    "hi": "Hindi (Devanagari script)",
    "as": "Assamese (Assamese script)",
}

# The gate in front of the model, set from measured behaviour rather than taste.
#
# Coverage is the primary signal and it separates cleanly: measured over the
# shipped corpus, real Vastu questions score 0.80 to 1.00 because they are
# written in the app's own vocabulary, while questions about cricket, cooking or
# the weather score 0.00 to 0.67 — the words they do not share are precisely the
# ones carrying their meaning.
MIN_COVERAGE = 0.75
#: A handful of off-topic questions are built entirely from ordinary words the
#: corpus also uses ("recommend a good movie"). Coverage cannot see those;
#: similarity can, so a question must also clear one of the two below.
MIN_DENSE = 0.50
MIN_LEXICAL = 6.0

SYSTEM = """You are the Newmeric Compass assistant. You answer questions about \
Vastu using ONLY the numbered passages given to you. Those passages are the \
app's own content, written by Acharya Pannkaj Kabiraj.

Rules you must follow:

1. Use ONLY the passages. Never use anything you know from outside them. If the \
passages do not contain the answer, say so plainly and stop.
2. Cite as you go. After each sentence or bullet that makes a claim, put the \
passage number(s) it came from in square brackets, like [3] or [1][4].
3. Never invent a passage number. Only cite numbers that appear below.
4. Do not soften or embellish. If a passage says a placement is to be avoided, \
say it is to be avoided.
5. Be specific and complete. Give the reasoning and the remedy when the \
passages carry them — a short answer that leaves out the remedy is a bad answer.
6. Do not give medical, legal, financial or structural-engineering advice, and \
do not predict the future. Stay with what the passages say.
7. Write in {language}. Keep Vastu terms and direction codes (NE, SSW, \
Brahmasthan, pada names) as they are — do not translate or transliterate them.
8. Format for a phone screen: short paragraphs, bullets where there is a list, \
no tables, no headings larger than bold text.

If the passages are not about what was asked, reply with exactly: \
INSUFFICIENT_CONTEXT"""

REFUSAL = {
    "en": "I can only answer from what is written in this app, and I could not find anything here about that. Try asking about a placement, a direction, a zone, a colour or a remedy — for example, “where should the kitchen go?”",
    "bn": "আমি শুধু এই অ্যাপে যা লেখা আছে তার থেকেই উত্তর দিতে পারি, আর এই বিষয়ে এখানে কিছু পেলাম না। কোনো স্থান, দিক, জোন, রং বা প্রতিকার নিয়ে জিজ্ঞেস করে দেখুন — যেমন, “রান্নাঘর কোন দিকে হওয়া উচিত?”",
    "hi": "मैं केवल इस ऐप में लिखी बातों से ही उत्तर दे सकता हूँ, और इस विषय पर मुझे यहाँ कुछ नहीं मिला। किसी स्थान, दिशा, ज़ोन, रंग या उपाय के बारे में पूछकर देखें — जैसे, “रसोई किस दिशा में होनी चाहिए?”",
    "as": "মই কেৱল এই এপত লিখা কথাৰ পৰাহে উত্তৰ দিব পাৰোঁ, আৰু এই বিষয়ে ইয়াত একো পোৱা নগ'ল। কোনো স্থান, দিশ, জ'ন, ৰং বা প্ৰতিকাৰৰ বিষয়ে সুধি চাওক — যেনে, “ৰন্ধনঘৰ কোন দিশত হ'ব লাগে?”",
}


@dataclass(slots=True)
class Source:
    """One passage an answer leaned on, as the app will show it."""

    n: int
    screen: str
    route: str
    heading: str
    excerpt: str


@dataclass(slots=True)
class Answer:
    text: str
    sources: list[Source]
    answered: bool


def is_configured() -> bool:
    return bool(settings.GROQ_API_KEY)


def should_answer(rel: Relevance) -> bool:
    """Whether this question is close enough to the app to be worth answering.

    Both tests must pass. Coverage asks whether the question is even phrased in
    the app's subject; similarity asks whether anything in it actually matches.
    A question that fails either is refused without the model ever seeing it,
    which is the only refusal that cannot be talked around.

    Similarity falls back to the keyword score when no vector is available, so
    an embedding outage narrows the assistant rather than opening it up.
    """
    if rel.coverage < MIN_COVERAGE:
        return False
    return rel.dense >= MIN_DENSE or rel.lexical >= MIN_LEXICAL


def refusal(lang: str) -> Answer:
    return Answer(text=REFUSAL.get(lang, REFUSAL["en"]), sources=[], answered=False)


def _context(hits: list[Hit]) -> str:
    return "\n\n".join(
        f"[{i}] {h.passage.heading}\n{h.passage.text}"
        for i, h in enumerate(hits, start=1)
    )


_CITE = re.compile(r"\[(\d+)\]")


async def _ask_groq(question: str, hits: list[Hit], lang: str, screen: str | None) -> str:
    where = (
        f"\n\nThe person is currently reading the \"{screen}\" screen, so prefer "
        f"passages from there when they answer the question equally well."
        if screen else ""
    )
    body = {
        "model": settings.GROQ_MODEL,
        "temperature": 0.2,
        "max_tokens": 1200,
        "messages": [
            {"role": "system", "content": SYSTEM.format(language=LANG_NAMES.get(lang, "English"))},
            {
                "role": "user",
                "content": f"Passages:\n\n{_context(hits)}{where}\n\nQuestion: {question}",
            },
        ],
    }
    headers = {"Authorization": f"Bearer {settings.GROQ_API_KEY}"}
    async with httpx.AsyncClient() as client:
        r = await client.post(GROQ_URL, json=body, headers=headers, timeout=90)
        if r.status_code >= 400:
            logger.error("Groq refused: %s %s", r.status_code, r.text[:300])
            r.raise_for_status()
        data = r.json()
    return (data["choices"][0]["message"]["content"] or "").strip()


async def answer(question: str, hits: list[Hit], lang: str, screen: str | None = None) -> Answer:
    """Answer from these passages, or refuse."""
    if not hits:
        return refusal(lang)

    text = await _ask_groq(question, hits, lang, screen)

    if not text or "INSUFFICIENT_CONTEXT" in text:
        return refusal(lang)

    # Every number the answer cited, kept only if it was really sent.
    cited = {int(n) for n in _CITE.findall(text)}
    valid = {n for n in cited if 1 <= n <= len(hits)}
    for bad in cited - valid:
        text = text.replace(f"[{bad}]", "")
        logger.warning("Dropped invented citation [%s]", bad)

    # An answer that cites nothing is an answer that was not read off the
    # passages, whatever it says. Refuse rather than pass it on.
    if not valid:
        logger.warning("Answer carried no usable citation; refusing. Question: %r", question[:120])
        return refusal(lang)

    sources = [
        Source(
            n=n,
            screen=hits[n - 1].passage.screen,
            route=hits[n - 1].passage.route,
            heading=hits[n - 1].passage.heading,
            excerpt=hits[n - 1].passage.text[:300].strip(),
        )
        for n in sorted(valid)
    ]
    return Answer(text=text.strip(), sources=sources, answered=True)

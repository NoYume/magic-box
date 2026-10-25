"""Fuzzy incantation matching against one player's set only (spec section 9, voice/).

Owner: Nikhil
"""

import re
from collections.abc import Mapping

from rapidfuzz import fuzz

_PUNCTUATION = re.compile(r"[^\w\s]|_")


def normalize(text: str) -> str:
    """Lowercases, drops punctuation (keeping Unicode letters and digits), collapses whitespace."""
    return " ".join(_PUNCTUATION.sub("", text.lower()).split())


def _score(transcript_words: list[str], incantation: str) -> float:
    """Best fuzz.ratio of the incantation against word windows sized n-1, n and n+1."""
    n = len(incantation.split())
    sizes = [size for size in (n - 1, n, n + 1) if size >= 1]
    if len(transcript_words) < min(sizes):
        return float(fuzz.ratio(" ".join(transcript_words), incantation))
    best = 0.0
    for size in sizes:
        for start in range(len(transcript_words) - size + 1):
            window = " ".join(transcript_words[start : start + size])
            best = max(best, float(fuzz.ratio(window, incantation)))
    return best


def match_incantation(
    text: str, incantations: Mapping[str, str], threshold: float
) -> tuple[str, float] | None:
    """Returns (spell_id, score 0-100) for the best match at or above threshold, else None."""
    transcript_words = normalize(text).split()
    if not transcript_words:
        return None
    best_id: str | None = None
    best_score = -1.0
    for spell_id, incantation in incantations.items():
        normalized = normalize(incantation)
        if not normalized:
            continue
        score = _score(transcript_words, normalized)
        if score > best_score:
            best_id, best_score = spell_id, score
    if best_id is None or best_score < threshold:
        return None
    return best_id, best_score


def keywords_for(incantations: Mapping[str, str], min_chars: int) -> list[str]:
    """Distinct normalized words of all incantations, first-seen order, at least min_chars long."""
    seen: dict[str, None] = {}
    for incantation in incantations.values():
        for word in normalize(incantation).split():
            if len(word) >= min_chars:
                seen.setdefault(word, None)
    return list(seen)

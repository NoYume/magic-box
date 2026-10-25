"""Fuzzy incantation matching against one player's set only (spec section 8, voice/).

Owner: Nikhil
"""

from collections.abc import Mapping

from rapidfuzz.fuzz import ratio


def match_incantation(
    text: str, incantations: Mapping[str, str], threshold: float
) -> tuple[str, float] | None:
    """Return the best normalized fuzzy match at or above ``threshold``."""
    normalized = " ".join(text.lower().split())
    if not normalized or not incantations:
        return None
    scored = [
        (spell_id, float(ratio(normalized, " ".join(phrase.lower().split()))))
        for spell_id, phrase in incantations.items()
    ]
    best = max(scored, key=lambda item: item[1])
    return best if best[1] >= threshold else None

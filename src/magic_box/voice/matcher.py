"""Fuzzy incantation matching against one player's set only (spec section 8, voice/).

Owner: Nikhil
"""

from collections.abc import Mapping


def match_incantation(
    text: str, incantations: Mapping[str, str], threshold: float
) -> tuple[str, float] | None:
    """Returns (spell_id, score 0-100) for the best match at or above threshold, else None."""
    raise NotImplementedError("TODO(Nikhil): rapidfuzz incantation match")

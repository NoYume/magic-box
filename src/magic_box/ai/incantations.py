"""Incantation generation with config fallback (spec section 8, ai/).

Owner: Nikhil
"""

import json
from collections.abc import Mapping

from rapidfuzz.fuzz import ratio

from magic_box.ai.spark_client import SparkClient
from magic_box.core.config import Config


def fallback_incantations(classes: Mapping[int, str], cfg: Config) -> dict[int, dict[str, str]]:
    """Return the per-slot fixed incantations from config."""
    return {
        slot: {
            row["id"]: str(row["fallback"][slot])
            for row in cfg["game"]["classes"][class_id]["spells"]
        }
        for slot, class_id in classes.items()
    }


def _valid(result: dict[int, dict[str, str]], classes: Mapping[int, str], cfg: Config) -> bool:
    ai = cfg["ai"]
    minimum = int(ai["incantation_min_words"])
    maximum = int(ai["incantation_max_words"])
    expected = fallback_incantations(classes, cfg)
    if set(result) != set(expected):
        return False
    phrases: list[tuple[int, str]] = []
    for slot, spells in expected.items():
        if set(result[slot]) != set(spells):
            return False
        for text in result[slot].values():
            if not isinstance(text, str) or not minimum <= len(text.split()) <= maximum:
                return False
            phrases.append((slot, text.lower()))
    limit = float(ai["incantation_max_similarity"])
    return all(
        slot_a == slot_b or ratio(text_a, text_b) <= limit
        for index, (slot_a, text_a) in enumerate(phrases)
        for slot_b, text_b in phrases[index + 1 :]
    )


def generate_incantations(
    client: SparkClient, classes: Mapping[int, str], cfg: Config
) -> dict[int, dict[str, str]]:
    """Generate and validate incantations, returning config fallback on any failure."""
    fallback = fallback_incantations(classes, cfg)
    schema = {str(slot): list(spells) for slot, spells in fallback.items()}
    prompt = (
        "Write distinct Austin/HackTX-themed magic incantations of 3–7 words. "
        f"Return only JSON shaped as slot -> spell id -> phrase for: {json.dumps(schema)}"
    )
    try:
        raw = client.complete(
            "You write concise spoken incantations for a two-player duel.", prompt
        )
        start, end = raw.find("{"), raw.rfind("}")
        parsed = json.loads(raw[start : end + 1])
        result = {
            int(slot): {str(spell): str(text).strip() for spell, text in spells.items()}
            for slot, spells in parsed.items()
        }
        return result if _valid(result, classes, cfg) else fallback
    except (KeyError, TypeError, ValueError, RuntimeError, json.JSONDecodeError):
        return fallback

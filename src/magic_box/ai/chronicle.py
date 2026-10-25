"""Duel chronicle from the GameEvent log, with template fallback (spec section 8, ai/).

Owner: Nikhil
"""

import json
from collections import Counter
from collections.abc import Mapping, Sequence

from magic_box.core.contracts import GameEvent


def template_chronicle(events: Sequence[GameEvent], names: Mapping[int, str]) -> str:
    """Build a deterministic offline summary from the append-only event log."""
    counts = Counter(event.kind for event in events)
    ending = next((event for event in reversed(events) if event.kind == "match_end"), None)
    winner = ending.slot if ending is not None else None
    if winner is None:
        result = f"{names.get(0, 'P1')} and {names.get(1, 'P2')} ended their duel evenly."
    else:
        result = f"{names.get(winner, f'P{winner + 1}')} prevailed in the duel."
    return (
        f"{result} The arena recorded {counts['cast']} casts, {counts['hit']} hits, "
        f"{counts['dodge']} dodges, and {counts['block']} blocks."
    )


def write_chronicle(client, events: Sequence[GameEvent], names: Mapping[int, str]) -> str:
    """Ask Spark for a short chronicle, falling back when the call fails."""
    fallback = template_chronicle(events, names)
    payload = [
        {"t": event.t, "kind": event.kind, "slot": event.slot, "data": event.data}
        for event in events
    ]
    try:
        text = client.complete(
            "Write a warm, concise two-sentence Duel Chronicle. Do not invent events.",
            f"Players: {dict(names)}\nEvents: {json.dumps(payload)}",
        ).strip()
        return text or fallback
    except (RuntimeError, TypeError, ValueError):
        return fallback

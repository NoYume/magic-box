"""Duel chronicle from the GameEvent log, with template fallback (spec section 8, ai/).

Owner: Nikhil
"""

from collections.abc import Mapping, Sequence

from magic_box.core.contracts import GameEvent


def write_chronicle(client, events: Sequence[GameEvent], names: Mapping[int, str]) -> str:
    raise NotImplementedError("TODO(Nikhil): Spark-written chronicle")


def template_chronicle(events: Sequence[GameEvent], names: Mapping[int, str]) -> str:
    raise NotImplementedError("TODO(Nikhil): template chronicle")

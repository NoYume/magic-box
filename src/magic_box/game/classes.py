"""Class table access and the lobby's spoken class pick (spec section 8, game/).

Owner: Adetola

Each class in `game.classes` lists `keywords`: saying one of them in the lobby picks it.
"""

import re

from magic_box.core.config import Config
from magic_box.core.contracts import ClassView

_WORD = re.compile(r"[a-z]+")


def class_ids(cfg: Config) -> list[str]:
    return list(cfg["game"]["classes"])


def class_name(cfg: Config, class_id: str) -> str:
    return cfg["game"]["classes"][class_id]["name"]


def class_views(cfg: Config) -> tuple[ClassView, ...]:
    """Every class in config order, for the lobby's class-pick screen."""
    return tuple(
        ClassView(cid, c["name"], tuple(s["name"] for s in c["spells"]))
        for cid, c in cfg["game"]["classes"].items()
    )


def parse_class(text: str, cfg: Config) -> str | None:
    """Class id picked by a transcript, or None. The last keyword said wins ("fire, no, holy")."""
    keywords = {
        kw.lower(): cid for cid, c in cfg["game"]["classes"].items() for kw in c["keywords"]
    }
    picked = None
    for word in _WORD.findall(text.lower()):
        picked = keywords.get(word, picked)
    return picked


def class_prompt(cfg: Config) -> str:
    """'SAY FIRE, LIGHTNING OR HOLY': the first keyword of each class, in config order."""
    words = [c["keywords"][0].upper() for c in cfg["game"]["classes"].values()]
    if len(words) == 1:
        return f"SAY {words[0]}"
    return f"SAY {', '.join(words[:-1])} OR {words[-1]}"

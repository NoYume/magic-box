"""Spell table (spec section 8, game/; Appendix A).

Owner: Adetola
Thin placeholder rules (2026-10-24 phase); replace freely.
"""

from dataclasses import dataclass

from magic_box.core.config import Config

BASIC_ATTACK_ID = "basic"


@dataclass(frozen=True)
class SpellDef:
    id: str
    name: str
    cost: float
    damage: float
    travel_s: float
    release: str
    fallback: dict[int, str]


def load_spells(cfg: Config, class_id: str) -> list[SpellDef]:
    return [
        SpellDef(
            id=s["id"],
            name=s["name"],
            cost=s["cost"],
            damage=s["damage"],
            travel_s=s["travel_s"],
            release=s["release"],
            fallback={int(k): v for k, v in s["fallback"].items()},
        )
        for s in cfg["game"]["classes"][class_id]["spells"]
    ]

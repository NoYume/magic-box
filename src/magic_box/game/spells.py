"""Spell table (spec section 8, game/; Appendix A).

Owner: Adetola
"""

from dataclasses import dataclass

from magic_box.core.config import Config


@dataclass(frozen=True)
class SpellDef:
    id: str
    name: str
    cost: float
    damage: float
    travel_s: float
    release: str


def load_spells(cfg: Config, class_id: str) -> list[SpellDef]:
    raise NotImplementedError("TODO(Adetola): load spells for a class from config")

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
    """Load one class's spell definitions from config."""
    try:
        rows = cfg["game"]["classes"][class_id]["spells"]
    except KeyError as exc:
        raise ValueError(f"unknown class {class_id!r}") from exc
    return [
        SpellDef(
            id=str(row["id"]),
            name=str(row["name"]),
            cost=float(row["cost"]),
            damage=float(row["damage"]),
            travel_s=float(row["travel_s"]),
            release=str(row["release"]),
        )
        for row in rows
    ]


def spell_map(cfg: Config, class_id: str) -> dict[str, SpellDef]:
    return {spell.id: spell for spell in load_spells(cfg, class_id)}

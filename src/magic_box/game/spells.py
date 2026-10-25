"""Spell table (spec section 8, game/; Appendix A; docs/game-design.md).

Owner: Adetola

Every number comes from the spell's entry in `config.yaml` (`game.classes.<id>.spells`).
Optional keys: `effect` + `effect_s` (a timed effect, see `game/effects.py`), `heal_hp`,
`hits` + `chain_gap_s` (several projectiles, one after another).
"""

from dataclasses import dataclass

from magic_box.core.config import Config
from magic_box.game.effects import HIT_EFFECTS

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
    effect: str | None = None  # an EFFECT_KINDS entry
    effect_s: float = 0.0
    heal_hp: float = 0.0
    hits: int = 1
    chain_gap_s: float = 0.0

    @property
    def is_projectile(self) -> bool:
        """Flies at the opponent: it deals damage or puts an effect on whoever it hits."""
        return self.damage > 0 or self.effect in HIT_EFFECTS


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
            effect=s.get("effect"),
            effect_s=float(s.get("effect_s", 0.0)),
            heal_hp=float(s.get("heal_hp", 0.0)),
            hits=int(s.get("hits", 1)),
            chain_gap_s=float(s.get("chain_gap_s", 0.0)),
        )
        for s in cfg["game"]["classes"][class_id]["spells"]
    ]


def basic_attack(cfg: Config) -> SpellDef:
    """The free push attack used when no spell is charged."""
    g = cfg["game"]
    return SpellDef(
        BASIC_ATTACK_ID,
        "Basic",
        0,
        g["basic_attack_damage"],
        g["basic_attack_travel_s"],
        "push",
        {},
    )

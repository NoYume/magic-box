"""Combat formula (spec section 8, game/; Appendix A).

Owner: Adetola

Appendix A:
    damage = base x speed_mult x atk_dist_mult x def_dist_mult x buffs
    speed_mult = push speed / 2.0 m/s, clamped to 0.6-1.8
    distance multiplier: smooth, x1.4 at 1.2 m to x0.7 at 2.8 m
    attacker distance read at release, defender distance at impact
"""

from magic_box.core.config import Config


def damage(
    base: float,
    push_speed: float,
    atk_dist: float,
    def_dist: float,
    buff_mult: float,
    cfg: Config,
) -> float:
    raise NotImplementedError("TODO(Adetola): combat damage formula")

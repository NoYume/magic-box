"""Combat formula (spec section 8, game/; Appendix A).

Owner: Adetola
Thin placeholder rules (2026-10-24 phase); replace freely.

Appendix A:
    damage = base x speed_mult x atk_dist_mult x def_dist_mult x buffs
    speed_mult = push speed / 2.0 m/s, clamped to 0.6-1.8
    distance multiplier: smooth, x1.4 at 1.2 m to x0.7 at 2.8 m
    attacker distance read at release, defender distance at impact
"""

from magic_box.core.config import Config


def speed_mult(speed: float | None, cfg: Config) -> float:
    """Push-speed multiplier; None (no push, e.g. a pose release) is 1.0."""
    if speed is None:
        return 1.0
    c = cfg["game"]["combat"]
    return min(max(speed / c["speed_ref_mps"], c["speed_mult_min"]), c["speed_mult_max"])


def dist_mult(dist: float, cfg: Config) -> float:
    """Linear near->far multiplier, clamped outside; dist <= 0 (unknown) is 1.0."""
    if dist <= 0:
        return 1.0
    c = cfg["game"]["combat"]
    near_m, far_m = c["near_m"], c["far_m"]
    f = min(max((dist - near_m) / (far_m - near_m), 0.0), 1.0)
    return c["near_mult"] + f * (c["far_mult"] - c["near_mult"])


def damage(
    base: float,
    push_speed: float | None,
    atk_dist: float,
    def_dist: float,
    buff_mult: float,
    cfg: Config,
) -> float:
    return (
        base
        * speed_mult(push_speed, cfg)
        * dist_mult(atk_dist, cfg)
        * dist_mult(def_dist, cfg)
        * buff_mult
    )

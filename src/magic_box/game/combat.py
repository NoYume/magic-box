"""Combat formula (spec section 8, game/; Appendix A).

Owner: Adetola
"""

from magic_box.core.config import Config


def _lerp_clamped(value: float, start: float, end: float, at_start: float, at_end: float) -> float:
    if end <= start:
        raise ValueError("distance_far_m must be greater than distance_near_m")
    t = max(0.0, min(1.0, (value - start) / (end - start)))
    return at_start + t * (at_end - at_start)


def distance_multiplier(distance: float, cfg: Config) -> float:
    game = cfg["game"]
    return _lerp_clamped(
        distance,
        float(game["distance_near_m"]),
        float(game["distance_far_m"]),
        float(game["distance_near_mult"]),
        float(game["distance_far_mult"]),
    )


def damage(
    base: float,
    push_speed: float,
    atk_dist: float,
    def_dist: float,
    buff_mult: float,
    cfg: Config,
) -> float:
    """Apply the Appendix A speed, distance and buff multipliers."""
    game = cfg["game"]
    speed = push_speed / float(game["speed_reference_mps"])
    speed = max(float(game["speed_mult_min"]), min(float(game["speed_mult_max"]), speed))
    return max(
        0.0,
        base
        * speed
        * distance_multiplier(atk_dist, cfg)
        * distance_multiplier(def_dist, cfg)
        * buff_mult,
    )

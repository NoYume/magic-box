"""Mutable match state (spec section 8, game/; Appendix A).

Owner: Adetola

MatchState will hold, per slot: HP, mana, charges (spell charged, window
deadline, reserved mana), buffs (Holy Light multiplier, Flame Wall block,
Static Field regen slow), and the projectiles in flight.
"""

from magic_box.core.config import Config


class MatchState:
    def __init__(self, cfg: Config) -> None:
        raise NotImplementedError("TODO(Adetola): HP, mana, charges, buffs, projectiles in flight")

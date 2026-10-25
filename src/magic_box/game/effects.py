"""Timed player effects (docs/game-design.md).

Owner: Adetola

- `shield` (Flame Wall, on the caster): blocks the next incoming hit, then ends.
- `empowered` (Holy Light, on the caster): spells and basic attacks released while it
  lasts deal x `game.empowered_mult`.
- `mana_slow` (Static Field, on the target): mana regen x `game.mana_slow_mult`.
- `slow` (Inferno, on the target): the next charge window is x `game.slow_charge_mult`;
  charging uses it up.

Times are on the match clock, so a pause freezes them.
"""

from magic_box.core.contracts import EFFECT_KINDS, EffectView

SELF_EFFECTS = ("shield", "empowered")  # put on the caster when the spell is released
HIT_EFFECTS = ("mana_slow", "slow")  # put on the target when the projectile lands


class Effects:
    """One player's active effects: kind -> match-clock time it ends."""

    def __init__(self) -> None:
        self._until: dict[str, float] = {}

    def add(self, kind: str, clock: float, duration_s: float) -> None:
        """Start `kind`, or extend it if it is already running longer."""
        self._until[kind] = max(self._until.get(kind, clock), clock + duration_s)

    def active(self, kind: str, clock: float) -> bool:
        return self._until.get(kind, clock) > clock

    def consume(self, kind: str, clock: float) -> bool:
        """End `kind` now; True if it was active."""
        was = self.active(kind, clock)
        self._until.pop(kind, None)
        return was

    def expire(self, clock: float) -> None:
        self._until = {k: t for k, t in self._until.items() if t > clock}

    def views(self, clock: float) -> tuple[EffectView, ...]:
        return tuple(
            EffectView(kind, self._until[kind] - clock)
            for kind in EFFECT_KINDS
            if self.active(kind, clock)
        )

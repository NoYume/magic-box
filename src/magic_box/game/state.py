"""Mutable match state (spec section 8, game/; Appendix A).

Owner: Adetola
"""

from dataclasses import dataclass, field

from magic_box.core.config import Config
from magic_box.core.contracts import Px
from magic_box.game.spells import SpellDef, spell_map


@dataclass
class ChargeState:
    spell_id: str
    expires_at: float
    match_score: float


@dataclass
class PlayerState:
    slot: int
    name: str
    class_id: str
    hp: float
    mana: float
    spells: dict[str, SpellDef]
    charge: ChargeState | None = None
    basic_ready_at: float = 0.0
    damage_buff_until: float = 0.0
    shield_until: float = 0.0
    regen_slow_until: float = 0.0
    last_dodge_at: float = float("-inf")
    zone: str = "neutral"
    dist: float = 0.0
    tracking_ok: bool = False
    mic_ok: bool = False


@dataclass
class ProjectileState:
    spell_id: str
    source_slot: int
    target_slot: int
    origin_px: Px
    launched_at: float
    impacts_at: float
    base_damage: float
    push_speed: float
    attacker_dist: float
    buff_mult: float


@dataclass
class MatchState:
    """All mutable combat state. No renderer or I/O state belongs here."""

    cfg: Config
    players: list[PlayerState] = field(init=False)
    projectiles: list[ProjectileState] = field(default_factory=list)
    started_at: float | None = None
    ended: bool = False
    winner: int | None = None
    remaining_s: float = field(init=False)
    last_step_at: float | None = None
    tracking_lost_at: float | None = None

    def __post_init__(self) -> None:
        self.remaining_s = float(self.cfg["game"]["round_s"])
        self._build_players()

    def _build_players(self) -> None:
        game = self.cfg["game"]
        defaults = game["default_classes"]
        self.players = [
            PlayerState(
                slot=slot,
                name=f"P{slot + 1}",
                class_id=defaults[slot],
                hp=float(game["hp_max"]),
                mana=float(game["mana_max"]),
                spells=spell_map(self.cfg, defaults[slot]),
            )
            for slot in (0, 1)
        ]

    def reset(self, now: float) -> None:
        profiles = [(player.name, player.class_id, player.mic_ok) for player in self.players]
        self._build_players()
        for player, (name, class_id, mic_ok) in zip(self.players, profiles, strict=True):
            player.name = name
            player.class_id = class_id
            player.spells = spell_map(self.cfg, class_id)
            player.mic_ok = mic_ok
        self.projectiles = []
        self.started_at = now
        self.ended = False
        self.winner = None
        self.remaining_s = float(self.cfg["game"]["round_s"])
        self.last_step_at = now
        self.tracking_lost_at = None

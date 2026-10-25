"""Data contracts that cross team ownership boundaries (spec section 7).

Owner: Nikhil
"""

from dataclasses import dataclass, field
from typing import Any

import numpy as np

Vec3 = tuple[float, float, float]  # meters, camera frame
Px = tuple[float, float]  # pixels, unmirrored left image

SLOTS = (0, 1)
ZONES = ("danger", "neutral", "far")
SCENES = ("boot", "lobby", "loading", "fight", "victory")
VOICE_KINDS = ("incantation", "transcript", "status")
VOICE_MODES = ("transcript", "incantation")
ACTION_KINDS = ("charge", "push", "pose", "dodge", "speech")
RELEASE_KINDS = ("push", "two_hand_push", "arm_overhead", "hands_together")
DODGE_KINDS = ("step", "duck")
EFFECT_KINDS = ("shield", "empowered", "mana_slow", "slow")
GAME_EVENT_KINDS = (
    "match_start",
    "cast",
    "hit",
    "dodge",
    "block",
    "heal",
    "buff",
    "ko",
    "match_end",
)
KEYPOINT_NAMES = (
    "head",
    "neck",
    "pelvis",
    "l_shoulder",
    "r_shoulder",
    "l_wrist",
    "r_wrist",
    "l_ankle",
    "r_ankle",
)
SKELETON_EDGES = (
    ("head", "neck"),
    ("neck", "pelvis"),
    ("neck", "l_shoulder"),
    ("neck", "r_shoulder"),
    ("l_shoulder", "l_wrist"),
    ("r_shoulder", "r_wrist"),
    ("pelvis", "l_ankle"),
    ("pelvis", "r_ankle"),
)


def _check_in(name: str, value: Any, allowed: tuple) -> None:
    if value not in allowed:
        raise ValueError(f"{name} must be one of {allowed}, got {value!r}")


@dataclass(frozen=True)
class Push:
    """One detected thrust toward the camera."""

    hand: str  # "L" | "R"
    speed: float  # m/s toward the camera relative to the torso (positive number)
    origin_px: Px  # wrist pixel when detected (projectile spawn point)


@dataclass(frozen=True)
class PlayerState:
    """Perception to game, one per slot per camera frame."""

    slot: int
    player_id: int  # ZED tracking id (fake mode: slot + 1)
    t: float
    cam_t: float
    frame_idx: int
    tracking_ok: bool
    root: Vec3
    root_vx: float
    head: Vec3
    wrists: dict[str, Vec3]  # "L"/"R" (person's own), valid points only: read with .get()
    wrist_vz: dict[
        str, float
    ]  # m/s relative to the neck, negative toward the camera; both keys always
    zone: str
    push: Push | None
    pose_flags: frozenset[str]
    bbox_px: tuple[int, int, int, int]
    keypoints_px: dict[str, Px]  # valid points only
    finger_gesture: dict[str, str | None]

    def __post_init__(self) -> None:
        _check_in("slot", self.slot, SLOTS)
        _check_in("zone", self.zone, ZONES)


@dataclass(frozen=True)
class VoiceEvent:
    """Voice to game."""

    slot: int
    t: float
    kind: str  # "incantation" | "transcript" | "status"
    text: str
    spell_id: str | None
    match_score: float  # 0-100

    def __post_init__(self) -> None:
        _check_in("slot", self.slot, SLOTS)
        _check_in("kind", self.kind, VOICE_KINDS)


@dataclass(frozen=True)
class Action:
    """Intent to game rules."""

    kind: str  # "charge" | "push" | "pose" | "dodge" | "speech"
    slot: int
    t: float
    spell_id: str | None = None
    match_score: float = 0.0
    push: Push | None = None
    pose: str | None = None
    dodge: str | None = None  # "step" | "duck"
    dist: float = 0.0
    two_hand: bool = False  # push: other hand crossed the threshold within two_hand_window_s
    text: str = ""  # speech: final transcript of one speech turn

    def __post_init__(self) -> None:
        _check_in("kind", self.kind, ACTION_KINDS)
        _check_in("slot", self.slot, SLOTS)
        if self.dodge is not None:
            _check_in("dodge", self.dodge, DODGE_KINDS)


@dataclass(frozen=True)
class GameEvent:
    """Append-only match log entry."""

    t: float
    kind: str
    slot: int | None
    data: dict[str, Any]

    def __post_init__(self) -> None:
        _check_in("kind", self.kind, GAME_EVENT_KINDS)
        if self.slot is not None:
            _check_in("slot", self.slot, SLOTS)


@dataclass(frozen=True)
class SpellView:
    id: str
    name: str
    incantation: str
    cost: float
    charged: bool
    release: str = "push"  # push | two_hand_push | arm_overhead | hands_together

    def __post_init__(self) -> None:
        _check_in("release", self.release, RELEASE_KINDS)


@dataclass(frozen=True)
class EffectView:
    """A timed effect on a player, for a HUD icon and countdown."""

    kind: str  # "shield" | "empowered" | "mana_slow" | "slow"
    remaining_s: float

    def __post_init__(self) -> None:
        _check_in("kind", self.kind, EFFECT_KINDS)


@dataclass(frozen=True)
class ClassView:
    """A class the lobby offers, for the class-pick screen."""

    id: str
    name: str
    spells: tuple[str, ...]  # spell display names, in config order


@dataclass(frozen=True)
class CheckView:
    """One boot self-check line (camera, mics, network, api key)."""

    name: str
    ok: bool
    detail: str = ""


@dataclass(frozen=True)
class PlayerView:
    slot: int
    name: str
    class_id: str
    hp: float
    hp_max: float
    mana: float
    mana_max: float
    spells: tuple[SpellView, ...]
    zone: str
    dist: float
    mic_ok: bool
    tracking_ok: bool
    effects: tuple[EffectView, ...] = ()
    charge_s: float = 0.0  # seconds left on the charge window, 0 when nothing is charged
    cooldown_s: float = 0.0  # seconds left on the basic-attack cooldown
    ready: bool = False  # lobby and victory: hands up, ready to start
    heard: str = ""  # last final transcript from this player's mic (lobby mic check)
    stats: dict[str, float] = field(default_factory=dict)  # match totals, see root CLAUDE.md
    can_parry: bool = False  # the class guards and parries (game.parry_classes)
    guard_s: float = 0.0  # fight only: seconds left on a raised guard's parry window
    guard_cooldown_s: float = 0.0  # fight only: seconds until a new guard counts
    riposte_s: float = 0.0  # fight only: seconds left to push a riposte after a parry

    def __post_init__(self) -> None:
        _check_in("slot", self.slot, SLOTS)
        _check_in("zone", self.zone, ZONES)


@dataclass(frozen=True)
class ProjectileView:
    spell_id: str
    target_slot: int  # drawn on the target's half
    origin_px: Px  # attacker wrist in the camera image
    progress: float  # 0 = just cast, 1 = impact
    in_dodge_window: bool

    def __post_init__(self) -> None:
        _check_in("target_slot", self.target_slot, SLOTS)


@dataclass(frozen=True)
class GameView:
    """Game to render, one snapshot per tick. Render draws only this."""

    scene: str
    players: tuple[PlayerView, PlayerView]
    projectiles: tuple[ProjectileView, ...]
    banner: str | None
    timer_s: float | None
    chronicle: str | None
    events: tuple[GameEvent, ...] = ()  # GameEvents emitted this tick (render FX and sounds)
    classes: tuple[ClassView, ...] = ()  # lobby: classes on offer
    checks: tuple[CheckView, ...] = ()  # boot: self-check results
    winner_slot: int | None = None  # victory: winner, None for a draw
    howto_s: float | None = None  # loading: seconds left on the how-to-play screen, else None

    def __post_init__(self) -> None:
        _check_in("scene", self.scene, SCENES)
        if self.winner_slot is not None:
            _check_in("winner_slot", self.winner_slot, SLOTS)
        if len(self.players) != 2 or any(p.slot != i for i, p in enumerate(self.players)):
            raise ValueError("players must be ordered by slot (players[i].slot == i)")


@dataclass(frozen=True)
class VoiceConfig:
    """Voice recognition mode plus per-slot incantations (slot -> spell_id -> text)."""

    mode: str
    incantations: dict[int, dict[str, str]]

    def __post_init__(self) -> None:
        _check_in("mode", self.mode, VOICE_MODES)
        for slot in self.incantations:
            _check_in("incantation slot", slot, SLOTS)


@dataclass(frozen=True, eq=False)
class Frame:
    """Camera frame. image is HxWx4 uint8 BGRA, unmirrored. Not serializable."""

    frame_idx: int
    cam_t: float
    image: np.ndarray

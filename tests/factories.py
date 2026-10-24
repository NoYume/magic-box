"""Test factories for the shared data contracts."""

from typing import Any

from magic_box.core.contracts import (
    KEYPOINT_NAMES,
    GameView,
    PlayerState,
    PlayerView,
    SpellView,
)


def make_state(slot: int = 0, **overrides: Any) -> PlayerState:
    root = (0.6 if slot == 0 else -0.6, 0.0, 2.0)
    fields: dict[str, Any] = {
        "slot": slot,
        "player_id": slot + 1,
        "t": 0.0,
        "cam_t": 0.0,
        "frame_idx": 0,
        "tracking_ok": True,
        "root": root,
        "root_vx": 0.0,
        "head": (root[0], -0.7, root[2]),
        "wrists": {"L": (root[0] - 0.3, -0.2, root[2]), "R": (root[0] + 0.3, -0.2, root[2])},
        "wrist_vz": {"L": 0.0, "R": 0.0},
        "zone": "neutral",
        "push": None,
        "pose_flags": frozenset(),
        "bbox_px": (100, 100, 200, 400),
        "keypoints_px": {
            name: (100.0 + 10.0 * i, 200.0 + 5.0 * i) for i, name in enumerate(KEYPOINT_NAMES)
        },
        "finger_gesture": {"L": None, "R": None},
    }
    fields.update(overrides)
    return PlayerState(**fields)


def _make_player_view(slot: int) -> PlayerView:
    spell = SpellView("fireball", "Fireball", "embers burn", 20.0, False)
    return PlayerView(
        slot=slot,
        name=f"P{slot + 1}",
        class_id="mage",
        hp=100.0,
        hp_max=100.0,
        mana=50.0,
        mana_max=100.0,
        spells=(spell,),
        zone="neutral",
        dist=2.0,
        mic_ok=True,
        tracking_ok=True,
    )


def make_view(**overrides: Any) -> GameView:
    fields: dict[str, Any] = {
        "scene": "fight",
        "players": (_make_player_view(0), _make_player_view(1)),
        "projectiles": (),
        "banner": None,
        "timer_s": 90.0,
        "chronicle": None,
    }
    fields.update(overrides)
    return GameView(**fields)

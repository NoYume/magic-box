"""Test factories for the shared data contracts."""

from typing import Any

from magic_box.core.contracts import (
    KEYPOINT_NAMES,
    CheckView,
    ClassView,
    EffectView,
    GameEvent,
    GameView,
    PlayerState,
    PlayerView,
    ProjectileView,
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


# -- fully populated views (render tests and scene previews) ------------------

FULL_SPELLS = {
    0: (
        ("fireball", "Fireball", "embers of the forty acres burn", 25.0, "push"),
        ("flame_wall", "Flame Wall", "rise crimson rampart", 30.0, "two_hand_push"),
        ("inferno", "Inferno", "let the whole sky catch fire", 60.0, "push"),
    ),
    1: (
        ("bolt", "Bolt", "lightning answer my call", 20.0, "push"),
        ("chain", "Chain", "chain the storm across the river", 35.0, "push"),
        ("static_field", "Static Field", "hum of the restless grid", 30.0, "two_hand_push"),
    ),
}


def make_full_player(slot: int, **overrides: Any) -> PlayerView:
    """A PlayerView with every optional field set (effects, charge, stats, ...)."""
    spells = tuple(
        SpellView(sid, name, inc, cost, slot == 0 and i == 0, release)
        for i, (sid, name, inc, cost, release) in enumerate(FULL_SPELLS[slot])
    )
    effects = (
        (EffectView("shield", 3.2), EffectView("empowered", 5.5))
        if slot == 0
        else (EffectView("mana_slow", 4.1), EffectView("slow", 1.4))
    )
    fields: dict[str, Any] = {
        "slot": slot,
        "name": ("Daniel", "Adetola")[slot],
        "class_id": ("fire_mage", "lightning_mage")[slot],
        "hp": (72.0, 23.0)[slot],
        "hp_max": 100.0,
        "mana": (55.0, 25.0)[slot],
        "mana_max": 100.0,
        "spells": spells,
        "zone": ("danger", "far")[slot],
        "dist": (1.3, 2.7)[slot],
        "mic_ok": slot == 0,
        "tracking_ok": True,
        "effects": effects,
        "charge_s": 2.1 if slot == 0 else 0.0,
        "cooldown_s": 0.0 if slot == 0 else 0.5,
        "ready": slot == 0,
        "heard": ("call me daniel", "fire")[slot],
        "stats": {
            "damage": (77.0, 28.0)[slot],
            "hits": (6.0, 3.0)[slot],
            "casts": (5.0, 4.0)[slot],
            "dodges": (2.0, 1.0)[slot],
            "blocks": (1.0, 0.0)[slot],
            "heals": (0.0, 1.0)[slot],
            "best_push_mps": (3.4, 2.6)[slot],
        },
        "can_parry": slot == 1,
        "guard_s": (0.0, 0.2)[slot],
        "guard_cooldown_s": (0.0, 1.1)[slot],
        "riposte_s": (0.0, 0.9)[slot],
    }
    fields.update(overrides)
    return PlayerView(**fields)


def make_full_events(t: float = 0.0) -> tuple[GameEvent, ...]:
    """One GameEvent of every kind, with the data the engine logs."""
    return (
        GameEvent(t, "match_start", None, {"names": {0: "Daniel", 1: "Adetola"}}),
        GameEvent(t, "cast", 0, {"spell_id": "fireball", "release": "push", "two_hand": False}),
        GameEvent(t, "hit", 0, {"spell_id": "fireball", "damage": 18.4, "target": 1}),
        GameEvent(t, "dodge", 1, {"spell_id": "bolt", "dodge": "duck"}),
        GameEvent(t, "block", 0, {"spell_id": "bolt", "attacker": 1}),
        GameEvent(t, "heal", 1, {"spell_id": "heal", "amount": 25, "target": 1}),
        GameEvent(t, "buff", 0, {"spell_id": "holy_light", "effect": "empowered", "target": 0}),
        GameEvent(t, "ko", None, {"winner": 0}),
        GameEvent(t, "match_end", None, {"winner": 0, "reason": "ko"}),
    )


CHRONICLE = (
    "Under the tower's orange glow, Daniel called the embers of the forty acres and Adetola "
    "answered with lightning across the river. Three fireballs found their mark; one bolt was "
    "ducked at the last instant. When the smoke cleared, the crowd on Speedway knew the name of "
    "the new champion of the box."
)


def make_full_view(scene: str = "fight", **overrides: Any) -> GameView:
    """A GameView with every optional field populated (events, classes, checks, winner)."""
    fields: dict[str, Any] = {
        "scene": scene,
        "players": (make_full_player(0), make_full_player(1)),
        "projectiles": (
            ProjectileView("fireball", 1, (300.0, 250.0), 0.55, False),
            ProjectileView("bolt", 0, (650.0, 260.0), 0.8, True),
            ProjectileView("judgment", 0, (600.0, 240.0), 0.3, False),
            ProjectileView("basic", 1, (320.0, 280.0), 0.2, False),
        ),
        "banner": "FIREBALL!" if scene == "fight" else None,
        "timer_s": {"fight": 42.3, "loading": 2.4, "boot": 4.2}.get(scene),
        "chronicle": CHRONICLE if scene == "victory" else None,
        "events": make_full_events(),
        "classes": (
            ClassView("fire_mage", "Fire Mage", ("Fireball", "Flame Wall", "Inferno")),
            ClassView("lightning_mage", "Lightning Mage", ("Bolt", "Chain", "Static Field")),
            ClassView("holy_knight", "Holy Knight", ("Holy Light", "Heal", "Judgment")),
        ),
        "checks": (
            CheckView("camera", True, "ZED X SVGA 30 fps"),
            CheckView("mic P1", True, "USB lav"),
            CheckView("mic P2", False, "no device"),
            CheckView("network", True),
            CheckView("api key", False, "META_MODEL_API_KEY not set"),
        ),
        "winner_slot": 0 if scene == "victory" else None,
    }
    fields.update(overrides)
    return GameView(**fields)


def pin_pre_venue_tuning(cfg: dict) -> dict:
    """Restore the numbers these tests were written against, before the 2026-10-25 Jetson
    tuning: wider zones and damage-distance span, start at 2.0 m, no how-to-play screen."""
    cfg["perception"]["zones"].update(danger_max_m=1.6, far_min_m=2.4)
    cfg["game"]["combat"].update(near_m=1.2, far_m=2.8)
    cfg["game"]["howto_s"] = 0.0
    cfg["fake"]["start_z_m"] = 2.0
    # Long incantations (3-7 words, no per-spell count) from before the short-spell change.
    cfg["ai"].update(min_words=3, max_words=7)
    for cls in cfg["game"]["classes"].values():
        for spell in cls["spells"]:
            spell.pop("words", None)
            spell["fallback"] = dict(zip((0, 1), OLD_FALLBACKS[spell["id"]], strict=True))
    return cfg


OLD_FALLBACKS = {
    "fireball": ("embers of the forty acres burn", "ignite the longhorn flame"),
    "flame_wall": ("rise crimson rampart", "wall of burning cedar"),
    "inferno": ("let the whole sky catch fire", "summon the sixth street inferno"),
    "bolt": ("storm of speedway strike", "lightning answer my call"),
    "chain": ("thunder binds the tower", "chain the storm across the river"),
    "static_field": ("static fills the air", "hum of the restless grid"),
    "holy_light": ("light of the tower guide my blade", "dawn breaks upon my sword"),
    "heal": ("mend me gentle light", "breath of the hill country heal"),
    "judgment": ("judgment falls from above", "steel and sunlight strike true"),
}

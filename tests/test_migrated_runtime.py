from dataclasses import replace
from pathlib import Path

import pytest

from magic_box.ai.incantations import fallback_incantations, generate_incantations
from magic_box.core.config import load_config
from magic_box.game.combat import damage, distance_multiplier
from magic_box.intent.dodge import DodgeDetector
from magic_box.voice.matcher import match_incantation
from tests.factories import make_state

CFG = load_config(Path(__file__).resolve().parents[1] / "config.yaml")


def test_windowed_dodge_detection():
    detector = DodgeDetector(CFG)
    assert detector.update(make_state(t=0.0, root=(0.0, 0.0, 2.0))) is None
    moved = make_state(t=0.2, root=(0.4, 0.0, 2.0))
    assert detector.update(moved) == "step"

    detector = DodgeDetector(CFG)
    assert detector.update(make_state(t=0.0, head=(0.0, -0.7, 2.0))) is None
    ducked = replace(make_state(t=0.2), head=(0.0, -0.4, 2.0))
    assert detector.update(ducked) == "duck"


def test_damage_formula_uses_configured_metric_multipliers():
    assert distance_multiplier(CFG["game"]["distance_near_m"], CFG) == pytest.approx(
        CFG["game"]["distance_near_mult"]
    )
    amount = damage(10, 2.0, 1.2, 2.8, 1.5, CFG)
    assert amount == pytest.approx(10 * 1.4 * 0.7 * 1.5)


def test_voice_matcher_is_scoped_to_supplied_incantations():
    matched = match_incantation(
        "embers of the forty acres burn",
        {"fireball": "embers of the forty acres burn"},
        80,
    )
    assert matched == ("fireball", 100.0)
    assert match_incantation("lightning answer", {"fireball": "embers burn"}, 80) is None


class BrokenSpark:
    def complete(self, system, user):
        raise RuntimeError("offline")


def test_incantation_generation_always_has_config_fallback():
    classes = dict(CFG["game"]["default_classes"])
    assert generate_incantations(BrokenSpark(), classes, CFG) == fallback_incantations(classes, CFG)

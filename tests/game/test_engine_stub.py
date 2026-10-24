from pathlib import Path

import pytest

from magic_box.core.config import load_config
from magic_box.game.engine import Engine
from magic_box.intent.fusion import Intent
from tests.factories import make_state

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")


def test_engine_placeholder_view():
    view, events = Engine(CFG).step(
        [], {0: make_state(slot=0, zone="danger", root=(0.6, 0.0, 1.2))}, now=0.0
    )
    p1, p2 = view.players
    cls = CFG["game"]["default_classes"][0]
    assert view.scene == "fight" and events == [] and view.timer_s == CFG["game"]["round_s"]
    assert p1.hp == p1.hp_max == CFG["game"]["hp_max"]
    assert p1.zone == "danger" and p1.dist == pytest.approx(1.2) and p1.tracking_ok
    assert p2.tracking_ok is False  # no state for slot 1 yet
    assert [s.incantation for s in p1.spells] == [
        sp["fallback"][0] for sp in CFG["game"]["classes"][cls]["spells"]
    ]
    assert view.projectiles == ()


def test_intent_placeholder_returns_no_actions():
    assert Intent(CFG).update([], [], 0.0) == []

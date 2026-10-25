"""Loading opens with the how-to-play screen (`game.howto_s`), then the spell cards."""

import copy
from pathlib import Path

from magic_box.core.config import load_config
from magic_box.game.engine import Engine
from tests.factories import make_state

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")
G = CFG["game"]
DT = 0.05


def _states(flags=frozenset()):
    return {s: make_state(s, pose_flags=flags) for s in (0, 1)}


def _to_loading(e):
    e.provide_check("camera", True)
    t = 0.0
    while e.step([], _states(), t)[0].scene != "lobby":
        t += DT
    while e.step([], _states(frozenset({"hands_up"})), t)[0].scene != "loading":
        t += DT
    return t


def test_loading_shows_how_to_play_first_with_no_countdown():
    e = Engine(copy.deepcopy(CFG))
    t0 = _to_loading(e)
    e.provide_incantations({0: {}, 1: {}})  # Spark is done at once
    view, _ = e.step([], _states(), t0 + DT)
    assert view.howto_s is not None and view.howto_s > G["howto_s"] - 0.2
    assert view.timer_s is None  # no ticking under the how-to screen
    view, _ = e.step([], _states(), t0 + G["howto_s"] + DT)
    assert view.scene == "loading" and view.howto_s is None
    assert view.timer_s is not None and view.timer_s > G["loading_read_s"] - 0.2


def test_spell_cards_get_the_full_read_time_after_the_how_to_screen():
    e = Engine(copy.deepcopy(CFG))
    t = t0 = _to_loading(e)
    e.provide_incantations({0: {}, 1: {}})
    while e.step([], _states(), t)[0].scene == "loading":
        t += DT
    assert t - t0 >= G["howto_s"] + G["loading_read_s"] - 2 * DT


def test_howto_0_skips_the_screen():
    cfg = copy.deepcopy(CFG)
    cfg["game"]["howto_s"] = 0.0
    e = Engine(cfg)
    t0 = _to_loading(e)
    view, _ = e.step([], _states(), t0 + DT)
    assert view.howto_s is None


def test_other_scenes_have_no_howto():
    e = Engine(copy.deepcopy(CFG))
    view, _ = e.step([], _states(), 0.0)
    assert view.scene == "boot" and view.howto_s is None

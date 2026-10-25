"""Tests for the duel chronicle and its template fallback.

Owner: Nikhil
"""

import re
from pathlib import Path

from magic_box.ai.chronicle import template_chronicle, write_chronicle
from magic_box.core.config import load_config
from magic_box.core.contracts import GameEvent
from tests.ai.fakes import FakeClient

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")
NAMES = {0: "Ada", 1: "Bo"}


def ev(kind, slot=None, **data):
    return GameEvent(0.0, kind, slot, data)


KO_LOG = [
    ev("match_start", names={0: "Ada", 1: "Bo"}, classes={0: "fire_mage", 1: "lightning_mage"}),
    ev("cast", 0, spell_id="fireball", release="push", two_hand=False),
    ev("hit", 0, spell_id="fireball", damage=19.8, target=1, hp_left=80.2),
    ev("dodge", 1, spell_id="basic", dodge="duck"),
    ev("ko", 0, winner=0),
    ev("match_end", None, winner=0, reason="ko", hp={0: 100.0, 1: 0.0}),
]


def test_template_ko_mentions_names_classes_big_hit_and_ending():
    text = template_chronicle(KO_LOG, NAMES, CFG)
    for part in ("Ada", "Bo", "Fire Mage", "Lightning Mage", "Fireball", "19.8", "knocked out"):
        assert part in text


def test_template_time_out_and_draw():
    timeout = KO_LOG[:4] + [ev("match_end", None, winner=1, reason="time", hp={0: 40.0, 1: 60.0})]
    text = template_chronicle(timeout, NAMES, CFG)
    assert "time" in text and "Bo" in text
    draw = KO_LOG[:1] + [ev("match_end", None, winner=None, reason="time", hp={0: 100.0, 1: 100.0})]
    assert "draw" in template_chronicle(draw, NAMES, CFG).lower()


def test_template_handles_empty_log():
    assert "Ada" in template_chronicle([], NAMES, CFG)


def test_template_without_match_start_omits_classes():
    text = template_chronicle(KO_LOG[1:], NAMES, CFG)
    assert "Ada" in text and "Mage" not in text


def test_write_chronicle_uses_client_then_falls_back():
    client = FakeClient("A short tale of Ada and Bo.")
    assert write_chronicle(client, KO_LOG, NAMES, CFG) == "A short tale of Ada and Bo."
    assert "Ada" in client.calls[0][1] and "fireball" in client.calls[0][1].lower()
    for bad in ("", "   ", RuntimeError("down")):
        expected = template_chronicle(KO_LOG, NAMES, CFG)
        assert write_chronicle(FakeClient(bad), KO_LOG, NAMES, CFG) == expected


def _sentences(text):
    return [p for p in re.split(r"(?<=[.!?])\s+", text.strip()) if p]


def test_template_is_two_to_four_sentences():
    timeout = KO_LOG[:4] + [ev("match_end", None, winner=1, reason="time", hp={0: 40.0, 1: 60.0})]
    draw = KO_LOG[:1] + [ev("match_end", None, winner=None, reason="time", hp={0: 1.0, 1: 1.0})]
    for log in (KO_LOG, timeout, draw, []):
        assert 2 <= len(_sentences(template_chronicle(log, NAMES, CFG))) <= 4


def test_template_survives_malformed_log():
    log = [
        ev("match_start", names={"x": "Ada"}, classes={None: "fire_mage", "1": "lightning_mage"}),
        ev("hit", 0, spell_id="fireball", damage=None, target=1, hp_left=1),
        ev("hit", 1, spell_id="bolt", damage="lots", target=0, hp_left=1),
        ev("match_end", None, winner="nobody", reason="ko", hp={"a": 1}),
    ]
    text = template_chronicle(log, NAMES, CFG)
    assert isinstance(text, str) and text
    assert "draw" in text.lower()

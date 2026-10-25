"""Tests for incantation generation, validation and fallback.

Owner: Nikhil
"""

import copy
import json
from pathlib import Path

import pytest

from magic_box.ai.incantations import (
    fallback_incantations,
    generate_incantations,
    validate_incantations,
)
from magic_box.core.config import load_config
from tests.ai.fakes import FakeClient

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")
CLASSES = {0: "fire_mage", 1: "lightning_mage"}
NAMES = {0: "Ada", 1: "Bo"}
GOOD = {
    "0": {
        "fireball": "embers dance on the drag",
        "flame_wall": "rise wall of cedar smoke",
        "inferno": "let sixth street blaze tonight",
    },
    "1": {
        "bolt": "thunder over zilker hill",
        "chain": "lightning links the river bridges",
        "static_field": "hum across the capitol dome",
    },
}


def test_fallback_from_config():
    fb = fallback_incantations(CLASSES, CFG)
    assert fb[0]["fireball"] == "embers of the forty acres burn"
    assert fb[1]["bolt"] == "lightning answer my call"


def test_generate_accepts_valid_reply():
    client = FakeClient(json.dumps(GOOD))
    out = generate_incantations(client, CLASSES, NAMES, CFG)
    assert out == {0: GOOD["0"], 1: GOOD["1"]}
    system, user = client.calls[0]
    assert "Ada" in user and "fire_mage" in user and "fireball" in user


def test_code_fence_is_stripped():
    reply = "```json\n" + json.dumps(GOOD) + "\n```"
    out = generate_incantations(FakeClient(reply), CLASSES, NAMES, CFG)
    assert out[1]["bolt"] == "thunder over zilker hill"


def test_int_keys_whitespace_and_unknown_spells():
    raw = {0: dict(GOOD["0"]), 1: dict(GOOD["1"])}
    raw[0]["fireball"] = "  embers   dance on the drag "
    raw[0]["bogus"] = "ignored entirely here"
    out = validate_incantations(raw, CLASSES, CFG)
    assert out[0]["fireball"] == "embers dance on the drag"
    assert "bogus" not in out[0]


def test_invalid_entries_fall_back_per_spell():
    raw = copy.deepcopy(GOOD)
    raw["0"]["fireball"] = "one two three four five six seven eight"  # too long
    raw["0"]["flame_wall"] = "too short"  # too short
    raw["0"]["inferno"] = "fire 2 go now"  # digit
    raw["1"]["chain"] = raw["1"]["bolt"]  # duplicate in own set
    del raw["1"]["static_field"]  # missing
    out = validate_incantations(raw, CLASSES, CFG)
    fb = fallback_incantations(CLASSES, CFG)
    assert out[0] == fb[0]
    assert out[1] == {
        "bolt": GOOD["1"]["bolt"],
        "chain": fb[1]["chain"],
        "static_field": fb[1]["static_field"],
    }


def test_identical_sets_force_fallback_for_slot_1():
    raw = {"0": GOOD["0"], "1": dict(zip(GOOD["1"], GOOD["0"].values(), strict=True))}
    out = validate_incantations(raw, CLASSES, CFG)
    assert out[0] == GOOD["0"] and out[1] == fallback_incantations(CLASSES, CFG)[1]


@pytest.mark.parametrize("reply", ["not json", "[]", '{"0": 5}', RuntimeError("boom")])
def test_garbage_or_exception_gives_full_fallback(reply):
    out = generate_incantations(FakeClient(reply), CLASSES, NAMES, CFG)
    assert out == fallback_incantations(CLASSES, CFG)

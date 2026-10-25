"""Tests for the duel chronicle and its template fallback.

Owner: Nikhil
"""

import re
from pathlib import Path

from magic_box.ai.chronicle import template_chronicle, write_chronicle
from magic_box.ai.spark_client import SparkClient
from magic_box.core.config import load_config
from magic_box.core.contracts import GameEvent
from tests.ai.fakes import FakeClient, FakeOpenAI

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


# Task 1's engine ends a match with reason "abandon" after a player is gone 20 s: the tracked
# player wins, or it is a draw when both are gone.
ABANDON_LOG = KO_LOG[:4] + [
    ev("match_end", None, winner=0, reason="abandon", hp={0: 80.0, 1: 70.0})
]
ABANDON_DRAW_LOG = KO_LOG[:4] + [
    ev("match_end", None, winner=None, reason="abandon", hp={0: 80.0, 1: 70.0})
]


def test_template_abandon_says_who_held_the_field():
    text = template_chronicle(ABANDON_LOG, NAMES, CFG)
    assert "Ada held the field when Bo left the arena." in text
    assert "time ran out" not in text and "knocked out" not in text
    draw = template_chronicle(ABANDON_DRAW_LOG, NAMES, CFG)
    assert "Both duelists left the arena" in draw and "draw" in draw.lower()
    assert "time ran out" not in draw


def test_spark_prompt_says_how_an_abandoned_match_ended():
    for log, ending in (
        (ABANDON_LOG, "Ending: Ada held the field when Bo left the arena."),
        (ABANDON_DRAW_LOG, "Ending: Both duelists left the arena"),
    ):
        client = FakeClient("A tale.")
        write_chronicle(client, log, NAMES, CFG)
        assert ending in client.calls[0][1]


BLOCK_HEAL_LOG = KO_LOG[:4] + [
    ev("block", 1, spell_id="fireball", attacker=0),
    ev("heal", 0, spell_id="heal", amount=25.0, hp=90.0),
    ev("heal", 0, spell_id="heal", amount=10.0, hp=100.0),
    ev("buff", 0, spell_id="holy_light", effect="empowered", target=0, duration_s=6.0),
    ev("match_end", None, winner=1, reason="time", hp={0: 40.0, 1: 60.0}),
]


def test_template_counts_blocks_and_heals():
    text = template_chronicle(BLOCK_HEAL_LOG, NAMES, CFG)
    assert "Bo blocked 1 attack" in text and "Ada healed twice" in text
    assert 2 <= len(_sentences(text)) <= 4
    assert "blocked" not in template_chronicle(KO_LOG, NAMES, CFG)  # none: not mentioned


def test_malformed_block_heal_and_abandon_never_raise():
    log = [
        ev("block", 1, spell_id=None, attacker="someone"),
        ev("heal", 0, spell_id="heal", amount="lots"),
        ev("match_end", None, winner=7, reason="abandon", hp=None),
    ]
    text = template_chronicle(log, NAMES, CFG)
    assert "Bo blocked 1 attack" in text and "Ada healed once" in text and "left the arena" in text
    client = FakeClient("A tale.")
    write_chronicle(client, log, NAMES, CFG)
    prompt = client.calls[0][1]
    assert "Bo blocked an attack." in prompt and "Ada healed 0.0 HP." in prompt


def test_spark_prompt_counts_and_lists_blocks_and_heals():
    client = FakeClient("A tale.")
    write_chronicle(client, BLOCK_HEAL_LOG, NAMES, CFG)
    prompt = client.calls[0][1]
    assert "Ada: 1 casts, 1 hits, 0 dodges, 0 blocks, 2 heals." in prompt
    assert "Bo: 0 casts, 0 hits, 1 dodges, 1 blocks, 0 heals." in prompt
    assert "Bo blocked Ada's Fireball." in prompt and "Ada healed 25.0 HP." in prompt


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


class KeyEchoError(Exception):
    """Like an openai APIStatusError whose message echoes request details."""

    status_code = 429


def test_spark_failure_logs_one_line_without_the_key(capsys):
    fake = FakeOpenAI(KeyEchoError("rate limited for key sk-secret-123"))
    client = SparkClient(CFG, env={"META_MODEL_API_KEY": "sk-secret-123"}, openai_factory=fake)
    assert write_chronicle(client, KO_LOG, NAMES, CFG) == template_chronicle(KO_LOG, NAMES, CFG)
    err = capsys.readouterr().err
    assert err == "spark: chronicle fell back: KeyEchoError 429\n"
    assert "sk-secret" not in err
    write_chronicle(FakeClient(RuntimeError("down sk-secret-123")), KO_LOG, NAMES, CFG)
    assert capsys.readouterr().err == "spark: chronicle fell back: RuntimeError\n"


def test_chronicle_whitespace_and_control_chars_are_cleaned():
    reply = "  Ada\x00 struck\n\tBo\u200b down.\r\n "
    assert write_chronicle(FakeClient(reply), KO_LOG, NAMES, CFG) == "Ada struck Bo down."


def test_long_chronicle_is_truncated_to_max_words():
    n = CFG["ai"]["chronicle_max_words"]
    exact = " ".join(f"w{i}" for i in range(n))
    assert write_chronicle(FakeClient(exact), KO_LOG, NAMES, CFG) == exact
    long = write_chronicle(FakeClient(exact + " w_extra more"), KO_LOG, NAMES, CFG)
    assert long == exact + "\u2026"


def test_chronicle_of_only_control_chars_gives_the_template():
    text = write_chronicle(FakeClient("\x00\n\u200b\x07 \t"), KO_LOG, NAMES, CFG)
    assert text == template_chronicle(KO_LOG, NAMES, CFG)

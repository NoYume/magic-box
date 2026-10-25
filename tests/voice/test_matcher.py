"""Tests for incantation matching and keyword extraction.

Owner: Nikhil
"""

from magic_box.voice.matcher import keywords_for, match_incantation, normalize

INC = {
    "fireball": "embers of the forty acres burn",
    "flame_wall": "rise crimson rampart",
    "inferno": "let the whole sky catch fire",
}
OTHER = {"bolt": "storm of speedway strike", "chain": "thunder binds the tower"}


def test_exact_match_scores_100():
    assert match_incantation("embers of the forty acres burn", INC, 80) == ("fireball", 100.0)


def test_filler_prefix_case_and_punctuation():
    assert match_incantation("Uh, okay... Embers of the Forty Acres burn!", INC, 80) == (
        "fireball",
        100.0,
    )


def test_half_said_partial_does_not_match():
    assert match_incantation("embers of the", INC, 80) is None


def test_misheard_word_still_matches_below_100():
    spell, score = match_incantation("embers of the forty acre burn", INC, 80)
    assert spell == "fireball" and 80 <= score < 100


def test_other_players_incantation_does_not_match():
    assert match_incantation("storm of speedway strike", INC, 80) is None
    assert match_incantation("thunder binds the tower", INC, 80) is None


def test_empty_and_short_incantations():
    assert match_incantation("", INC, 80) is None
    assert match_incantation("rise crimson rampart now", INC, 80) == ("flame_wall", 100.0)


def test_normalize():
    assert normalize("  Hello,   WORLD!! ") == "hello world"


def test_keywords_for():
    assert keywords_for(INC, 4) == [
        "embers",
        "forty",
        "acres",
        "burn",
        "rise",
        "crimson",
        "rampart",
        "whole",
        "catch",
        "fire",
    ]

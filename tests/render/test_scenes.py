import dataclasses

import pygame

from magic_box.core.contracts import SpellView
from magic_box.render.scenes import loading_lines, lobby_lines, victory_lines, wrap_text
from tests.factories import make_view


def test_lobby_lines_show_names_and_tracking():
    view = make_view(scene="lobby", banner="SAY YOUR NAME · BOTH RAISE YOUR HANDS")
    p2 = dataclasses.replace(view.players[1], tracking_ok=False)
    view = dataclasses.replace(view, players=(view.players[0], p2))
    lines = lobby_lines(view)
    assert "P1: TRACKED" in lines and "P2: STEP INTO VIEW" in lines


def test_loading_lines_show_incantation_and_cue():
    view = make_view(scene="loading", timer_s=2.4)
    p0 = dataclasses.replace(
        view.players[0],
        spells=(
            SpellView("fireball", "Fireball", "embers burn bright", 25.0, False, "push"),
            SpellView("flame_wall", "Flame Wall", "", 30.0, False, "two_hand_push"),
        ),
    )
    lines = loading_lines(dataclasses.replace(view, players=(p0, view.players[1])), 0)
    assert 'Fireball: "embers burn bright", then PUSH!' in lines
    assert 'Flame Wall: "…", then TWO-HAND PUSH!' in lines


def test_victory_lines_wait_for_chronicle():
    assert victory_lines(make_view(scene="victory", chronicle=None)) == ["writing the chronicle…"]
    assert victory_lines(make_view(scene="victory", chronicle="A tale.")) == ["A tale."]


def test_wrap_text_fits_width():
    pygame.init()
    try:
        font = pygame.font.Font(None, 36)
        lines = wrap_text("word " * 200, font, 600)
        assert len(lines) > 1 and all(font.size(line)[0] <= 600 for line in lines)
    finally:
        pygame.quit()


def test_headline_uses_banner_then_winner_slot_then_draw():
    from magic_box.render.scenes import headline
    from tests.factories import make_full_view

    assert headline(make_full_view("victory", banner="DANIEL WINS")) == "DANIEL WINS"
    assert headline(make_full_view("victory", winner_slot=1)) == "ADETOLA WINS"
    assert headline(make_full_view("victory", winner_slot=None)) == "DRAW"


def test_stat_lines_show_only_present_keys():
    from magic_box.render.scenes import stat_lines
    from tests.factories import make_full_player

    p = make_full_player(0, stats={"damage": 41.6, "best_push_mps": 3.25, "junk": "x"})
    assert stat_lines(p) == [("DAMAGE DEALT", "42"), ("FASTEST PUSH", "3.2 m/s")]
    assert stat_lines(make_full_player(0, stats={})) == []


def test_loading_card_shrinks_long_incantations_instead_of_dropping_lines():
    from magic_box.core.config import load_config
    from magic_box.render.scenes.loading import fit_incantation
    from magic_box.render.style import Theme

    cfg = load_config("config.yaml")
    pygame.init()
    try:
        th = Theme(cfg["render"])
        text = "summon thunderous crimson stormclouds across austin skylines " * 3  # ~180 chars
        font, lines = fit_incantation(th, text.strip(), 640, 100)
        assert "…" not in " ".join(lines) and len(" ".join(lines)) == len(text.strip()) + 2
        assert len(lines) * th.font(font).get_linesize() <= 100
        assert fit_incantation(th, "short words", 640, 100) == ("big", ["“short words”"])
    finally:
        pygame.quit()


def test_class_keyword_is_the_first_word():
    from magic_box.core.contracts import ClassView
    from magic_box.render.scenes.lobby import class_keyword

    assert class_keyword(ClassView("holy_knight", "Holy Knight", ())) == "HOLY"
    assert class_keyword(ClassView("x", "", ())) == "X"

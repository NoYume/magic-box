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

import dataclasses

from magic_box.core.contracts import SpellView
from magic_box.render.hud import name_line, release_cue, spell_line
from magic_box.render.layout import Rect
from tests.factories import make_view


def test_release_cues_and_spell_lines():
    assert release_cue("two_hand_push") == "TWO-HAND PUSH!"
    assert release_cue("arm_overhead") == "RAISE ARM!"
    charged = SpellView("heal", "Heal", "mend me", 40.0, True, "hands_together")
    assert spell_line(charged) == "Heal  CHARGED: HANDS TOGETHER!"
    assert spell_line(SpellView("bolt", "Bolt", "zap now go", 20.0, False)) == 'Bolt: "zap now go"'


def test_name_line_shows_mic_status():
    view = make_view()
    p = dataclasses.replace(view.players[0], mic_ok=False)
    assert name_line(p) == "P1 · mage · MIC OFF"
    assert name_line(view.players[1]).endswith("MIC OK")


def _hud():
    from pathlib import Path

    import pygame

    from magic_box.core.config import load_config
    from magic_box.render.hud import Hud
    from magic_box.render.style import Theme

    cfg = load_config(Path(__file__).resolve().parents[2] / "config.yaml")
    pygame.init()
    theme = Theme(cfg["render"])
    return cfg, theme, Hud(cfg, theme)


def test_bar_anim_eases_toward_target_and_ghost_holds():
    from magic_box.render.hud import BarAnim

    bar = BarAnim()
    bar.update(1.0, 0.016, 10.0, 0.5, 3.0)
    assert bar.shown == 1.0 and bar.ghost == 1.0
    bar.update(0.6, 0.016, 10.0, 0.5, 3.0)
    assert 0.6 < bar.shown < 1.0
    assert bar.ghost == 1.0  # held for ghost_hold_s
    for _ in range(200):
        bar.update(0.6, 0.016, 10.0, 0.5, 3.0)
    assert abs(bar.shown - 0.6) < 1e-3 and abs(bar.ghost - 0.6) < 1e-2
    bar.update(0.9, 0.016, 10.0, 0.5, 3.0)  # heal: the ghost never sits below the bar
    assert bar.ghost >= bar.shown


def test_hud_draws_full_and_default_views():
    import pygame

    from tests.factories import make_full_view

    cfg, theme, hud = _hud()
    try:
        surf = pygame.Surface((1920, 1080))
        for view in (make_view(), make_full_view("fight")):
            hud.update(view, 0.016)
            for slot in (0, 1):
                hud.draw_panel(surf, Rect(16 + 960 * slot, 784, 928, 280), view.players[slot], 1.0)
                hud.draw_enemy(
                    surf, Rect(230 + 960 * slot, 16, 499, 28), view.players[1 - slot], 690, 1.0
                )
            hud.draw_timer(surf, 960, view.timer_s, 1.0)
            hud.draw_timer(surf, 960, 4.2, 1.0)  # low-time pulse
            hud.draw_timer(surf, 960, None, 1.0)
    finally:
        pygame.quit()


def test_zone_meter_position_is_monotonic():
    import pygame

    _, _, hud = _hud()
    try:
        xs = [hud._zone_pos(d / 10) for d in range(0, 50)]
        assert xs == sorted(xs) and xs[0] == 0.0 and xs[-1] == 1.0
    finally:
        pygame.quit()


LONG_INCANTATION = "summon thunderous crimson stormclouds across austin skylines"  # 60, 7


def test_long_incantation_fits_a_spell_row_without_an_ellipsis():
    import pygame

    from magic_box.render.hud import LEFT_COL_W

    assert len(LONG_INCANTATION) == 60 and len(LONG_INCANTATION.split()) == 7
    cfg, theme, hud = _hud()
    try:
        h = cfg["render"]["hud"]
        row_w = 928 - LEFT_COL_W - h["pad_px"]  # the HUD rect at 1920x1080
        row_h = h["spell_row_h_px"] - 4
        spell = SpellView("bolt", "Bolt", LONG_INCANTATION, 20.0, False)
        font, lines = hud.incantation_lines(spell, row_w, row_h)
        text = " ".join(lines)
        assert "…" not in text and text == f"“{LONG_INCANTATION}”"
        f = theme.font(font)
        assert all(f.size(line)[0] <= row_w - 68 for line in lines)
        assert len(lines) * f.get_linesize() <= row_h + 2 - theme.font("tiny").get_linesize()
        short = SpellView("bolt", "Bolt", "zap", 20.0, False)
        assert hud.incantation_lines(short, row_w, row_h) == ("text", ["“zap”"])
    finally:
        pygame.quit()


def test_affordable_and_charged_spell():
    from magic_box.render.hud import affordable, charged_spell
    from tests.factories import make_full_player

    p = make_full_player(1)  # 25 mana: Bolt 20 ok, Chain 35 not
    assert affordable(p, p.spells[0]) and not affordable(p, p.spells[1])
    assert charged_spell(p) is None
    assert charged_spell(make_full_player(0)).id == "fireball"

import dataclasses

from magic_box.core.contracts import SpellView
from magic_box.render.hud import name_line, release_cue, spell_line
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

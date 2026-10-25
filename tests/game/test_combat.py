from pathlib import Path

import pytest

from magic_box.core.config import load_config
from magic_box.game.classes import class_ids, class_name
from magic_box.game.combat import damage, dist_mult, speed_mult
from magic_box.game.spells import load_spells
from tests.factories import pin_pre_venue_tuning

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")
pin_pre_venue_tuning(CFG)


@pytest.mark.parametrize(
    "dist,mult", [(1.2, 1.4), (2.8, 0.7), (2.0, 1.05), (1.0, 1.4), (3.5, 0.7), (0.0, 1.0)]
)
def test_dist_mult(dist, mult):
    assert dist_mult(dist, CFG) == pytest.approx(mult)


@pytest.mark.parametrize(
    "speed,mult", [(2.0, 1.0), (1.5, 0.75), (0.5, 0.6), (5.0, 1.8), (None, 1.0)]
)
def test_speed_mult(speed, mult):
    assert speed_mult(speed, CFG) == pytest.approx(mult)


def test_damage_combines_multipliers():
    assert damage(8, 2.0, 2.0, 2.0, 1.0, CFG) == pytest.approx(8.82)
    assert damage(10, None, 1.2, 2.8, 1.15, CFG) == pytest.approx(10 * 1.4 * 0.7 * 1.15)


def test_spell_table_from_config():
    spells = load_spells(CFG, "fire_mage")
    assert [s.id for s in spells] == ["fireball", "flame_wall", "inferno"]
    assert spells[1].release == "two_hand_push"
    assert spells[0].fallback[0] == "embers of the forty acres burn"
    assert class_ids(CFG) == ["fire_mage", "lightning_mage", "holy_knight"]
    assert class_name(CFG, "holy_knight") == "Holy Knight"

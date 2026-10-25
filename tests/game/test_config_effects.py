"""Validation of the game keys added for effects, boot, debounce and the lobby pick."""

import copy
from pathlib import Path

import pytest
import yaml

from magic_box.core.config import load_config, validate

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")


def spell(cfg, class_id, spell_id):
    return next(s for s in cfg["game"]["classes"][class_id]["spells"] if s["id"] == spell_id)


def problems(mutate):
    cfg = copy.deepcopy(CFG)
    mutate(cfg)
    return validate(cfg)


def test_shipped_config_is_valid():
    assert validate(CFG) == []


@pytest.mark.parametrize("value", [-1, "25", True, None])
def test_heal_hp_must_be_a_number_at_least_0(value):
    found = problems(lambda c: spell(c, "holy_knight", "heal").update(heal_hp=value))
    assert any("holy_knight.spells.heal.heal_hp" in p for p in found)


def test_heal_hp_0_is_fine():
    assert problems(lambda c: spell(c, "holy_knight", "heal").update(heal_hp=0)) == []


def test_chain_gap_is_required_with_more_than_one_hit():
    found = problems(lambda c: spell(c, "lightning_mage", "chain").pop("chain_gap_s"))
    assert any("lightning_mage.spells.chain.chain_gap_s" in p for p in found)


@pytest.mark.parametrize("value", [0, -0.25, "0.25", True])
def test_chain_gap_must_be_a_number_above_0(value):
    found = problems(lambda c: spell(c, "lightning_mage", "chain").update(chain_gap_s=value))
    assert any("chain.chain_gap_s" in p for p in found)


def test_single_hit_spells_need_no_chain_gap():
    assert "chain_gap_s" not in spell(CFG, "fire_mage", "fireball")


@pytest.mark.parametrize("value", [0, 1.5, True])
def test_hits_must_be_an_integer_at_least_1(value):
    found = problems(lambda c: spell(c, "lightning_mage", "chain").update(hits=value))
    assert any("chain.hits" in p for p in found)


def test_yaml_on_keyword_is_rejected_not_a_crash():
    [kw] = yaml.safe_load("[on]")  # YAML 1.1 reads on/no/yes as booleans
    found = problems(lambda c: c["game"]["classes"]["fire_mage"].update(keywords=[kw]))
    assert any("fire_mage.keywords" in p for p in found)


@pytest.mark.parametrize("keywords", [[], "fire", ["two words"], None])
def test_keywords_must_be_a_list_of_single_words(keywords):
    found = problems(lambda c: c["game"]["classes"]["fire_mage"].update(keywords=keywords))
    assert any("fire_mage.keywords" in p for p in found)


def test_keywords_must_be_unique_across_classes():
    found = problems(lambda c: c["game"]["classes"]["holy_knight"].update(keywords=["fire"]))
    assert any("holy_knight.keywords" in p for p in found)


@pytest.mark.parametrize("effect,effect_s", [("burn", 3), ("slow", 0), ("slow", None)])
def test_effect_kind_and_time(effect, effect_s):
    found = problems(
        lambda c: spell(c, "fire_mage", "inferno").update(effect=effect, effect_s=effect_s)
    )
    assert any("inferno.effect" in p for p in found)


@pytest.mark.parametrize(
    "key", ["boot_min_s", "hands_up_hold_s", "abandon_after_s", "release_grace_s"]
)
@pytest.mark.parametrize("value", [-1, True, "2"])
def test_game_numbers_are_numbers_at_least_0(key, value):
    assert any(f"game.{key}" in p for p in problems(lambda c: c["game"].update({key: value})))


def test_boot_min_must_not_exceed_boot_max():
    found = problems(lambda c: c["game"].update(boot_min_s=9.0, boot_max_s=8.0))
    assert any("game.boot_min_s" in p for p in found)

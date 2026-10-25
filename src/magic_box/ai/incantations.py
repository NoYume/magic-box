"""Incantation generation with config fallback (spec 2026-10-24 nikhil-pipeline, section 10).

Owner: Nikhil
"""

import json
import re
from collections.abc import Mapping

from rapidfuzz import fuzz
from rapidfuzz.utils import default_process

from magic_box.core.config import Config

_ALLOWED = re.compile(r"^[A-Za-z' ]+$")
_FENCE = re.compile(r"^```[A-Za-z]*\s*\n?(.*?)\n?```$", re.DOTALL)

_SYSTEM = (
    "You write short spoken incantations for a two-player magic duel game at HackTX "
    "in Austin, Texas. Reply with only JSON, no prose."
)


def _spells(classes: Mapping[int, str], cfg: Config, slot: int) -> list[Mapping]:
    return cfg["game"]["classes"][classes[slot]]["spells"]


def fallback_incantations(classes: Mapping[int, str], cfg: Config) -> dict[int, dict[str, str]]:
    """slot -> spell_id -> the fixed incantation from config."""
    return {
        slot: {s["id"]: s["fallback"][slot] for s in _spells(classes, cfg, slot)}
        for slot in classes
    }


def _normalize(text: object) -> str | None:
    if not isinstance(text, str):
        return None
    return " ".join(text.split())


def _valid(text: str | None, cfg: Config) -> bool:
    if not text or not _ALLOWED.match(text):
        return False
    ai = cfg["ai"]
    return ai["min_words"] <= len(text.split()) <= ai["max_words"]


def _slot_entries(raw: Mapping, slot: int) -> Mapping:
    entry = raw.get(str(slot), raw.get(slot))
    return entry if isinstance(entry, dict) else {}


def validate_incantations(
    raw: object, classes: Mapping[int, str], cfg: Config
) -> dict[int, dict[str, str]]:
    """Keep each valid generated entry; any failing or missing one takes its fallback."""
    fallback = fallback_incantations(classes, cfg)
    if not isinstance(raw, dict):
        return fallback
    max_sim = cfg["ai"]["max_cross_similarity"]
    out: dict[int, dict[str, str]] = {}
    for slot in sorted(classes):
        entries = _slot_entries(raw, slot)
        seen: list[str] = []
        final: dict[str, str] = {}
        for spell in _spells(classes, cfg, slot):
            sid = spell["id"]
            text = _normalize(entries.get(sid))
            ok = _valid(text, cfg)
            if ok:
                key = default_process(text)
                ok = key not in seen
                if ok and slot != 0 and 0 in out:
                    ok = all(fuzz.ratio(key, default_process(o)) < max_sim for o in out[0].values())
            if ok:
                seen.append(key)
                final[sid] = text
            else:
                final[sid] = fallback[slot][sid]
        out[slot] = final
    return out


def _strip_fence(reply: str) -> str:
    text = reply.strip()
    m = _FENCE.match(text)
    return m.group(1).strip() if m else text


def _prompt(classes: Mapping[int, str], names: Mapping[int, str], cfg: Config) -> str:
    ai = cfg["ai"]
    lines = []
    for slot in sorted(classes):
        lines.append(f'Player {slot}: name "{names.get(slot, "")}", class {classes[slot]}. Spells:')
        for s in _spells(classes, cfg, slot):
            lines.append(f"- {s['id']} ({s['name']}, damage {s['damage']})")
    lines += [
        "",
        'Reply with only JSON: {"0": {spell_id: incantation, ...}, "1": {spell_id: text, ...}}.',
        f"Each incantation is {ai['min_words']} to {ai['max_words']} words, using only letters, "
        "spaces and apostrophes (no digits or punctuation), and easy to say aloud.",
        "Give them Texas, Austin and HackTX flavor.",
        "The two players' sets must sound clearly different from each other.",
    ]
    return "\n".join(lines)


def generate_incantations(
    client, classes: Mapping[int, str], names: Mapping[int, str], cfg: Config
) -> dict[int, dict[str, str]]:
    """slot -> spell_id -> text. Any failure gives the full config fallback."""
    try:
        reply = client.complete(_SYSTEM, _prompt(classes, names, cfg))
        raw = json.loads(_strip_fence(reply))
    except Exception:
        return fallback_incantations(classes, cfg)
    return validate_incantations(raw, classes, cfg)

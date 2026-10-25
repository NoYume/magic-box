"""Duel chronicle with template fallback (spec 2026-10-24 nikhil-pipeline, section 10).

Owner: Nikhil
"""

import unicodedata
from collections.abc import Mapping, Sequence

from magic_box.ai.spark_client import log_fallback
from magic_box.core.config import Config
from magic_box.core.contracts import GameEvent

_SYSTEM = (
    "You are a bard chronicling a magic duel at HackTX in Austin, Texas. "
    "Write a short, vivid story in plain prose."
)


def _int_keys(mapping: object) -> dict[int, object]:
    if not isinstance(mapping, Mapping):
        return {}
    out: dict[int, object] = {}
    for k, v in mapping.items():
        try:
            out[int(k)] = v
        except (TypeError, ValueError):
            continue
    return out


def _num(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _spell_names(cfg: Config) -> dict[str, str]:
    return {s["id"]: s["name"] for c in cfg["game"]["classes"].values() for s in c["spells"]}


def summarize(events: Sequence[GameEvent], names: Mapping[int, str], cfg: Config) -> dict:
    """Counts and highlights from the event log."""
    spell_names = _spell_names(cfg)
    players = dict(names)
    class_names: dict[int, str] = {}
    casts = {0: 0, 1: 0}
    hits = {0: 0, 1: 0}
    dodges = {0: 0, 1: 0}
    hit_list: list[dict] = []
    dodge_list: list[dict] = []
    biggest = None
    winner = None
    reason = None
    hp: dict[int, object] = {}
    for e in events:
        d = e.data
        if e.kind == "match_start":
            players.update({k: str(v) for k, v in _int_keys(d.get("names")).items()})
            for slot, cid in _int_keys(d.get("classes")).items():
                cls = cfg["game"]["classes"].get(cid)
                class_names[slot] = cls["name"] if cls else str(cid)
        elif e.kind == "cast" and e.slot in casts:
            casts[e.slot] += 1
        elif e.kind == "hit" and e.slot in hits:
            hits[e.slot] += 1
            hit = {
                "attacker": e.slot,
                "spell": spell_names.get(str(d.get("spell_id")), str(d.get("spell_id"))),
                "damage": _num(d.get("damage")),
            }
            hit_list.append(hit)
            if biggest is None or hit["damage"] > biggest["damage"]:
                biggest = hit
        elif e.kind == "dodge" and e.slot in dodges:
            dodges[e.slot] += 1
            dodge_list.append({"defender": e.slot, "dodge": d.get("dodge")})
        elif e.kind == "match_end":
            winner = d.get("winner")
            try:
                winner = None if winner is None else int(winner)
            except (TypeError, ValueError):
                winner = None
            reason = d.get("reason")
            hp = _int_keys(d.get("hp"))
    return {
        "names": players,
        "classes": class_names,
        "casts": casts,
        "hits": hits,
        "dodges": dodges,
        "hit_list": hit_list,
        "dodge_list": dodge_list,
        "biggest_hit": biggest,
        "winner": winner,
        "reason": reason,
        "hp": hp,
    }


def _label(s: dict, slot: int) -> str:
    name = s["names"].get(slot, f"Player {slot + 1}")
    return f"{name} the {s['classes'][slot]}" if slot in s["classes"] else name


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def _ending(s: dict) -> str:
    winner = s["winner"]
    if winner is None:
        return "The duel ended in a draw."
    name = s["names"].get(winner, f"Player {winner + 1}")
    if s["reason"] == "ko":
        return f"{name} won, and the rival was knocked out."
    return f"{name} won when time ran out."


def template_chronicle(events: Sequence[GameEvent], names: Mapping[int, str], cfg: Config) -> str:
    """Two to four sentences from the log. Never raises on an empty log."""
    s = summarize(events, names, cfg)
    sentences = [f"{_label(s, 0)} faced {_label(s, 1)} in a duel under the Texas sky."]
    p0, p1 = (s["names"].get(i, f"Player {i + 1}") for i in (0, 1))
    c, h = s["casts"], s["hits"]
    sentences.append(
        f"{p0} cast {_plural(c[0], 'spell')} and landed {_plural(h[0], 'hit')}, "
        f"while {p1} cast {_plural(c[1], 'spell')} and landed {_plural(h[1], 'hit')}."
    )
    parts = []
    big = s["biggest_hit"]
    if big:
        who = s["names"].get(big["attacker"], f"Player {big['attacker'] + 1}")
        parts.append(f"the biggest blow was {who}'s {big['spell']} for {big['damage']} damage")
    if sum(s["dodges"].values()):
        parts.append(
            f"{p0} dodged {_plural(s['dodges'][0], 'attack')} and "
            f"{p1} dodged {_plural(s['dodges'][1], 'attack')}"
        )
    if parts:
        text = ", and ".join(parts)
        sentences.append(text[0].upper() + text[1:] + ".")
    sentences.append(_ending(s))
    return " ".join(sentences)


def _user_prompt(s: dict, cfg: Config) -> str:
    max_words = cfg["ai"]["chronicle_max_words"]
    lines = [f"Players: {_label(s, 0)} (slot 0) versus {_label(s, 1)} (slot 1)."]
    for slot in (0, 1):
        n = s["names"].get(slot, f"Player {slot + 1}")
        lines.append(
            f"{n}: {s['casts'][slot]} casts, {s['hits'][slot]} hits, {s['dodges'][slot]} dodges."
        )
    for h in s["hit_list"]:
        lines.append(
            f"Hit by {s['names'].get(h['attacker'])}: {h['spell']} for {h['damage']} damage."
        )
    for dd in s["dodge_list"]:
        lines.append(f"{s['names'].get(dd['defender'])} dodged ({dd['dodge']}).")
    lines.append(f"Ending: {_ending(s)}")
    lines.append(
        f"Write the story of this duel in at most {max_words} words, using both players' names."
    )
    return "\n".join(lines)


def sanitize_chronicle(text: str, max_words: int) -> str:
    """One line of printable text, at most `max_words` words ("…" marks a cut).

    Whitespace runs become one space; other control and format characters (a NUL crashes
    pygame's font.render) are dropped.
    """
    kept = "".join(c for c in text if c.isspace() or unicodedata.category(c) not in ("Cc", "Cf"))
    words = kept.split()
    if len(words) > max_words:
        return " ".join(words[:max_words]) + "\u2026"
    return " ".join(words)


def write_chronicle(
    client, events: Sequence[GameEvent], names: Mapping[int, str], cfg: Config
) -> str:
    """Spark-written story, sanitized; an empty reply or any exception gives the template."""
    try:
        s = summarize(events, names, cfg)
        reply = client.complete(_SYSTEM, _user_prompt(s, cfg))
        text = sanitize_chronicle(reply, cfg["ai"]["chronicle_max_words"])
    except Exception as e:
        log_fallback("chronicle", e)
        return template_chronicle(events, names, cfg)
    return text or template_chronicle(events, names, cfg)

"""End-to-end fake matches: the real GameLoop, FakeSources, Intent, Engine and keyboard voice.

Each test is a generator script: it yields the keys held for the next tick and reads the
last drawn GameView between yields. Speech and mic status are injected as VoiceEvents
through the sources, as the voice process would deliver them. The clock is a fake 60 fps
clock, so nothing sleeps. One test draws through the real headless Window.

Owner: Daniel
"""

import copy
import random
from collections.abc import Callable, Iterator
from dataclasses import replace
from pathlib import Path

import pytest

from magic_box.ai.worker import AiWorker
from magic_box.core.config import load_config
from magic_box.core.contracts import GameEvent, GameView, VoiceEvent
from magic_box.game.engine import Engine
from magic_box.intent.fusion import Intent
from magic_box.pipeline.loop import GameLoop
from magic_box.pipeline.sources import FakeSources, KeyboardVoiceSource, ReplaySources
from magic_box.replay.record import SessionRecorder

ROOT = Path(__file__).resolve().parents[1]
BASE_CFG = load_config(ROOT / "config.yaml")
FPS = 60
DT = 1 / FPS
KEYS = BASE_CFG["keys"]["fake"]
SPELL_KEYS = BASE_CFG["keys"]["spells"]
RELEASE_KEY = {
    "push": "push",
    "two_hand_push": "two_hand_push",
    "arm_overhead": "hands_up",
    "hands_together": "hands_together",
}
BOTH_HANDS_UP = frozenset({KEYS[0]["hands_up"], KEYS[1]["hands_up"]})
NONE: frozenset[str] = frozenset()

Script = Callable[["Harness"], Iterator[frozenset[str]]]


def make_cfg(**game_overrides) -> dict:
    cfg = copy.deepcopy(BASE_CFG)
    cfg["ai"]["enabled"] = False  # template chronicle and config incantations, no network
    cfg["game"].update(game_overrides)
    return cfg


class FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start - DT

    def __call__(self) -> float:
        self.now += DT
        return self.now


class ListQueue:
    def __init__(self) -> None:
        self.items: list = []

    def put(self, item) -> None:
        self.items.append(item)


class Harness:
    """Drives one GameLoop from a script; collects views and events."""

    def __init__(self, cfg: dict, window=None, sources=None, recorder=None) -> None:
        self.cfg = cfg
        self.clock = FakeClock()
        self.window = window
        self.view: GameView | None = None
        self.views: list[GameView] = []
        self.events: list[GameEvent] = []
        self.event_ticks: list[int] = []  # tick index of each event
        self.tick = -1
        self.pending_voice: list[tuple[int, str, str, str | None, float]] = []
        self.gone: set[int] = set()
        self.voice_q = ListQueue()
        self.finished = False
        self._script: Iterator[frozenset[str]] | None = None
        self.loop = GameLoop(
            cfg,
            sources if sources is not None else _HarnessSources(self, FakeSources(cfg)),
            _HarnessDisplay(self),
            Intent(cfg),
            Engine(cfg),
            KeyboardVoiceSource(cfg),
            ai=AiWorker(cfg),
            voice_control=self.voice_q,
            clock=self.clock,
            recorder=recorder,
        )

    # -- script helpers ----------------------------------------------------

    @property
    def scene(self) -> str | None:
        return self.view.scene if self.view is not None else None

    @property
    def now(self) -> float:
        return self.clock.now

    def say(self, slot: int, text: str) -> None:
        self.pending_voice.append((slot, "transcript", text, None, 0.0))

    def mic(self, slot: int, status: str) -> None:
        self.pending_voice.append((slot, "status", status, None, 0.0))

    def incant(self, slot: int, spell_id: str, score: float = 90.0) -> None:
        self.pending_voice.append((slot, "incantation", f"<{spell_id}>", spell_id, score))

    def find(self, kind: str, slot: int | None = None, since: int = 0, **data) -> list[GameEvent]:
        return [
            e
            for e in self.events[since:]
            if e.kind == kind
            and (slot is None or e.slot == slot)
            and all(e.data.get(k) == v for k, v in data.items())
        ]

    def player(self, slot: int):
        assert self.view is not None
        return self.view.players[slot]

    def run(self, script: Script, max_s: float = 120.0) -> "Harness":
        self._script = script(self)
        self.loop.run(max_ticks=int(max_s * FPS))
        assert self.finished, f"script did not finish in {max_s} s (scene {self.scene})"
        return self

    # -- loop hooks --------------------------------------------------------

    def _pump(self) -> tuple[frozenset[str], bool]:
        assert self._script is not None
        try:
            return frozenset(next(self._script)), False
        except StopIteration:
            self.finished = True
            return NONE, True

    def _draw(self, view: GameView, frame, states, fps, dropped=0) -> None:
        self.tick += 1
        self.view = view
        self.views.append(view)
        self.events += view.events
        self.event_ticks += [self.tick] * len(view.events)
        if self.window is not None:
            self.window.draw(view, frame, states, fps, dropped)


class _HarnessDisplay:
    def __init__(self, h: Harness) -> None:
        self.h = h

    def pump(self):
        return self.h._pump()

    def tick(self) -> float:
        return DT

    def draw(self, view, frame, states, fps, dropped=0) -> None:
        self.h._draw(view, frame, states, fps, dropped)

    def close(self) -> None:
        pass


class _HarnessSources:
    """FakeSources plus injected VoiceEvents and players who left the camera."""

    def __init__(self, h: Harness, inner: FakeSources) -> None:
        self.h, self.inner = h, inner

    def poll(self, keys, now, dt):
        got = self.inner.poll(keys, now, dt)
        voice = [VoiceEvent(s, now, k, text, sp, sc) for s, k, text, sp, sc in self.h.pending_voice]
        self.h.pending_voice.clear()
        states = [s for s in got.states if s.slot not in self.h.gone]
        return replace(got, states=states, voice=got.voice + voice)

    def close(self) -> None:
        pass


# -- reusable script pieces --------------------------------------------------


def hold(keys=NONE, seconds: float = 0.0) -> Iterator[frozenset[str]]:
    for _ in range(max(round(seconds * FPS), 1)):
        yield frozenset(keys)


def until(h: Harness, cond, keys=NONE, max_s: float = 40.0) -> Iterator[frozenset[str]]:
    for _ in range(int(max_s * FPS)):
        if h.view is not None and cond(h):
            return
        yield frozenset(keys)
    raise AssertionError(f"condition not met in {max_s} s (scene {h.scene})")


def until_scene(h: Harness, scene: str, keys=NONE, max_s: float = 40.0):
    yield from until(h, lambda h: h.scene == scene, keys, max_s)


def tap(*keys: str, ticks: int = 1) -> Iterator[frozenset[str]]:
    yield from hold(frozenset(keys), ticks / FPS)
    yield NONE


def to_fight(h: Harness, speech=()) -> Iterator[frozenset[str]]:
    """Boot, lobby (speech said, both hands up), loading, fight."""
    yield from until_scene(h, "lobby")
    for slot, text in speech:
        h.say(slot, text)
        yield NONE
    yield from until_scene(h, "loading", BOTH_HANDS_UP)
    yield from until_scene(h, "fight")


def cast(h: Harness, slot: int, spell_id: str) -> Iterator[frozenset[str]]:
    """Charge `spell_id` with its keyboard key, then release it with its gesture."""
    spells = [s.id for s in h.player(slot).spells]
    release = next(s.release for s in h.player(slot).spells if s.id == spell_id)
    yield from tap(SPELL_KEYS[slot][spells.index(spell_id)])
    yield from tap(KEYS[slot][RELEASE_KEY[release]], ticks=3)


def wait_for(h: Harness, kind: str, since: int, max_s: float = 4.0, **match):
    yield from until(h, lambda h: h.find(kind, since=since, **match), max_s=max_s)


# -- tests --------------------------------------------------------------------


def test_full_flow_two_matches_through_the_real_window():
    """Boot, names and classes, a KO match, victory, the lobby edge trigger, a second match."""
    from magic_box.render.window import Window

    cfg = make_cfg()
    window = Window(cfg, headless=True)
    g = cfg["game"]
    marks: dict[str, float] = {}

    def script(h: Harness):
        yield from until_scene(h, "lobby")
        marks["lobby"] = h.now
        assert {c.name: c.ok for c in h.view.checks}["camera"] is True
        h.say(0, "hi, my name is Ada, fire")
        h.say(1, "call me Bob")
        yield NONE
        h.say(1, "knight")
        yield NONE
        yield from hold(NONE, 0.1)
        assert [(p.name, p.class_id) for p in h.view.players] == [
            ("Ada", "fire_mage"),
            ("Bob", "holy_knight"),
        ]
        yield from until_scene(h, "loading", BOTH_HANDS_UP)
        marks["loading"] = h.now
        assert h.view.timer_s is None  # no countdown before the incantations arrive
        yield NONE
        assert h.view.timer_s == pytest.approx(max(g["loading_min_s"], g["loading_read_s"]))
        yield from until_scene(h, "fight")
        marks["fight"] = h.now
        incs = {s.id: s.incantation for s in h.player(0).spells}
        assert all(incs.values()), incs
        # Fireball then Inferno: 34.2 + 66.6 at the fake 3 m/s push is a KO.
        n = len(h.events)
        yield from cast(h, 0, "fireball")
        yield from wait_for(h, "hit", n, spell_id="fireball")
        yield from cast(h, 0, "inferno")
        yield from wait_for(h, "ko", n)
        marks["ko"] = h.now
        assert h.scene == "fight" and h.view.winner_slot == 0
        yield from until_scene(h, "victory")
        marks["victory"] = h.now
        assert h.view.banner == "ADA WINS" and h.view.winner_slot == 0
        yield NONE  # the chronicle job is started on entering victory and shows a tick later
        assert h.view.chronicle  # template chronicle (AI off)
        assert h.player(0).stats["casts"] == 2 and h.player(0).stats["hits"] == 2
        # Hands up after victory_min_s: back to the lobby; held hands don't start match 2.
        yield from until_scene(h, "lobby", BOTH_HANDS_UP, max_s=g["victory_min_s"] + 2)
        marks["lobby2"] = h.now
        yield from hold(BOTH_HANDS_UP, 2.0)
        assert h.scene == "lobby"
        assert [(p.name, p.class_id) for p in h.view.players] == [
            ("Ada", "fire_mage"),
            ("Bob", "holy_knight"),
        ]
        yield from hold(NONE, 0.5)
        yield from until_scene(h, "loading", BOTH_HANDS_UP, max_s=2)
        yield from until_scene(h, "fight")
        assert [p.hp for p in h.view.players] == [g["hp_max"]] * 2
        assert h.player(1).class_id == "holy_knight"
        n = len(h.events)
        yield from tap(KEYS[1]["push"])
        yield from wait_for(h, "hit", n, spell_id="basic", slot=1)

    try:
        h = Harness(cfg, window=window).run(script)
    finally:
        window.close()
    scenes = [v.scene for v in h.views]
    assert scenes[0] == "boot"
    assert marks["lobby"] - 1000.0 == pytest.approx(g["boot_min_s"], abs=3 * DT)
    # AI off: the fallback incantations arrive on the second loading tick.
    loading_s = max(g["loading_min_s"], g["loading_read_s"] + DT)
    assert marks["fight"] - marks["loading"] == pytest.approx(loading_s, abs=2 * DT)
    assert marks["victory"] - marks["ko"] == pytest.approx(g["ko_hold_s"], abs=2 * DT)
    assert marks["lobby2"] - marks["victory"] == pytest.approx(g["victory_min_s"], abs=0.5)
    assert len(h.find("match_start")) == 2
    assert h.find("match_end")[0].data["reason"] == "ko"
    # Voice got transcript mode in the lobby and each class's incantations in the fight.
    modes = [(c.mode, sorted(c.incantations.get(0, {}))) for c in h.voice_q.items]
    assert modes[:2] == [("transcript", []), ("incantation", ["fireball", "flame_wall", "inferno"])]


CLASS_WORDS = {"fire_mage": "fire", "lightning_mage": "lightning", "holy_knight": "holy"}
EVERY_SPELL = [
    (cid, s["id"]) for cid, c in BASE_CFG["game"]["classes"].items() for s in c["spells"]
]


@pytest.mark.parametrize(("class_id", "spell_id"), EVERY_SPELL)
def test_every_spell_of_every_class(class_id, spell_id):
    cfg = make_cfg()
    spell = next(s for s in cfg["game"]["classes"][class_id]["spells"] if s["id"] == spell_id)
    out: dict = {}

    def script(h: Harness):
        yield from to_fight(h, [(0, CLASS_WORDS[class_id]), (1, "lightning")])
        assert h.player(0).class_id == class_id
        if spell.get("heal_hp"):
            n = len(h.events)
            yield from tap(KEYS[1]["push"])  # take a hit first so the heal shows
            yield from wait_for(h, "hit", n, slot=1)
        out["hp0"], out["hp1"] = h.player(0).hp, h.player(1).hp
        n = len(h.events)
        yield from cast(h, 0, spell_id)
        yield from wait_for(h, "cast", n, slot=0, spell_id=spell_id, max_s=0.5)
        out["mana_after_cast"] = h.player(0).mana
        out["since"] = n
        yield from hold(NONE, spell["travel_s"] + spell.get("chain_gap_s", 0) * 3 + 0.3)

    h = Harness(cfg).run(script)
    n = out["since"]
    # The cost is spent at the charge; a few ticks of regen follow before the cast is seen.
    assert out["mana_after_cast"] <= cfg["game"]["mana_max"] - spell["cost"] + 3.0
    hits = h.find("hit", slot=0, since=n, spell_id=spell_id)
    buffs = h.find("buff", slot=0, since=n, spell_id=spell_id)
    if spell["damage"] > 0:
        assert len(hits) == spell.get("hits", 1)
        assert all(e.data["damage"] > 0 and e.data["target"] == 1 for e in hits)
        assert h.player(1).hp < out["hp1"]
    effect = spell.get("effect")
    if effect in ("shield", "empowered"):
        assert [(b.data["effect"], b.data["target"]) for b in buffs] == [(effect, 0)]
        assert not hits
    elif effect in ("mana_slow", "slow"):
        assert [(b.data["effect"], b.data["target"]) for b in buffs] == [(effect, 1)]
        assert len(hits) == 1
    if spell.get("heal_hp"):
        heal = h.find("heal", slot=0, since=n, spell_id=spell_id)
        assert len(heal) == 1 and heal[0].data["amount"] > 0
        assert h.player(0).hp > out["hp0"]


@pytest.mark.parametrize("dodge", ["duck", "step"])
def test_dodge_in_the_window_avoids_a_fireball(dodge):
    cfg = make_cfg()
    window = cfg["game"]["dodge_window_s"]
    travel = cfg["game"]["classes"]["fire_mage"]["spells"][0]["travel_s"]
    # A step is reported once the player has moved dodge_step_m, so it starts that much earlier.
    step_s = cfg["intent"]["dodge_step_m"] / cfg["fake"]["move_speed_mps"]
    lead = step_s if dodge == "step" else 0.0

    def script(h: Harness):
        yield from to_fight(h)
        n = len(h.events)
        yield from cast(h, 0, "fireball")
        yield from wait_for(h, "cast", n, spell_id="fireball", max_s=0.5)
        yield from hold(NONE, travel - window / 2 - lead - 4 * DT)  # mid-window
        if dodge == "duck":
            yield from tap(KEYS[1]["duck"], ticks=10)
        else:
            yield from hold({KEYS[1]["left"]}, step_s + 3 * DT)
        yield from hold(NONE, 1.0)
        out["n"] = n

    out: dict = {}
    h = Harness(cfg).run(script)
    assert [e.data["dodge"] for e in h.find("dodge", slot=1, since=out["n"])] == [dodge]
    assert not h.find("hit", since=out["n"])
    assert h.player(1).hp == cfg["game"]["hp_max"]
    assert h.player(1).stats["dodges"] == 1


def test_flame_wall_blocks_the_next_hit():
    cfg = make_cfg()

    def script(h: Harness):
        yield from to_fight(h)  # P1 fire_mage, P2 lightning_mage (defaults)
        yield from cast(h, 0, "flame_wall")
        assert [e.kind for e in h.player(0).effects] == ["shield"]
        out["n"] = len(h.events)
        yield from cast(h, 1, "bolt")
        yield from hold(NONE, 1.5)

    out: dict = {}
    h = Harness(cfg).run(script)
    blocks = h.find("block", since=out["n"])
    assert [(b.slot, b.data["spell_id"], b.data["attacker"]) for b in blocks] == [(0, "bolt", 1)]
    assert not h.find("hit", since=out["n"])
    assert h.player(0).hp == cfg["game"]["hp_max"]
    assert h.player(0).effects == ()  # the shield is used up
    assert h.player(0).stats["blocks"] == 1


@pytest.mark.parametrize("ducks", [1, 3])
def test_chain_needs_one_dodge_per_bolt(ducks):
    cfg = make_cfg()
    chain = cfg["game"]["classes"]["lightning_mage"]["spells"][1]
    gap, travel = chain["chain_gap_s"], chain["travel_s"]

    def script(h: Harness):
        yield from to_fight(h)
        out["n"] = n = len(h.events)
        yield from cast(h, 1, "chain")  # P2 is the lightning mage
        yield from wait_for(h, "cast", n, spell_id="chain", max_s=0.5)
        # Bolt k lands at travel + k * gap; duck once inside each bolt's window.
        yield from hold(NONE, travel - 0.15 - 4 * DT)
        for _ in range(ducks):
            yield from tap(KEYS[0]["duck"], ticks=3)
            yield from hold(NONE, gap - 4 * DT)
        yield from hold(NONE, 1.0)

    out: dict = {}
    h = Harness(cfg).run(script)
    n = out["n"]
    hits = h.find("hit", slot=1, since=n, spell_id="chain")
    assert len(h.find("dodge", slot=0, since=n)) == ducks
    assert len(hits) == chain["hits"] - ducks
    ticks = [h.event_ticks[h.events.index(e)] for e in hits]
    assert all(abs(b - a - gap * FPS) <= 1 for a, b in zip(ticks, ticks[1:], strict=False))


def test_ko_holds_the_fight_for_ko_hold_s():
    cfg = make_cfg()
    hold_s = cfg["game"]["ko_hold_s"]

    def script(h: Harness):
        yield from to_fight(h, [(0, "my name is Ada")])
        n = len(h.events)
        yield from cast(h, 0, "fireball")
        yield from wait_for(h, "hit", n)
        yield from cast(h, 0, "inferno")
        yield from wait_for(h, "ko", n)
        ko_view = h.view
        assert ko_view.scene == "fight" and {e.kind for e in ko_view.events} >= {"ko", "match_end"}
        frozen = [(p.hp, p.mana) for p in h.view.players]
        timer = h.view.timer_s
        # Inputs during the hold change nothing.
        yield from cast(h, 1, "bolt")
        yield from until_scene(h, "victory", max_s=hold_s + 0.5)
        before = h.views[-2]
        assert before.scene == "fight" and before.winner_slot == 0
        assert [(p.hp, p.mana) for p in before.players] == frozen and before.timer_s == timer
        assert h.view.banner == "ADA WINS"
        out["ko_tick"] = h.views.index(ko_view)

    out: dict = {}
    h = Harness(cfg).run(script)
    victory_tick = next(i for i, v in enumerate(h.views) if v.scene == "victory")
    assert victory_tick - out["ko_tick"] == pytest.approx(hold_s * FPS, abs=2)
    assert len(h.find("ko")) == 1 and len(h.find("match_end")) == 1
    assert not h.find("cast", slot=1)


@pytest.mark.parametrize(
    ("p2_hits", "banner", "winner"), [(True, "P2 WINS", 1), (False, "DRAW", None)]
)
def test_time_out(p2_hits, banner, winner):
    cfg = make_cfg(round_s=3)

    def script(h: Harness):
        yield from to_fight(h)
        if p2_hits:
            yield from tap(KEYS[1]["push"])
        yield from until_scene(h, "victory", max_s=4)

    h = Harness(cfg).run(script)
    end = h.find("match_end")
    assert [(e.data["reason"], e.data["winner"]) for e in end] == [("time", winner)]
    end_tick = h.event_ticks[h.events.index(end[0])]
    assert h.views[end_tick].scene == "victory"  # no hold after a time-out
    assert h.view.banner == banner and h.view.winner_slot == winner


@pytest.mark.parametrize(
    ("leave", "winner", "banner"), [({1}, 0, "P1 WINS"), ({0, 1}, None, "DRAW")]
)
def test_abandon_after_a_long_pause(leave, winner, banner):
    cfg = make_cfg()
    g = cfg["game"]

    def script(h: Harness):
        yield from to_fight(h)
        h.gone |= leave
        out["left"] = h.now
        yield from until(
            h, lambda h: h.view.banner == "STEP INTO VIEW", max_s=g["pause_after_s"] + 1
        )
        timer = h.view.timer_s
        yield from until_scene(h, "victory", max_s=g["pause_after_s"] + g["abandon_after_s"] + 2)
        out["victory"] = h.now
        assert h.views[-2].timer_s == timer  # the pause froze the round timer

    out: dict = {}
    h = Harness(cfg).run(script)
    end = h.find("match_end")
    assert [(e.data["reason"], e.data["winner"]) for e in end] == [("abandon", winner)]
    assert out["victory"] - out["left"] == pytest.approx(
        g["pause_after_s"] + g["abandon_after_s"], abs=0.5
    )
    assert h.view.banner == banner


def test_return_before_abandon_resumes_the_match():
    cfg = make_cfg()

    def script(h: Harness):
        yield from to_fight(h)
        h.gone.add(1)
        yield from until(h, lambda h: h.view.banner == "STEP INTO VIEW", max_s=4)
        yield from hold(NONE, 5.0)
        h.gone.clear()
        yield from until(h, lambda h: h.view.banner != "STEP INTO VIEW", max_s=1)
        n = len(h.events)
        yield from tap(KEYS[0]["push"])
        yield from wait_for(h, "hit", n, slot=0)

    h = Harness(cfg).run(script)
    assert h.scene == "fight" and not h.find("match_end")


@pytest.mark.parametrize("mic", ["connected", None])
def test_push_just_before_a_late_charge_releases_the_spell(mic):
    """Live voice charges land ~0.4 s after speech; with a mic up the push waits for them."""
    cfg = make_cfg()
    grace = cfg["game"]["release_grace_s"]

    def script(h: Harness):
        if mic:
            h.mic(0, mic)
        yield from to_fight(h)
        assert h.player(0).mic_ok is bool(mic)
        out["n"] = len(h.events)
        yield from tap(KEYS[0]["push"])
        yield from hold(NONE, grace / 2)
        h.incant(0, "fireball", score=88.0)
        yield from hold(NONE, 2.5)

    out: dict = {}
    h = Harness(cfg).run(script)
    casts = [e.data["spell_id"] for e in h.find("cast", slot=0, since=out["n"])]
    if mic:
        assert casts == ["fireball"]
        assert h.find("hit", slot=0, spell_id="fireball")
        assert not any(s.charged for s in h.player(0).spells)
    else:
        assert casts == ["basic"]  # no mic: the push is a basic attack at once
        assert [s.id for s in h.player(0).spells if s.charged] == ["fireball"]


@pytest.mark.parametrize(
    ("spell_id", "key"), [("holy_light", "hands_up"), ("heal", "hands_together")]
)
def test_a_late_charge_releases_a_pose_already_held(spell_id, key):
    """A Holy Knight raises the arm while speaking; the voice charge lands after."""
    cfg = make_cfg()

    def script(h: Harness):
        h.mic(0, "connected")
        yield from to_fight(h, [(0, "holy")])
        out["n"] = len(h.events)
        yield from hold({KEYS[0][key]}, 0.3)
        h.incant(0, spell_id, score=92.0)
        yield from hold({KEYS[0][key]}, 0.3)
        yield from hold(NONE, 0.2)

    out: dict = {}
    h = Harness(cfg).run(script)
    assert [e.data["spell_id"] for e in h.find("cast", slot=0, since=out["n"])] == [spell_id]
    assert not any(s.charged for s in h.player(0).spells)


def test_mic_up_push_without_a_charge_is_a_basic_after_the_grace():
    cfg = make_cfg()
    grace = cfg["game"]["release_grace_s"]

    def script(h: Harness):
        h.mic(0, "connected")
        yield from to_fight(h)
        out["push"] = h.now
        out["n"] = n = len(h.events)
        yield from tap(KEYS[0]["push"])
        yield from wait_for(h, "cast", n, slot=0, max_s=grace + 0.5)
        out["cast"] = h.now
        yield from hold(NONE, 1.0)

    out: dict = {}
    h = Harness(cfg).run(script)
    assert [e.data["spell_id"] for e in h.find("cast", slot=0, since=out["n"])] == ["basic"]
    two_hand_s = cfg["intent"]["two_hand_window_s"]
    assert out["cast"] - out["push"] == pytest.approx(grace + two_hand_s, abs=3 * DT)


def _check_view(h: Harness, problems: list) -> None:
    g = h.cfg["game"]
    v = h.view
    for p in v.players:
        if not 0 <= p.hp <= g["hp_max"] or not -1e-9 <= p.mana <= g["mana_max"] + 1e-9:
            problems.append((h.tick, "hp/mana", p.slot, p.hp, p.mana))
        if p.charge_s < 0 or p.cooldown_s < 0 or sum(s.charged for s in p.spells) > 1:
            problems.append((h.tick, "charge", p.slot))
        if any(val < 0 for val in p.stats.values()) or any(e.remaining_s <= 0 for e in p.effects):
            problems.append((h.tick, "stats/effects", p.slot))
    if any(not 0 <= pr.progress <= 1 for pr in v.projectiles):
        problems.append((h.tick, "projectile"))


@pytest.mark.parametrize(("seed", "classes"), [(3, ("fire", "holy")), (7, ("lightning", "fire"))])
def test_random_fights_keep_the_view_consistent(seed, classes):
    """Random keys, late voice charges, mics and walk-offs; HP, mana, charges, stats, effects
    and projectiles stay in range every tick, and the match ends."""
    rng = random.Random(seed)
    pool = [KEYS[s][k] for s in (0, 1) for k in KEYS[s]] + [
        k for s in (0, 1) for k in SPELL_KEYS[s]
    ]
    problems: list = []

    def script(h: Harness):
        h.mic(0, "connected")
        yield from to_fight(h, [(0, classes[0]), (1, classes[1])])
        held: dict[str, int] = {}
        while h.scene == "fight":
            held |= {k: rng.randint(1, 20) for k in pool if rng.random() < 0.02}
            if rng.random() < 0.005:
                slot = rng.choice((0, 1))
                h.incant(slot, rng.choice(h.player(slot).spells).id, rng.uniform(80, 100))
            if rng.random() < 0.002:
                h.gone ^= {rng.choice((0, 1))}
            _check_view(h, problems)
            keys = frozenset(held)
            held = {k: n - 1 for k, n in held.items() if n > 1}
            yield keys
        _check_view(h, problems)

    h = Harness(make_cfg()).run(script, max_s=200)
    assert problems == []
    assert len(h.find("match_end")) == 1


def test_record_then_replay_plays_to_the_same_result(tmp_path):
    """A recorded fake match replays to the same casts, hits, dodges and ending."""
    cfg = make_cfg()
    session = tmp_path / "session"

    def script(h: Harness):
        yield from to_fight(h, [(0, "my name is Ada, fire"), (1, "knight")])
        n = len(h.events)
        yield from cast(h, 0, "fireball")
        yield from wait_for(h, "cast", n, spell_id="fireball", max_s=0.5)
        yield from hold(NONE, 1.2)
        yield from tap(KEYS[1]["duck"], ticks=8)  # dodges the fireball
        yield from cast(h, 1, "holy_light")
        yield from tap(KEYS[1]["push"])
        yield from hold(NONE, 1.0)
        yield from cast(h, 0, "fireball")
        yield from wait_for(h, "hit", n, spell_id="fireball")
        yield from cast(h, 0, "inferno")
        yield from wait_for(h, "ko", n, max_s=3)
        yield from until_scene(h, "victory")

    recorder = SessionRecorder(session, cfg, "fake")
    try:
        live = Harness(cfg, recorder=recorder).run(script)
    finally:
        recorder.close()

    def watch(h: Harness):
        yield from until_scene(h, "victory", max_s=60)

    replayed = Harness(cfg, sources=ReplaySources(session, cfg)).run(watch)

    def summary(h: Harness):
        keep = ("cast", "hit", "dodge", "block", "buff", "heal", "ko", "match_end")
        return [
            (e.kind, e.slot, e.data.get("spell_id"), e.data.get("damage"), e.data.get("winner"))
            for e in h.events
            if e.kind in keep
        ]

    assert summary(replayed) == summary(live)
    assert [p.name for p in replayed.view.players] == ["Ada", "P2"]
    assert replayed.view.banner == live.view.banner == "ADA WINS"
    assert {e.kind for e in live.events} >= {"dodge", "buff", "hit", "ko"}

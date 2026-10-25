import copy
from dataclasses import replace
from pathlib import Path

from magic_box.ai.worker import AiWorker
from magic_box.core.config import load_config
from magic_box.core.contracts import GameEvent, SpellView, VoiceEvent
from magic_box.game.engine import Engine
from magic_box.intent.fusion import Intent
from magic_box.pipeline.loop import GameLoop, latest_states
from magic_box.pipeline.sources import FakeSources, KeyboardVoiceSource
from tests.factories import make_state, make_view

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")


def test_latest_keeps_newest_per_slot():
    out = latest_states({}, [make_state(t=1.0), make_state(t=1.05)], now=1.1, stale_s=0.2)
    assert out[0].t == 1.05 and out[0].tracking_ok


def test_stalled_camera_marks_tracking_lost():
    fresh = latest_states({}, [make_state(t=1.0)], now=1.1, stale_s=0.2)
    stale = latest_states(fresh, [], now=1.3, stale_s=0.2)
    assert stale[0].tracking_ok is False and stale[0].root == fresh[0].root


class ScriptedDisplay:
    def __init__(self, script):
        self.script, self.draws, self.dropped = list(script), 0, []

    def pump(self):
        keys = self.script.pop(0) if self.script else frozenset()
        return frozenset(keys), False

    def tick(self):
        return 1 / 60

    def draw(self, view, frame, states, fps, dropped=0):
        self.draws += 1
        self.dropped.append(dropped)

    def close(self):
        pass


class SpyIntent(Intent):
    def __init__(self, cfg):
        super().__init__(cfg)
        self.voice = []

    def update(self, states, voice, now):
        self.voice += list(voice)
        return super().update(states, voice, now)


def test_loop_merges_keyboard_voice_from_second_tick():
    display, intent = ScriptedDisplay([set(), {"1"}, set()]), SpyIntent(CFG)
    loop = GameLoop(CFG, FakeSources(CFG), display, intent, Engine(CFG), KeyboardVoiceSource(CFG))
    assert loop.run(max_ticks=3) == 3
    assert [(e.slot, e.spell_id) for e in intent.voice] == [(0, "fireball")]
    assert display.draws == 3


def test_loop_forwards_dropped_count_to_display():
    class DroppySources(FakeSources):
        def poll(self, keys, now, dt):
            return replace(super().poll(keys, now, dt), dropped=7)

    display = ScriptedDisplay([])
    GameLoop(
        CFG, DroppySources(CFG), display, Intent(CFG), Engine(CFG), KeyboardVoiceSource(CFG)
    ).run(max_ticks=2)
    assert display.dropped == [7, 7]


class SceneEngine:
    """Returns scripted scenes (last one repeats) and records provide_* calls."""

    def __init__(self, scenes, events=None):
        self.scenes, self.events = list(scenes), events or {}
        self.tick, self.provided, self.mic = 0, [], []

    def step(self, actions, states, now):
        scene = self.scenes[min(self.tick, len(self.scenes) - 1)]
        events = [GameEvent(now, k, None, {}) for k in self.events.get(self.tick, [])]
        self.tick += 1
        return make_view(scene=scene), events

    def provide_incantations(self, incantations):
        self.provided.append(("incantations", incantations))

    def provide_chronicle(self, text):
        self.provided.append(("chronicle", text))

    def provide_mic_status(self, slot, ok):
        self.mic.append((slot, ok))

    def provide_camera_status(self, ok):
        self.camera = getattr(self, "camera", []) + [ok]

    def provide_check(self, name, ok, detail=""):
        self.checks = getattr(self, "checks", {}) | {name: (ok, detail)}


class FakeAi:
    def __init__(self, poll_results=()):
        self.poll_results, self.started, self.polls = list(poll_results), [], 0

    def start_incantations(self, classes, names, now):
        self.started.append(("incantations", dict(classes), dict(names)))

    def start_chronicle(self, events, names, now):
        self.started.append(("chronicle", [e.kind for e in events], dict(names)))

    def poll(self, now):
        i, self.polls = self.polls, self.polls + 1
        return self.poll_results[i] if i < len(self.poll_results) else []


class ListQueue:
    def __init__(self):
        self.items = []

    def put(self, item):
        self.items.append(item)


class FakeClock:
    def __init__(self, step):
        self.step, self.n = step, 0

    def __call__(self):
        t = self.n * self.step
        self.n += 1
        return t


class RecordingDisplay(ScriptedDisplay):
    def __init__(self, script):
        super().__init__(script)
        self.views = []

    def draw(self, view, frame, states, fps, dropped=0):
        super().draw(view, frame, states, fps, dropped)
        self.views.append(view)


def test_voice_configs_on_first_tick_and_scene_changes():
    q = ListQueue()
    engine = SceneEngine(["lobby", "lobby", "loading", "fight", "fight", "victory", "lobby"])
    GameLoop(
        CFG,
        FakeSources(CFG),
        ScriptedDisplay([]),
        Intent(CFG),
        engine,
        KeyboardVoiceSource(CFG),
        ai=FakeAi(),
        voice_control=q,
    ).run(max_ticks=7)
    assert [(c.mode, c.incantations) for c in q.items] == [
        ("transcript", {}),
        ("incantation", {0: {"fireball": "embers burn"}, 1: {"fireball": "embers burn"}}),
        ("transcript", {}),
    ]


def test_ai_jobs_on_loading_and_victory_and_results_delivered():
    ai = FakeAi(
        poll_results=[[], [], [("incantations", {0: {}, 1: {}})], [], [("chronicle", "A tale.")]]
    )
    engine = SceneEngine(
        ["lobby", "loading", "loading", "fight", "victory"], events={3: ["match_start", "hit"]}
    )
    GameLoop(
        CFG,
        FakeSources(CFG),
        ScriptedDisplay([]),
        Intent(CFG),
        engine,
        KeyboardVoiceSource(CFG),
        ai=ai,
    ).run(max_ticks=5)
    assert ai.started == [
        ("incantations", {0: "mage", 1: "mage"}, {0: "P1", 1: "P2"}),
        ("chronicle", ["match_start", "hit"], {0: "P1", 1: "P2"}),
    ]
    assert engine.provided == [("incantations", {0: {}, 1: {}}), ("chronicle", "A tale.")]


def test_status_events_reach_engine_and_intent():
    class StatusSources(FakeSources):
        def poll(self, keys, now, dt):
            got = super().poll(keys, now, dt)
            return replace(got, voice=[VoiceEvent(1, now, "status", "connected", None, 0.0)])

    engine, intent = SceneEngine(["lobby"]), SpyIntent(CFG)
    GameLoop(
        CFG, StatusSources(CFG), ScriptedDisplay([]), intent, engine, KeyboardVoiceSource(CFG)
    ).run(max_ticks=1)
    assert engine.mic == [(1, True)] and [e.kind for e in intent.voice] == ["status"]


def test_voice_status_resends_the_last_voice_config():
    """A restarted voice child starts in transcript mode; a status re-sends the config."""

    class StatusSources(FakeSources):
        def __init__(self, cfg):
            super().__init__(cfg)
            self.tick = 0

        def poll(self, keys, now, dt):
            got = super().poll(keys, now, dt)
            tick, self.tick = self.tick, self.tick + 1
            if tick in (0, 2):  # before any config, then mid-fight from both slots
                status = [VoiceEvent(s, now, "status", "connected", None, 0.0) for s in (0, 1)]
                got = replace(got, voice=status)
            return got

    q = ListQueue()
    GameLoop(
        CFG,
        StatusSources(CFG),
        ScriptedDisplay([]),
        Intent(CFG),
        SceneEngine(["lobby", "fight", "fight", "fight"]),
        KeyboardVoiceSource(CFG),
        voice_control=q,
    ).run(max_ticks=4)
    sets = {0: {"fireball": "embers burn"}, 1: {"fireball": "embers burn"}}
    assert [(c.mode, c.incantations) for c in q.items] == [
        ("transcript", {}),
        ("incantation", sets),
        ("incantation", sets),
    ]


def test_full_fake_match_reaches_a_hit():
    cfg = copy.deepcopy(CFG)
    cfg["ai"]["enabled"] = False
    k0 = cfg["keys"]["fake"]
    g = cfg["game"]
    boot_ticks = int(g["boot_max_s"] * 60) + 5  # covers boot with or without a camera report
    hold_ticks = int(g["hands_up_hold_s"] * 60) + 5
    script = (
        [set()] * boot_ticks
        + [{k0[0]["hands_up"], k0[1]["hands_up"]}] * hold_ticks
        + [set()] * 620
        + [{"1"}, set(), {k0[0]["push"]}]
        + [set()] * 150
    )
    display = RecordingDisplay(script)
    loop = GameLoop(
        cfg,
        FakeSources(cfg),
        display,
        Intent(cfg),
        Engine(cfg),
        KeyboardVoiceSource(cfg),
        ai=AiWorker(cfg),
        clock=FakeClock(1 / 60),
    )
    loop.run(max_ticks=len(script))
    scenes = [v.scene for v in display.views]
    assert scenes[0] == "boot" and "lobby" in scenes and "loading" in scenes
    assert scenes[-1] == "fight"
    assert display.views[-1].players[1].hp < cfg["game"]["hp_max"]


class SpyRecorder:
    def __init__(self):
        self.items = []

    def write_state(self, state):
        self.items.append(("state", state.slot))

    def write_voice(self, event):
        self.items.append(("voice", event.kind))

    def write_event(self, event):
        self.items.append(("event", event.kind))


def test_recorder_gets_states_voice_and_events():
    rec = SpyRecorder()
    display = ScriptedDisplay([set(), {"1"}])
    GameLoop(
        CFG,
        FakeSources(CFG),
        display,
        Intent(CFG),
        SceneEngine(["lobby", "lobby"], events={1: ["match_start"]}),
        KeyboardVoiceSource(CFG),
        recorder=rec,
    ).run(max_ticks=2)
    assert rec.items.count(("state", 0)) == 2 and ("event", "match_start") in rec.items
    assert ("voice", "incantation") in rec.items


class IncEngine(SceneEngine):
    """Spells show an empty incantation until provide_incantations is called."""

    def __init__(self, scenes):
        super().__init__(scenes)
        self.text = ""

    def provide_incantations(self, incantations):
        super().provide_incantations(incantations)
        self.text = "real words"

    def step(self, actions, states, now):
        view, events = super().step(actions, states, now)
        if view.scene == "lobby":
            self.text = ""  # a new match starts without incantations
        spell = SpellView("fireball", "Fireball", self.text, 10.0, False)
        players = tuple(replace(p, spells=(spell,)) for p in view.players)
        return replace(view, players=players), events


class QueueDisplay(ScriptedDisplay):
    """Records, per drawn frame, the scene and how many voice configs were sent so far."""

    def __init__(self, q):
        super().__init__([])
        self.q, self.log = q, []

    def draw(self, view, frame, states, fps, dropped=0):
        super().draw(view, frame, states, fps, dropped)
        self.log.append((view.scene, len(self.q.items)))


def _run_inc(scenes, poll_results, ticks):
    q = ListQueue()
    display = QueueDisplay(q)
    engine = IncEngine(scenes)
    GameLoop(
        CFG,
        FakeSources(CFG),
        display,
        Intent(CFG),
        engine,
        KeyboardVoiceSource(CFG),
        ai=FakeAi(poll_results=poll_results),
        voice_control=q,
    ).run(max_ticks=ticks)
    return q, display


def test_incantation_config_is_sent_in_loading_once_the_engine_has_them():
    scenes = ["lobby", "loading", "loading", "loading", "loading", "fight", "fight"]
    q, display = _run_inc(scenes, [[], [("incantations", {0: {}, 1: {}})]], 7)
    assert [c.mode for c in q.items] == ["transcript", "incantation"]
    assert q.items[1].incantations[0] == {"fireball": "real words"}
    sent_at = next(i for i, (_, n) in enumerate(display.log) if n == 2)
    assert display.log[sent_at][0] == "loading"  # in loading, not at the fight start


def test_stale_delivery_flag_does_not_leak_into_the_next_loading():
    # Loading ends on the tick after the hand-over, so the delivery flag is never consumed
    # there. The next match's loading must not send a config with empty incantations.
    scenes = ["lobby", "loading", "fight", "victory", "lobby", "loading", "loading"]
    q, _ = _run_inc(scenes, [[], [("incantations", {0: {}, 1: {}})]], 7)
    texts = [
        text
        for c in q.items
        if c.mode == "incantation"
        for spells in c.incantations.values()
        for text in spells.values()
    ]
    assert texts and all(texts)


def test_spark_is_skipped_when_the_network_check_failed():
    class OfflineAi(FakeAi):
        def __init__(self):
            super().__init__()
            self.offline = []

        def set_offline(self, offline):
            self.offline.append(offline)

    class FailedNet:
        network_ok = False

        def poll(self, seen_frame, camera_ok):
            pass

    ai = OfflineAi()
    GameLoop(
        CFG,
        FakeSources(CFG),
        ScriptedDisplay([]),
        Intent(CFG),
        SceneEngine(["lobby", "loading", "victory"]),
        KeyboardVoiceSource(CFG),
        ai=ai,
        boot_checks=FailedNet(),
    ).run(max_ticks=3)
    assert ai.offline == [True, True]

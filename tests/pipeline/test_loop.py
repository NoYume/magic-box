from pathlib import Path

from magic_box.core.config import load_config
from magic_box.core.contracts import VoiceConfig
from magic_box.game.engine import Engine
from magic_box.intent.fusion import Intent
from magic_box.pipeline.loop import GameLoop, latest_states
from magic_box.pipeline.sources import FakeSources, KeyboardVoiceSource
from tests.factories import make_state

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
        self.script, self.draws, self.dropped, self.views = list(script), 0, [], []

    def pump(self):
        keys = self.script.pop(0) if self.script else frozenset()
        return frozenset(keys), False

    def tick(self):
        return 1 / 60

    def draw(self, view, frame, states, fps, dropped=0):
        self.draws += 1
        self.dropped.append(dropped)
        self.views.append(view)

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


def test_loop_configures_lobby_transcripts_with_class_keywords():
    class SpyControlQueue:
        def __init__(self):
            self.items = []

        def put(self, item):
            self.items.append(item)

    control = SpyControlQueue()
    GameLoop(
        CFG,
        FakeSources(CFG),
        ScriptedDisplay([]),
        Intent(CFG),
        Engine(CFG),
        KeyboardVoiceSource(CFG),
        control_q=control,
    ).run(max_ticks=1)
    assert len(control.items) == 1
    config = control.items[0]
    assert isinstance(config, VoiceConfig) and config.mode == "transcript"
    assert set(config.incantations[0].values()) == {
        row["name"] for row in CFG["game"]["classes"].values()
    }


def test_loop_shows_camera_reconnecting_when_perception_is_down():
    display = ScriptedDisplay([])
    GameLoop(
        CFG,
        FakeSources(CFG),
        display,
        Intent(CFG),
        Engine(CFG),
        KeyboardVoiceSource(CFG),
        camera_ok=lambda: False,
    ).run(max_ticks=1)
    assert display.views[0].banner == "CAMERA RECONNECTING"


def test_loop_forwards_dropped_count_to_display():
    from dataclasses import replace

    class DroppySources(FakeSources):
        def poll(self, keys, now, dt):
            return replace(super().poll(keys, now, dt), dropped=7)

    display = ScriptedDisplay([])
    GameLoop(
        CFG, DroppySources(CFG), display, Intent(CFG), Engine(CFG), KeyboardVoiceSource(CFG)
    ).run(max_ticks=2)
    assert display.dropped == [7, 7]

import json
import time
from pathlib import Path

import pytest

from magic_box.core.config import load_config
from magic_box.core.contracts import GameEvent, VoiceEvent
from magic_box.replay.play import SessionPlayer
from magic_box.replay.record import SessionRecorder
from tests.factories import make_state

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")


def record(tmp_path):
    out = tmp_path / "s"
    rec = SessionRecorder(out, CFG, "fake")
    rec.write_state(make_state(0, t=100.0, cam_t=7.0, frame_idx=3))
    rec.write_state(make_state(1, t=100.5, cam_t=7.5, frame_idx=4))
    rec.write_voice(VoiceEvent(0, 100.2, "incantation", "x", "fireball", 90.0))
    rec.write_event(GameEvent(100.3, "cast", 0, {"spell_id": "fireball"}))
    rec.close()
    return out


def test_recorder_writes_files_and_meta(tmp_path):
    out = record(tmp_path)
    assert len((out / "states.jsonl").read_text().splitlines()) == 2
    assert len((out / "events.jsonl").read_text().splitlines()) == 1
    meta = json.loads((out / "meta.json").read_text())
    assert meta["version"] == 1 and meta["mode"] == "fake"
    assert meta["config"]["game"]["round_s"] == 90
    assert {"started_t", "started_wall"} <= set(meta)


def test_recorder_close_is_idempotent(tmp_path):
    rec = SessionRecorder(tmp_path / "s", CFG, "fake")
    rec.close()
    rec.close()


def test_replay_rebases_t_and_keeps_cam_t(tmp_path):
    player = SessionPlayer(record(tmp_path), CFG)
    states, voice, frame = player.poll(5.0)
    assert [(s.slot, s.t, s.cam_t) for s in states] == [(0, 5.0, 7.0)] and voice == []
    assert frame is not None and frame.frame_idx == 3
    states, voice, _ = player.poll(5.25)
    assert states == [] and [(v.spell_id, v.t) for v in voice] == [("fireball", pytest.approx(5.2))]
    states, _, _ = player.poll(6.0)
    assert [s.slot for s in states] == [1]
    assert player.poll(60.0) == ([], [], None)


def test_replay_frame_draws_silhouettes(tmp_path):
    _, _, frame = SessionPlayer(record(tmp_path), CFG).poll(5.0)
    x, y, w, h = make_state(0).bbox_px
    bg = tuple(reversed(CFG["render"]["background_rgb"]))
    assert tuple(frame.image[y + h // 2, x + w // 2, :3]) != bg


def test_missing_session_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        SessionPlayer(tmp_path / "nope", CFG)


def test_empty_states_is_valid_and_missing_voice_is_empty(tmp_path):
    out = tmp_path / "s"
    out.mkdir()
    (out / "states.jsonl").write_text("")
    assert SessionPlayer(out, CFG).poll(1.0) == ([], [], None)


def test_recorder_does_not_block_and_flushes_everything(tmp_path):
    rec = SessionRecorder(tmp_path / "s", CFG, "live")
    start = time.monotonic()
    for i in range(5000):
        rec.write_state(make_state(0, t=float(i)))
    assert time.monotonic() - start < 1.0
    rec.close()
    assert len((tmp_path / "s" / "states.jsonl").read_text().splitlines()) == 5000

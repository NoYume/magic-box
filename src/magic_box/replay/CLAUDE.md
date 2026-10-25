# replay

**Owner:** Nikhil

Stand-ins for the camera: keyboard-driven fake players, session recording and playback. Spec: `docs/superpowers/specs/2026-10-24-nikhil-pipeline-design.md` section 13.

## Inputs → Outputs
- `fake_input.FakePlayers.step(keys, now, dt)` turns pressed key names into two `PlayerState`s plus a synthetic BGRA numpy `Frame` (two silhouettes that follow fake root x and z). Includes the two-hand push key.
- `record.py` (`--record DIR`) writes a session directory: `states.jsonl`, `voice.jsonl`, `events.jsonl`, `meta.json` (contracts via `core/serde.py`). No video: the loop only enqueues objects and a daemon writer thread does all disk work.
- `play.py` (`--replay DIR`) feeds a session back with rebased timing and redraws silhouettes from the recorded states (`draw_silhouettes`). Events are not replayed (the engine regenerates them). A missing session makes `main.py` exit 2 with "replay: no session at DIR".

## Hard rules
- No `pygame`: keys arrive as a `frozenset` of key names from the loop. No `pyzed`. `cv2` only inside functions.
- Fake frames use numpy slicing only (no OpenCV), so they work everywhere.
- Fake players read keys, speeds and start positions from `cfg.keys.fake` and `cfg.fake`. Slot 0 starts at +x (image right).
- Replay rebases `t` and `cam_t` to the current clock; do not re-stamp otherwise.
- Never block the game loop; `poll` returns what is due now, and recording never touches the disk on the 60 fps path.

## Files
- `fake_input.py`: `FakePlayers`, `draw_silhouettes`.
- `record.py`: `SessionRecorder`.
- `play.py`: `SessionPlayer`.

## Test without the Jetson
```
uv run pytest tests/replay
uv run python -m magic_box --fake --record /tmp/session --max-ticks 300 --headless
uv run python -m magic_box --replay /tmp/session
```
Keys are listed in the root `CLAUDE.md` (P1: `a d w s f v c r t`; P2: `j l i k h m n y u`).

## Open TODOs
- Recordings carry no frames. If judges want real video of a replay, record SVO on the Jetson with `scripts/record_session.py`.
- `TODO(Nikhil)`: record a real match on the Jetson and replay it on a laptop to check the timing.

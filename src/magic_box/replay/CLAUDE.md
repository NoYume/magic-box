# replay

**Owner:** Nikhil

Stand-ins for the camera: keyboard-driven fake players, session recording and playback.

## Inputs → Outputs
- `fake_input.FakePlayers.step(keys, now, dt)` turns pressed key names into two `PlayerState`s plus a synthetic BGRA numpy `Frame` (two silhouettes that follow fake root x and z).
- `record.py` writes a session directory: `states.jsonl`, `voice.jsonl`, `events.jsonl`, `frames.mp4`, `meta.json` (contracts via `core/serde.py`).
- `play.py` feeds a session back with its original timing.

## Hard rules
- No `pygame`: keys arrive as a `frozenset` of key names from the loop. No `pyzed`. `cv2` only inside functions.
- Fake frames use numpy slicing only (no OpenCV), so they work everywhere.
- Fake players read keys, speeds and start positions from `cfg.keys.fake` and `cfg.fake`. Slot 0 starts at +x (image right).
- Replay uses the recorded `t` and `cam_t`; do not re-stamp with the current clock except to rebase.
- Never block the game loop; `poll` returns what is due now.

## Files
- `fake_input.py`: `FakePlayers` (working, tested).
- `record.py`: session recorder for contract streams, MP4 frames and metadata.
- `play.py`: timed session player.

## Test without the Jetson
```
uv run pytest tests/replay
uv run python -m magic_box --fake
```
Keys are listed in the root `CLAUDE.md` (P1: `a d w s f c r t`; P2: `j l i k h n y u`).

## Open TODOs
- Validate MP4 codec availability and camera/frame timing on the Jetson.
- Add a checked-in small hardware recording once one is available for regression tests.

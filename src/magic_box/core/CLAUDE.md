# core

**Owner:** Nikhil

The shared data contracts, JSON-lines serialization and config loading. Every other package depends on this one.

## Inputs → Outputs
- Defines the contracts from spec §7: `Push`, `PlayerState`, `VoiceEvent`, `Action`, `GameEvent`, `GameView`, `PlayerView`, `SpellView`, `ProjectileView`, `VoiceConfig`, `Frame`.
- `config.load_config(path)` reads `config.yaml`, deep-merges `config.local.yaml` over it and validates. It raises `ConfigError` on bad values.
- `serde` converts any contract to and from one JSON line (used by recording and replay).

## Hard rules
- Imports nothing from `magic_box` outside `core/`. No `pygame`, `pyzed`, `cv2` or `sounddevice`.
- A contract change needs a heads-up to every owner who produces or consumes it, and an update to the root `CLAUDE.md` in the same change.
- Contracts are frozen dataclasses. Meters and seconds. Camera frame is ZED `IMAGE` (+X right, +Y down, +Z away). Slot 0 = P1 = image right.
- `t` is `time.monotonic()` at publish; `cam_t` is only for velocities.
- Config keys are the single source of tunables. Add a key to `config.yaml` and to validation together.

## Files
- `contracts.py`: all cross-owner dataclasses and their allowed-value checks.
- `serde.py`: `to_json` / `from_json` round-trip every contract as one JSON line.
- `config.py`: `Config`, `deep_merge`, `validate`, `load_config`.
- `geometry.py`: `zone_for_distance` (uses `perception.zones`) and `project_point` (pinhole).

## Test without the Jetson
```
uv run pytest tests/core
```
No hardware needed. `tests/factories.py` builds sample contracts for tests.

## Open TODOs
- No `TODO(` markers in this package.
- Any new contract field must round-trip through `serde` (add a case to `tests/core/test_contracts.py`).

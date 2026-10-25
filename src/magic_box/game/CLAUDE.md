# game

**Owner:** Adetola

Pure game rules: classes, spells, HP and mana, charge and dodge windows, combat, scene flow. Draft mechanics: `docs/game-design.md`.

## Inputs → Outputs
- In: `Action` (from `intent/`), `provide_incantations()` and `provide_chronicle()` results from `ai/`.
- Out: `Engine.step(...)` returns a `GameView` (what render draws) plus `GameEvent`s (the match log used by the chronicle and recordings).

## Hard rules
- **Pure Python.** Never import `pygame`, `pyzed` or `cv2` (`tests/test_boundaries.py` fails the build).
- Never block: no network, no sleeping, no file I/O in `step`. Spark results arrive via `provide_*`.
- Every number (costs, damage, windows, HP, regen) is read from `cfg.game`; spell data lives in `config.yaml`. No hard-coded balance.
- Use `Action.t` and the tick time, not the wall clock. Distances are meters.
- The `GameView` contract is shared with render. Changing it needs a heads-up to Nikhil and a root `CLAUDE.md` update.

## Files
- `engine.py`: `Engine` facade (`step`, `provide_incantations`, `provide_chronicle`) and combat orchestration.
- `scenes.py`: scene state machine boot → lobby → loading → fight → victory.
- `state.py`: mutable match state (HP, mana, charges, buffs, projectiles in flight).
- `combat.py`: damage formula (spec Appendix A).
- `spells.py`: spell table loaded from config.
- `classes.py`: class ids and lookup from config.

## Test without the Jetson
```
uv run pytest tests/game
uv run python -m magic_box --fake
```
Fake mode feeds the engine no `Action`s yet: `Intent.update` in `intent/fusion.py` is a placeholder that returns `[]` (TODO Nikhil). Until it is implemented, iterate with the HUD and `GameView`, or a local stub that returns `Action`s. Spell keys (P1 `1 2 3`, P2 `8 9 0`) only reach the voice path.

## Open TODOs
- Hardware-tune the draft costs, damage, gestures, windows and distance multipliers.
- Lobby transcripts reach `Engine.accept_voice()` through the existing `VoiceEvent` contract; validate name/class recognition with both live microphones.
- "CAMERA RECONNECTING" still needs supervisor health exposed to `GameView`.

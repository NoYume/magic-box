# game

**Owner:** Adetola

Pure game rules: classes, spells, HP and mana, charge and dodge windows, combat, scene flow. Draft mechanics: `docs/game-design.md`.

**Thin engine (2026-10-24).** The files here were filled in by Nikhil so the whole pipeline plays end to end. They carry the docstring line `Thin placeholder rules (2026-10-24 phase); replace freely.` They are yours to replace; nothing outside `game/` depends on engine internals beyond the `Engine` facade and the `GameView` contract.

## Inputs → Outputs
- In: `Action`s (from `intent/`), the newest `PlayerState` per slot, and `provide_incantations()`, `provide_chronicle()` and `provide_mic_status(slot, ok)` from the loop.
- Out: `Engine.step(actions, states, now)` returns a `GameView` (what render draws) plus `GameEvent`s (the match log used by the chronicle and recordings).

## What the thin engine does
- Scene flow `lobby → loading → fight → victory → lobby` (it starts in `lobby`; there is no `boot`).
- Lobby: `speech` Actions set the player's name (`parse_name`, up to `name_max_chars`); both players raising hands starts the match. The start is edge-triggered: after a match the players must lower their hands, then raise them again (the first lobby at startup starts on the first both-hands-up tick). Names persist across matches.
- Loading: waits for the incantations from `ai/` (config fallback fills any gap), `loading_min_s` to `loading_max_s`.
- Fight: own match clock (starts at 0; `now` is only the timestamp on `GameEvent.t`). `round_s` round, mana regen, charge (`charge_window_s`), a release (push, two-hand push, arm overhead, hands together) fires the charged spell, a basic attack on an uncharged push. Damage is Appendix A (`combat.py`). The attacker's distance is the releasing Action's `dist` (else the last known). A dodge inside `dodge_window_s` of impact avoids the hit.
- Spells with 0 damage (Flame Wall, Static Field, Holy Light, Heal) spend mana, log a `cast` event and show a banner. Nothing more.
- Pause: if a player has been untracked for `pause_after_s`, everything freezes and the banner reads "STEP INTO VIEW".
- Victory: ends on KO or time-out. Back to the lobby when both raise hands after `victory_min_s`, or at `victory_max_s`. Hands still held up then keep the lobby open (names can change); lowering and raising them starts the next loading.

## Hard rules
- **Pure Python.** Never import `pygame`, `pyzed` or `cv2` (`tests/test_boundaries.py` fails the build).
- Never block: no network, no sleeping, no file I/O in `step`. Spark results arrive via `provide_*`.
- Every number (costs, damage, windows, HP, regen) is read from `cfg.game`; spell data lives in `config.yaml`. No hard-coded balance.
- Use `Action.t` and the tick time, not the wall clock. Distances are meters.
- The `GameView` contract is shared with render. Changing it needs a heads-up to Nikhil and a root `CLAUDE.md` update.

## Files
- `engine.py`: `Engine` facade (`step`, `provide_incantations`, `provide_chronicle`, `provide_mic_status`); builds the `GameView`.
- `scenes.py`: `SceneMachine` for lobby → loading → fight → victory; `parse_name`.
- `state.py`: `MatchState` (HP, mana, charges, cooldowns, projectiles in flight, round timer, banner, event log).
- `combat.py`: `speed_mult`, `dist_mult`, `damage` (spec Appendix A).
- `spells.py`: `SpellDef` and `load_spells` from config.
- `classes.py`: `class_ids`, `class_name` from config.

## Test without the Jetson
```
uv run pytest tests/game
uv run python -m magic_box --fake
```
In fake mode the whole match plays: raise hands (`r` + `y`), charge with the spell keys, push with `f` / `h`, two-hand spells with `v` / `m`.

## Open TODOs
- `TODO(Adetola)`: spell effects for 0-damage spells (Flame Wall block, Static Field slow, Holy Light buff, Heal; Chain hits once today).
- `TODO(Adetola)`: class pick (classes are fixed from `game.default_classes`) and the `boot` scene self-check.
- `TODO(Adetola)`: the "CAMERA RECONNECTING" banner (perception restarting) is not implemented.
- Open decisions (Adetola): final classes, spells, costs, gestures and numbers; scene flow and lobby interactions; `Push.speed` threshold vs peak (with Enoch).
- `game.charge_window_s` waits on the partial-latency measurement (Nikhil).

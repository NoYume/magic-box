# intent

**Owner:** Nikhil

Signal processing between inputs and rules. Turns `PlayerState` and `VoiceEvent` into `Action`s. No HP, mana or damage rules here. Spec: `docs/superpowers/specs/2026-10-24-nikhil-pipeline-design.md` section 7.

## Inputs → Outputs
- In: `PlayerState` stream (Enoch) and `VoiceEvent` (Nikhil), both drained by the loop each tick.
- Out: `Action` (`charge`, `push`, `pose`, `dodge`, `speech`) for `game/` (Adetola).
- A voice `incantation` becomes `charge`; a `transcript` becomes `speech` (`Action.text`); `PlayerState.push` becomes `push`; a rising edge of a pose flag becomes `pose`; a windowed step or duck becomes `dodge`. `status` events are not intent's business: the loop passes them to the engine.
- Charge, push, pose and dodge Actions carry `dist` (root Z; a charge uses the slot's last tracked root Z).

## Hard rules
- Pure Python on contracts. No `pygame`, `pyzed`, `cv2`, no I/O, no sleeping. Called from the game loop, so it must be fast.
- Time comes from `t` (`time.monotonic()`) on the contracts, never from the wall clock. Voice and push times are compared on that shared clock.
- Thresholds (`dodge_step_m`, `dodge_duck_m`, `dodge_lookback_s`, `two_hand_window_s`) come from `cfg.intent`. No game rules (cost, damage, cooldown) here.
- Skip states with `tracking_ok=False`.
- **Two-hand push:** a push is held up to `two_hand_window_s` (0.1 s), unless the other hand already crossed within the window (then it fires at once with `two_hand=True`). If the other hand's `wrist_vz <= -push_speed_mps` (inclusive) during the hold, it fires then with `two_hand=True`; a cross exactly at the deadline counts as single. A push state that arrives after a pending push's deadline releases the pending one first (stall safety).
- **Dodge:** step = |root.x minus any sample in the lookback window| >= `dodge_step_m`; duck = head.y rise >= `dodge_duck_m`; step wins when both fire.

## Files
- `fusion.py`: `Intent.update(states, voice, now)` fuses voice, push and pose into `Action`s, including the two-hand hold.
- `dodge.py`: `DodgeDetector.update(state)` returns `"step"`, `"duck"` or `None` over a lookback window.

## Test without the Jetson
Tests are in `tests/intent/` (driven by `tests/factories.py` states). To see it in the app:
```
uv run pytest tests/intent
uv run python -m magic_box --fake
```
Fake-mode keys produce pushes (`f`/`h`), two-hand pushes (`v`/`m`), ducks (`c`/`n`), poses (`r`,`t` / `y`,`u`) and spells (`1 2 3` / `8 9 0`).

## Rechecked 2026-10-25 against the overnight rulings
- `Push.speed` becomes the thrust's peak (Task 4), so a push can be reported after both hands crossed. Intent needs no change: the other hand's history covers `two_hand_window_s` and includes the push frame itself, so a hand still past the threshold then counts (`test_peak_speed_push_still_two_hand_when_the_other_hand_crossed_long_before`).
- Dodge thresholds (`dodge_step_m` 0.3, `dodge_duck_m` 0.25, `dodge_lookback_s` 0.4) are untouched by the rulings and still guesses. A step during a brief tracking loss still counts on re-acquire (the window is not cleared), which is what a fast dodge needs.
- A charge now lands about 0.4 s after the player stops speaking, and up to about +0.8 s for a held sub-perfect match (see `voice/CLAUDE.md`). The engine's `game.release_grace_s` (0.6 s, Task 1) holds an uncharged push that long for a charge; after that the push is a basic attack, and the charge waits `game.charge_window_s` (3.0 s) for the next release.

## Open TODOs
- `TODO(Nikhil)`: tune `two_hand_window_s` with real arms on the Jetson (0 removes the wait, but then only hands that cross on the same frame count).
- Tune the dodge thresholds on recordings (`--replay`).

# intent

**Owner:** Nikhil

Signal processing between inputs and rules. Turns `PlayerState` and `VoiceEvent` into `Action`s. No HP, mana or damage rules here.

## Inputs → Outputs
- In: `PlayerState` stream (Enoch) and `VoiceEvent` (Nikhil).
- Out: `Action` (`charge`, `push`, `pose`, `dodge`) for `game/` (Adetola).
- A voice match becomes `charge`; `PlayerState.push` becomes `push`; a rising edge of a pose flag becomes `pose`; a windowed step or duck becomes `dodge`.

## Hard rules
- Pure Python on contracts. No `pygame`, `pyzed`, `cv2`, no I/O, no sleeping. Called from the game loop, so it must be fast.
- Time comes from `t` (`time.monotonic()`) on the contracts, never from the wall clock. Voice and push times are compared on that shared clock.
- Thresholds (`dodge_step_m`, `dodge_duck_m`, `dodge_lookback_s`) come from `cfg.intent`. No game rules (cost, damage, cooldown) here.
- Skip states with `tracking_ok=False`.

## Files
- `fusion.py`: `Intent.update(...)` combines voice, push and pose into `Action`s. Placeholder emits nothing today.
- `dodge.py`: `DodgeDetector.update(state)` returns `"step"`, `"duck"` or `None` over a lookback window.

## Test without the Jetson
There is no `tests/intent/` yet; create it and drive the code with `tests/factories.py` states. Cover charge then push within the window, pose rising edges, step and duck. To see it in the app:
```
uv run python -m magic_box --fake
```
Fake-mode keys produce pushes (`f`/`h`), ducks (`c`/`n`), poses (`r`,`t` / `y`,`u`) and spells (`1 2 3` / `8 9 0`).

## Open TODOs
- `TODO(Nikhil)` in `fusion.py`: charge/push/pose/dodge fusion.
- `TODO(Nikhil)` in `dodge.py`: windowed step/duck detection.
- Open decision: size the charge window after measuring Muse partial-transcript latency (M4).

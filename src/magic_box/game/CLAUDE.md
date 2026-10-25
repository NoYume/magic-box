# game

**Owner:** Adetola

Pure game rules: classes, spells and their effects, HP and mana, charge and dodge windows, combat, scene flow. Draft mechanics: `docs/game-design.md`. The overnight beta (2026-10-25) filled in every spell effect, the voice class pick, the boot scene and the pause rules; numbers are still yours to tune.

## Inputs → Outputs
- In: `Action`s (from `intent/`), the newest `PlayerState` per slot, and from the loop: `provide_incantations()`, `provide_chronicle()`, `provide_mic_status(slot, ok)`, `provide_camera_status(ok)` and `provide_check(name, ok, detail)`.
- Out: `Engine.step(actions, states, now)` returns a `GameView` (what render draws) plus `GameEvent`s (the match log used by the chronicle and recordings). `GameView.events` repeats the same events.

## Scene flow
`boot → lobby → loading → fight → victory → lobby`
- **Boot** (first scene): `GameView.checks` lists `camera`, `mic P1`, `mic P2`, `network`, `api key` (unknown is not ok, detail `"checking"`), then any other names reported. `provide_check(name, ...)` sets any line; `provide_mic_status` fills the mics, and a later status with the same ok keeps its detail. `provide_camera_status` never makes the camera line ok: the loop reports ok before the first frame, so only `provide_check("camera", True)` (BootChecks: a frame was seen) does, and only that passes boot. `provide_camera_status(False)` marks the line `"no frames"` only while it isn't ok yet (perception dying at startup); after a frame was seen the line stays ok, and the CAMERA RECONNECTING banner and pause carry the live state. Boot goes to the lobby after `boot_min_s` once that camera line is ok, or at `boot_max_s` whatever the checks say. `timer_s` counts down to when boot will leave: `boot_min_s` once the camera line is ok, else `boot_max_s`; no banner.
- **Lobby:** a final transcript (`speech` Action) is parsed by `scenes.parse_lobby_speech` into a class and a name, either of which may be missing (then the current one stays). **Class:** a class keyword (`game.classes.<id>.keywords`: `fire`, `lightning`, `holy`, `knight`; whole words, the last one said wins) picks that class. **Name** (`parse_name`): after a name prefix found anywhere on word boundaries ("my name is", "my name's", "call me", "i am", "i'm"; the first wins), the following words up to the first class keyword, punctuation mark or stop word, at most `name_max_words` (2), then `name_max_chars`. With no prefix, the transcript is a name only if it is 1 or 2 words and none is a keyword or stop word. Stop words are `game.name_stop_words` (chatter such as ready, ok, hello, so, what, now). So "hi, my name is Ada, fire" sets Ada and Fire Mage, "Bob" sets Bob, "my name is knight" picks Holy Knight and keeps the name, and "so what do I do now", "this is cool" or "I'm ready" change nothing. Names and classes persist across matches. `PlayerView.heard` is the last transcript. Banner: `SAY NAME · SAY FIRE, LIGHTNING OR HOLY · HANDS UP` (built from the first keyword of each class; fits one line at 96 px on 1920 px).
- **Hands up** is debounced by `hands_up_hold_s` on both edges (`scenes.Hold`): it counts once held, and a one-frame drop doesn't lower it. `PlayerView.ready` shows the debounced value in lobby and victory. Both ready starts loading. The start is edge-triggered: after a match the players must lower their hands (held down), then raise them again. The first lobby after boot starts armed.
- **Loading:** waits for the incantations from `ai/` (config fallback fills any gap; `loading_max_s` forces the fallback). It lasts at least `loading_min_s` in all and at least `loading_read_s` (4.0) after the incantations arrive, so players can read the Spark ones (Spark takes 3.1-3.8 s). `timer_s` is None until they arrive (no countdown, render shows placeholders), then counts down to the later deadline. Incantations follow the picked class.
- **Fight:** own match clock (starts at 0; `now` is only the timestamp on `GameEvent.t`). `round_s` round, mana regen, charge (`charge_window_s`), a release (push, two-hand push, arm overhead, hands together) fires the charged spell, a basic attack on an uncharged push. Damage is Appendix A (`combat.py`). The attacker's distance is the releasing Action's `dist` (else the last known). A dodge removes the projectiles aimed at the dodger that are inside their `dodge_window_s`, but only the earliest one of each cast, so each Chain bolt needs its own dodge.
- **Release grace:** the Muse charge lands about 0.4 s (worst 0.6 s) after the player stops speaking, so a push with no charge, from a player whose mic is ok and who can afford a spell that push could release, is held for up to `release_grace_s` (0.6); out of mana it fires the basic attack at once. A charge arriving meanwhile whose release matches the held push (a plain push releases push spells; a two-hand push releases push and two-hand spells) fires that spell at once with the held push's speed, origin and dist. Otherwise the basic attack fires when the hold ends; a push held during the basic-attack cooldown can only release a spell, and is dropped when the hold ends. One push is held per player; a second one during the hold is ignored. Mic off (keyboard, fake mode) means no hold. The hold runs on the match clock (a pause freezes it) and is dropped when the match ends. Poses need no hold: a charge for a pose spell (arm overhead, hands together) that lands while that pose is already held (tracked) releases at once, so a player who raised the arm while speaking doesn't have to lower and raise it again.
- **KO hold:** after a KO the scene stays `fight` for `ko_hold_s` (2.5) so render can show the finishing blow (flash, damage number, K.O. overlay). The match is frozen: no actions, regen or timer, projectiles in flight are cleared at the end, and pause, abandon and camera logic don't run. `winner_slot` is already set. `ko` and `match_end` fire once, on the KO tick. Time-outs and abandons go to victory at once.
- **Victory:** on KO (after the hold), time-out or abandon. `winner_slot` (None for a draw). Back to the lobby when both hold hands up after `victory_min_s`, or at `victory_max_s`.

## Spell effects (config: per spell `effect` + `effect_s`, `heal_hp`, `hits` + `chain_gap_s`; multipliers under `game:`)
| Spell | Effect |
|---|---|
| Flame Wall | `shield` on the caster, 4 s: the next incoming hit (any projectile) is blocked (`block` event, no damage), then the shield ends. |
| Static Field | A 0-damage projectile; if it lands (not dodged or blocked) the target gets `mana_slow`, 5 s: mana regen x `mana_slow_mult` (0.25). |
| Inferno | 35 damage; if it lands the target gets `slow`, 3 s: their next charge window x `slow_charge_mult` (0.6); charging uses it up. |
| Holy Light | `empowered` on the caster, 6 s: anything they release meanwhile (spells and basic attacks) does x `empowered_mult` (1.5), fixed at release. |
| Heal | +25 HP on the caster, capped at `hp_max` (`heal` event with the HP actually gained). |
| Chain | 3 bolts of 7, launched `chain_gap_s` (0.25 s) apart. Each bolt needs its own dodge: one dodge avoids only the earliest bolt in its window. |

Rules: a spell is a projectile when it does damage or carries a hit effect (`mana_slow`, `slow`); otherwise it is instant and shows a `SPELL NAME!` banner. `shield` and `empowered` go on the caster at release, `mana_slow` and `slow` on the target at impact (not on a knockout blow). Re-applying an effect keeps the longer timer. Effect timers run on the match clock, so a pause freezes them.

Events: `buff` (slot = caster; data `spell_id`, `effect`, `target`, `duration_s`), `heal` (slot = caster; `spell_id`, `amount`, `hp`), `block` (slot = defender; `spell_id`, `attacker`), plus `cast`, `hit` (Static Field hits for 0), `dodge`, `ko`, `match_end` (reason `ko`, `time` or `abandon`).

## View fields
`PlayerView.effects` (fight only, `EFFECT_KINDS` order), `charge_s` and `cooldown_s` (fight only), `stats` (fight and victory; `{}` elsewhere): `damage` dealt (overkill not counted, 1 dp), `hits` landed, `casts` (charged spells, not basic attacks), `dodges` (projectiles dodged), `blocks`, `heals` (heal casts), `best_push_mps`. `GameView.classes` lists every class in every scene; `checks` is filled in every scene.

## Pauses
- **Tracking:** a player untracked for `pause_after_s` freezes the fight ("STEP INTO VIEW"). A pause that lasts `abandon_after_s` ends the match: the player still tracked wins, a draw if both are gone (`match_end` reason `abandon`).
- **Camera:** while `provide_camera_status(False)`, the banner is "CAMERA RECONNECTING" (lobby, loading and fight) and the fight freezes like a pause. It never abandons. When frames return, anyone not tracked yet pauses the fight at once ("STEP INTO VIEW") until they are seen again, and the abandon clock starts from the recovery. Until the loop reports, the camera counts as fine for this banner (but not for the boot check).

## Hard rules
- **Pure Python.** Never import `pygame`, `pyzed` or `cv2` (`tests/test_boundaries.py` fails the build).
- Never block: no network, no sleeping, no file I/O in `step`. Spark results arrive via `provide_*`.
- Every number (costs, damage, windows, HP, regen, effect times) is read from `cfg.game`; spell data lives in `config.yaml`. New keys get validation in `core/config.py` (`_check_game_effects`).
- Use `Action.t` and the tick time, not the wall clock. Distances are meters.
- The `GameView` contract is shared with render. Changing it needs a heads-up to Nikhil and a root `CLAUDE.md` update.

## Files
- `engine.py`: `Engine` facade (`step`, the `provide_*` calls); boot checks, names and class picks, debounced hands up, pause / abandon / camera, builds the `GameView`.
- `scenes.py`: `SceneMachine` (boot → lobby → loading → fight → victory), `Hold` (debounce), `parse_name` and `parse_lobby_speech`.
- `state.py`: `MatchState` (HP, mana, charges, cooldowns, effects, stats, projectiles in flight, round timer, banner, event log).
- `effects.py`: `Effects` (timed effects per player) and which effects go on the caster vs the target.
- `combat.py`: `speed_mult`, `dist_mult`, `damage` (spec Appendix A).
- `spells.py`: `SpellDef`, `load_spells`, `basic_attack` from config.
- `classes.py`: `class_ids`, `class_name`, `class_views`, `parse_class`, `class_prompt` from config.

## Test without the Jetson
```
uv run pytest tests/game
uv run python -m magic_box --fake
```
In fake mode the loop reports the camera at once, so boot leaves after `boot_min_s` (2 s); with no camera report it would wait `boot_max_s` (8 s). Then hold hands up (`r` + `y`) to start, charge with the spell keys, push with `f` / `h`, two-hand spells with `v` / `m`, Holy Light with hands up (`r` / `y`), Heal with hands together (`t` / `u`). Transcripts can't come from the keyboard; tests send `Action("speech", ...)`.

## Open TODOs
- Open decisions (Adetola): final classes, spells, costs, gestures and numbers; `heals` as a count vs HP. Ruled 2026-10-25: one dodge per Chain bolt.
- `game.charge_window_s` waits on the partial-latency measurement (Nikhil).
- Fake-mode damage runs high (fake pushes are 3.0 m/s, so `speed_mult` is 1.5): a Fireball with a perfect incantation does about 34.

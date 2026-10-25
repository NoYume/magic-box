# Game design

**Owner:** Adetola

> **DRAFT: open for discussion.** Everything below started as a proposal seeded from the design spec. The overnight beta (2026-10-25) built all of it and settled some open questions; those are marked **Decided overnight, Adetola to confirm**. Change anything freely: every number lives in `config.yaml` (`game:`) and is a guess until tuned on the Jetson.

## Casting

1. **Speak** the incantation into your own mic. A match score of 80 or more charges the spell for 3 s (`charge_window_s`) and reserves its mana. Muse often matches a prefix of the phrase first, so a match under 95 is held up to 0.5 s (`voice.perfect_hold_s`) in case the whole phrase lands.
2. **Release.** Attacks release with a push faster than 1.5 m/s toward the camera. Some spells need a two-hand push. Buffs release with a pose: one arm overhead for Holy Light, hands together at the chest for Heal. If the window passes with no release, the charge fizzles and the mana is refunded.
3. **Flight.** The projectile flies over the spell's travel time.
4. **Dodge.** In the last 0.6 s the defender can dodge by stepping at least 0.3 m sideways or ducking at least 0.25 m. A successful dodge means no damage. A dodge avoids one projectile per cast, so each Chain bolt needs its own dodge (**decided overnight, Adetola to confirm**).

**Basic attack:** a push with no charged spell. Free, 8 damage, 0.8 s cooldown, 0.7 s travel. The knight's main source of damage.

**Release grace** (**decided overnight, Adetola to confirm**): the voice charge lands about 0.4 s after the player stops speaking, so a player who pushes on the last word would otherwise throw a basic attack. When the player's mic is on and they can afford a spell that push could release by the end of the wait (mana regen over the 0.6 s counts, at the slowed rate while mana-slowed), an uncharged push waits up to 0.6 s (`release_grace_s`). If a matching charge lands in that time, the spell fires with that push. Otherwise the basic attack fires when the wait ends. Out of mana for every such spell, the basic fires at once. A push during the basic-attack cooldown is held the same way, but it can only release a spell: with no charge it is dropped. A push after the cooldown ends replaces such a hold, so spamming basic attacks never stalls: with the mic on they keep the 0.8 s cooldown cadence, each up to 0.6 s late (the cooldown of a held push counts from the push). With the mic off (keyboard play) there is no wait. A pose that is already held (arm overhead, hands together) releases a buff charge that lands late, but only if the pose rose within 1 s (`pose_grace_s`) before the charge; hands held up since the lobby don't count. If basic attacks feel laggy, lower `release_grace_s`.

## Damage

`base × speed_mult × atk_dist_mult × def_dist_mult × buffs`

- `speed_mult` = push speed ÷ 2.0 m/s, clamped to 0.6–1.8. Push speed is the **peak** wrist speed of the thrust (**decided overnight, Adetola/Enoch to confirm**), so a harder punch does more damage.
- The distance multiplier runs smoothly from ×1.4 at 1.2 m to ×0.7 at 2.8 m. The attacker's distance is read at release, the defender's at impact.
- Buffs: ×1.15 for a perfect incantation (match score 95 or more), ×1.5 while empowered by Holy Light (basic attacks too).

## Classes and spells

| Class | Spell (mana) | Effect | Release |
|---|---|---|---|
| Fire Mage | Fireball (25) | 18 damage, 1.6 s travel | push |
| | Flame Wall (30) | Shield on the caster for 4 s: blocks the next projectile of any kind, then ends | two-hand push |
| | Inferno (60) | 35 damage, 2.2 s travel. If it lands, the target's next charge window is ×0.6 (for 3 s) | push |
| Lightning Mage | Bolt (20) | 12 damage, 0.9 s travel | push |
| | Chain (35) | 3 bolts of 7 damage, 0.25 s apart, 1.2 s travel each | push |
| | Static Field (30) | A 0-damage projectile (1.4 s). If it lands, the target's mana regen is ×0.25 for 5 s | two-hand push |
| Holy Knight | Holy Light (30) | Empowered for 6 s: everything the caster releases does ×1.5 | arm overhead |
| | Heal (40) | +25 HP, capped at 100 | hands together |
| | Judgment (45) | 25 damage, 1.5 s travel | push |

**Parry and riposte (Holy Knight; Adetola, PR #2).** Hold one wrist toward the camera, between head and shoulder height, to guard. A guard raised in the 0.4 s before a projectile lands parries it: no damage, "PARRIED!", and a 1.5 s riposte window opens, in which the knight's next push that releases no spell fires a free 20-damage blade wave (0.5 s travel) at once, ignoring the basic cooldown. One guard parries one projectile (one bolt of a Chain). A new guard counts only 1.5 s after the last one. These values are untuned. P2 defaults to the Holy Knight so fake mode can show it.

Effects don't stack: casting one again keeps the longer timer. Effect timers stop while the fight is paused.

## Resources and match

100 HP, 100 mana, mana regenerates at 8 per second. One 90 s round (**decided overnight, Adetola to confirm**: no best of three). A KO, or higher HP at time-out, wins.

## Incantations

Muse Spark writes 1–3 words per spell (`words` per spell in config: the cheapest spell of each class 1, the middle one 2, the strongest 3; Heal is 2), themed by class with an Austin or HackTX flavor, and keeps each player's set clearly different from the other's. The prompt asks for common words a speech recognizer spells reliably (no acronyms such as "HackTX") and a different first word per spell. A match score of 95 or more gives the ×1.15 "perfect incantation" bonus (**decided overnight, Adetola to confirm**: the bonus stays). If Spark fails or takes longer than 8 s, fixed incantations from `config.yaml` are used.

## Scene flow

`boot → lobby → loading → fight → victory → lobby`

| Scene | What happens |
|---|---|
| boot | Self-check list: camera, mic P1, mic P2, network, API key, each with a check or a cross. Leaves once the camera has sent a frame (2 s at the earliest), or after 8 s whatever the checks say. Missing network still boots (voice offline, keyboard fallback). |
| lobby | Players step into the play area. Each picks a class by saying a keyword (`fire`, `lightning`, `holy` or `knight`, plus `lightening`, a spelling Muse sometimes writes; the last one said wins) and sets a name with a prefix ("my name is Ada", "call me Ada", "I am Ada", "I'm Ada") or a one- or two-word reply ("Ada"). One sentence can do both: "my name is Ada, fire". Chatter ("I'm ready", "this is cool") changes nothing. Both hold their hands up for 0.3 s to start. Banner: `SAY NAME · SAY FIRE, LIGHTNING OR HOLY · HANDS UP`. |
| loading | Spark generates incantations, shown on each half as a tutorial card. No countdown until they arrive; then at least 4 s (`loading_read_s`) to read them. Voice sessions restart with the match's keywords as soon as the incantations are known. |
| fight | 90 s round. A player out of view for 2 s pauses the fight, and the banner counts down to the abandon ("STEP INTO VIEW · 20"). A pause that lasts 20 s ends the match: the player still tracked wins, a draw if both are gone. While the camera is down the fight freezes ("CAMERA RECONNECTING") and never abandons. After a KO the fight freezes 2.5 s for the finishing effects. |
| victory | Winner headline, a stats card per player (damage, hits, casts, dodges, blocks, heals, best push speed), and the Duel Chronicle. Both raise hands to go back to the lobby, once 5 s have passed and the chronicle has been up for 4 s (`victory_read_s`), or it returns after 30 s. Names and classes persist. |

The lobby and victory rules were **decided overnight, Adetola to confirm**.

## Overnight beta engine (2026-10-25)

`game/` now plays every spell effect, the voice class pick, the boot scene and the pause rules. Details in `src/magic_box/game/CLAUDE.md`. The `game:` numbers in `config.yaml`:

| Key | Value | Meaning |
|---|---|---|
| `charge_window_s` | 3.0 | a charged spell waits this long for a release. Kept at 3.0 until the Jetson real-voice run (laptop TTS runs suggest 2.5) |
| `release_grace_s` | 0.6 | mic on: an uncharged push waits this long for a voice charge (guess) |
| `banner_s` | 1.2 | how long a banner shows |
| `boot_min_s` / `boot_max_s` | 2.0 / 8.0 | boot screen length bounds |
| `hands_up_hold_s` | 0.3 | hands up (or down) must hold this long to count (guess) |
| `loading_min_s` / `loading_max_s` | 3.0 / 10.0 | loading scene length bounds (waits for Spark up to the max) |
| `loading_read_s` | 4.0 | loading also lasts this long after the incantations arrive |
| `victory_min_s` / `victory_max_s` | 5.0 / 30.0 | victory scene: hands up allowed after the min, auto return at the max |
| `victory_read_s` | 4.0 | a hands-up exit from victory also waits this long after the chronicle arrives |
| `pause_after_s` | 2.0 | a player untracked this long pauses the match ("STEP INTO VIEW") |
| `abandon_after_s` | 20.0 | a pause this long ends the match |
| `ko_hold_s` | 2.5 | after a KO the fight stays frozen this long for the finishing effects; keep `render.fx.ko_s` equal (validated <=) |
| `pose_grace_s` | 1.0 | a late charge releases a held pose only if the pose rose this recently (guess) |
| `empowered_mult` | 1.5 | Holy Light damage multiplier |
| `mana_slow_mult` | 0.25 | Static Field mana regen multiplier |
| `slow_charge_mult` | 0.6 | Inferno charge window multiplier |
| `name_max_chars` / `name_max_words` | 12 / 2 | longest name taken from lobby speech |
| `name_stop_words` | list | words that are never part of a name (lobby chatter) |

Per-spell effect data sits on each spell in `game.classes`: `effect` + `effect_s`, `heal_hp`, `hits` + `chain_gap_s`. Class keywords are `game.classes.<id>.keywords`.

Fake-mode damage runs high because fake pushes are 3.0 m/s (`speed_mult` 1.5): a Fireball with a perfect incantation does about 34. Real balance depends on the peak punch speeds measured on the Jetson; the victory screen shows each player's `best_push_mps`.

## Open questions

- Final classes, spells, costs, gestures and numbers. Tune on the Jetson.
- Should the Flame Wall shield be popped by a cheap basic attack? Today it blocks any one projectile.
- `heals` in the stats counts heal casts, not HP healed. Is that the right label?
- The lobby lists FIRE, LIGHTNING and HOLY; `knight` also works but isn't shown.
- Which gestures are reliable with the default `BODY_34` keypoints (Enoch confirms after the benchmark)? If the Jetson needs `BODY_18`, recheck arm overhead and hands together.
- Resolved overnight (Adetola to confirm): class pick by voice keyword; a player leaving pauses after 2 s and ends the match after 20 s more; a single 90 s round; the perfect bonus stays; one dodge per Chain bolt.

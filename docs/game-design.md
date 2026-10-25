# Game design

**Owner:** Adetola

> **DRAFT: open for discussion.** Everything below is a proposal seeded from the design spec. Change it freely; every number lives in `config.yaml` (`game:`) and is a guess until tuned on recordings.

## Casting

1. **Speak** the incantation into your own mic. A match score of 80 or more charges the spell for 3 s and reserves its mana.
2. **Release.** Attacks release with a push faster than 1.5 m/s toward the camera. Buffs release with a pose: arm overhead for Holy Light, hands together at the chest for Heal. If the window passes with no release, the charge fizzles and the mana is refunded.
3. **Flight.** The projectile flies over the spell's travel time.
4. **Dodge.** In the last 0.6 s the defender can dodge by stepping at least 0.3 m sideways or ducking at least 0.25 m. A successful dodge means no damage.

**Basic attack:** a push with no charged spell. Free, 0.8 s cooldown, fast. The knight's main source of damage.

## Damage

`base × speed_mult × atk_dist_mult × def_dist_mult × buffs`

- `speed_mult` = push speed ÷ 2.0 m/s, clamped to 0.6–1.8.
- The distance multiplier runs smoothly from ×1.4 at 1.2 m to ×0.7 at 2.8 m. The attacker's distance is read at release, the defender's at impact.

## Classes and spells

| Class | Spells (mana) | Release |
|---|---|---|
| Fire Mage | Fireball, 18 damage (25) · Flame Wall, blocks next hit for 4 s (30) · Inferno, 35 damage, slow (60) | push · two-hand push · push |
| Lightning Mage | Bolt, 12 damage, 0.9 s travel (20) · Chain, 3 hits of 7 (35) · Static Field, slows opponent mana regen 5 s (30) | push · push · two-hand push |
| Holy Knight | Holy Light, ×1.5 damage for 6 s (30) · Heal, +25 HP (40) · Judgment, 25-damage sword wave (45) | arm overhead · hands together · push |

## Resources and match

100 HP, 100 mana, mana regenerates at 8 per second. One 90 s round. A KO, or higher HP at time-out, wins.

## Incantations

Muse Spark writes 3–7 words per spell, themed by class with an Austin or HackTX flavor, and keeps each player's set clearly different from the other's. A match score of 95 or more gives a ×1.15 "perfect incantation" bonus. If Spark fails, fixed incantations from `config.yaml` are used.

## Scene flow

`boot → lobby → loading → fight → victory → lobby`

| Scene | What happens |
|---|---|
| boot | Self-check: camera, both mics, network, API key. Shows status. Missing network still boots (voice offline, keyboard fallback). |
| lobby | Players step into the play area. Each says “My name is …” (or “Call me …”), which doubles as a mic check, then says Fire Mage, Lightning Mage, or Holy Knight. Both raise their hands to start; the displayed defaults remain a keyboard/offline fallback. |
| loading | Spark generates incantations, shown on each half as a tutorial card. Voice sessions restart with the match's keywords. Countdown. |
| fight | Default 90 s round. KO, or higher HP at time-out, wins. |
| victory | Winner banner, stats, and the Duel Chronicle (stretch). |

## Open questions

- Final classes, spells, costs, gestures and numbers.
- Lobby interactions: how do players pick a class by voice without a mic mix-up?
- Does a player leaving the frame pause the round after 2 s, or end it?
- Is the single 90 s round right, or best of three?
- Is the "perfect incantation" bonus worth the extra rule?
- Which gestures are reliable enough with BODY_18 keypoints (Enoch can say after the benchmark)?
- Is MediaPipe finger gesture input in or out?

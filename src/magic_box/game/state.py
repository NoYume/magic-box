"""Mutable match state (spec section 8, game/; Appendix A; docs/game-design.md).

Owner: Adetola

MatchState holds one fight: per-slot HP, mana, charge, basic-attack cooldown,
timed effects and match stats, the projectiles in flight, the round timer, the
banner and the event log. All rule timing runs on the match clock (`clock`,
starts at 0); `now` is only the timestamp written to GameEvent.t.

Event slots name the actor: `cast`, `hit` and `buff` the caster (`target` in the
data says who was hit or got the effect), `dodge` and `block` the defender,
`heal` the healed caster.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field

from magic_box.core.config import Config
from magic_box.core.contracts import Action, EffectView, GameEvent, PlayerState, ProjectileView
from magic_box.game.combat import damage
from magic_box.game.effects import HIT_EFFECTS, SELF_EFFECTS, Effects
from magic_box.game.spells import BASIC_ATTACK_ID, SpellDef, basic_attack, load_spells

Px = tuple[float, float]
POSE_RELEASES = {"hands_up": "arm_overhead", "hands_together": "hands_together"}
STAT_KEYS = ("damage", "hits", "casts", "dodges", "blocks", "heals", "best_push_mps")


@dataclass
class Charge:
    spell: SpellDef
    deadline: float  # match clock
    score: float


@dataclass
class HeldPush:
    action: Action
    until: float  # match clock
    spell_only: bool = False  # held during the basic cooldown: dropped, not a basic, at expiry


@dataclass
class PlayerMatch:
    slot: int
    name: str
    class_id: str
    spells: list[SpellDef]
    hp: float
    mana: float
    charge: Charge | None = None
    basic_ready_at: float = 0.0
    last_dist: float = 0.0
    effects: Effects = field(default_factory=Effects)
    stats: dict[str, float] = field(default_factory=lambda: dict.fromkeys(STAT_KEYS, 0.0))
    held: HeldPush | None = None  # an uncharged push waiting for a late voice charge
    pose_rise: dict[str, float] = field(default_factory=dict)  # pose flag -> match clock it rose


@dataclass
class Projectile:
    spell_id: str
    attacker: int
    target: int
    origin_px: Px
    launched: float  # match clock; later than now for the 2nd and 3rd Chain bolts
    travel_s: float
    base_damage: float
    speed: float | None
    atk_dist: float
    buff_mult: float
    hit_effect: str | None = None
    effect_s: float = 0.0
    cast_id: int = 0  # Chain's bolts share one; a dodge avoids one projectile per cast

    def elapsed(self, clock: float) -> float:
        return clock - self.launched

    def progress(self, clock: float) -> float:
        if self.travel_s <= 0:
            return 1.0
        return self.elapsed(clock) / self.travel_s

    def in_flight(self, clock: float) -> bool:
        return self.elapsed(clock) >= 0


class MatchState:
    def __init__(
        self,
        cfg: Config,
        names: Mapping[int, str],
        now: float,
        classes: Mapping[int, str] | None = None,
        mic_ok: Mapping[int, bool] | None = None,
    ) -> None:
        self.cfg = cfg
        g = cfg["game"]
        # Live view of the engine's mic status: a push is held only while the mic is ok.
        self.mic_ok: Mapping[int, bool] = mic_ok if mic_ok is not None else {}
        classes = classes if classes is not None else g["default_classes"]
        self.players: tuple[PlayerMatch, PlayerMatch] = tuple(  # type: ignore[assignment]
            PlayerMatch(
                slot=slot,
                name=names[slot],
                class_id=classes[slot],
                spells=load_spells(cfg, classes[slot]),
                hp=g["hp_max"],
                mana=g["mana_max"],
            )
            for slot in (0, 1)
        )
        self.projectiles: list[Projectile] = []
        self._casts = 0
        self.clock = 0.0
        self.time_left: float = g["round_s"]
        self._events: list[GameEvent] = []
        self._result: tuple[int | None, str] | None = None
        self._banner_text: str | None = None
        self._banner_until = 0.0
        self._set_banner("FIGHT!")
        self._log(
            now,
            "match_start",
            None,
            names={p.slot: p.name for p in self.players},
            classes={p.slot: p.class_id for p in self.players},
        )

    # -- public API -------------------------------------------------------

    def apply(self, action: Action, states: Mapping[int, PlayerState], now: float) -> None:
        self._track_dist(states)
        if self._result is not None:
            return
        if action.kind == "charge":
            self._charge(action, states, now)
        elif action.kind == "push":
            self._push(action, states, now)
        elif action.kind == "pose":
            self._pose(action, states, now)
        elif action.kind == "dodge":
            self._dodge(action, now)

    def advance(self, dt: float, states: Mapping[int, PlayerState], now: float) -> None:
        self._track_dist(states)
        if self._result is not None:
            return
        g = self.cfg["game"]
        for p in self.players:
            regen = g["mana_regen_per_s"] * dt
            if p.effects.active("mana_slow", self.clock):
                regen *= g["mana_slow_mult"]
            p.mana = min(p.mana + regen, g["mana_max"])
        self.clock += dt
        for p in self.players:
            p.effects.expire(self.clock)
            if p.charge is not None and self.clock >= p.charge.deadline:
                self._refund(p)
            if p.held is not None and self.clock >= p.held.until:
                held, p.held = p.held, None
                if not held.spell_only:
                    self._basic(p, held.action, now)
        for proj in sorted(self.projectiles, key=lambda pr: pr.launched + pr.travel_s):
            if self._result is not None:
                break
            if proj.in_flight(self.clock) and proj.progress(self.clock) >= 1.0:
                self.projectiles.remove(proj)
                self._impact(proj, now)
        if self._result is None:
            self.time_left -= dt
            if self.time_left <= 0:
                self._time_out(now)

    def abandon(self, now: float, winner: int | None) -> None:
        """End a match a player walked away from (the engine decides when)."""
        if self._result is None:
            self._end(now, winner, "abandon")

    def take_events(self) -> list[GameEvent]:
        events, self._events = self._events, []
        return events

    def result(self) -> tuple[int | None, str] | None:
        return self._result

    def banner(self) -> str | None:
        return self._banner_text if self.clock < self._banner_until else None

    def projectile_views(self) -> tuple[ProjectileView, ...]:
        window = self.cfg["game"]["dodge_window_s"]
        return tuple(
            ProjectileView(
                spell_id=p.spell_id,
                target_slot=p.target,
                origin_px=p.origin_px,
                progress=min(max(p.progress(self.clock), 0.0), 1.0),
                in_dodge_window=p.travel_s - p.elapsed(self.clock) <= window,
            )
            for p in self.projectiles
            if p.in_flight(self.clock)
        )

    def effect_views(self, slot: int) -> tuple[EffectView, ...]:
        return self.players[slot].effects.views(self.clock)

    def charge_left(self, slot: int) -> float:
        c = self.players[slot].charge
        return max(c.deadline - self.clock, 0.0) if c is not None else 0.0

    def cooldown_left(self, slot: int) -> float:
        return max(self.players[slot].basic_ready_at - self.clock, 0.0)

    def stats(self, slot: int) -> dict[str, float]:
        s = dict(self.players[slot].stats)
        s["damage"] = round(s["damage"], 1)
        s["best_push_mps"] = round(s["best_push_mps"], 2)
        return s

    # -- helpers ----------------------------------------------------------

    def _log(self, now: float, kind: str, slot: int | None, **data: object) -> None:
        self._events.append(GameEvent(now, kind, slot, data))

    def _set_banner(self, text: str) -> None:
        self._banner_text = text
        self._banner_until = self.clock + self.cfg["game"]["banner_s"]

    def _track_dist(self, states: Mapping[int, PlayerState]) -> None:
        for p in self.players:
            st = states.get(p.slot)
            if st is not None and st.tracking_ok:
                p.last_dist = st.root[2]

    def _refund(self, p: PlayerMatch) -> None:
        if p.charge is not None:
            p.mana = min(p.mana + p.charge.spell.cost, self.cfg["game"]["mana_max"])
            p.charge = None

    def clear_in_flight(self) -> None:
        """Drop projectiles and held pushes (the match is over)."""
        self.projectiles.clear()
        for p in self.players:
            p.held = None

    def _charge(self, action: Action, states: Mapping[int, PlayerState], now: float) -> None:
        p = self.players[action.slot]
        spell = next((s for s in p.spells if s.id == action.spell_id), None)
        if spell is None or p.mana < spell.cost:
            return
        g = self.cfg["game"]
        self._refund(p)
        p.mana -= spell.cost
        window = g["charge_window_s"]
        if p.effects.consume("slow", self.clock):
            window *= g["slow_charge_mult"]
        p.charge = Charge(spell, self.clock + window, action.match_score)
        if p.held is not None and self._releases(spell, p.held.action):
            held, p.held, c, p.charge = p.held.action, None, p.charge, None
            assert held.push is not None
            self._cast(p, c, held, held.push.origin_px, held.push.speed, now)
            return
        # The voice charge lands ~0.4 s (worst ~0.8 s) after speech: a release pose that rose
        # within pose_grace_s and is still held releases it now, rather than waiting for the
        # player to lower and raise again. An older pose (hands up since the lobby) doesn't.
        st = states.get(p.slot)
        if st is not None and st.tracking_ok:
            recent = self.clock - self.cfg["game"]["pose_grace_s"]
            for flag in sorted(st.pose_flags):
                if (
                    POSE_RELEASES.get(flag) == spell.release
                    and p.pose_rise.get(flag, float("-inf")) >= recent
                ):
                    c, p.charge = p.charge, None
                    pose = Action("pose", p.slot, action.t, pose=flag, dist=st.root[2])
                    self._cast(p, c, pose, self._pose_origin(p.slot, states), None, now)
                    return

    def _push(self, action: Action, states: Mapping[int, PlayerState], now: float) -> None:
        p = self.players[action.slot]
        assert action.push is not None
        p.stats["best_push_mps"] = max(p.stats["best_push_mps"], action.push.speed)
        c = p.charge
        if c is not None:
            if self._releases(c.spell, action):
                p.charge = None
                self._cast(p, c, action, action.push.origin_px, action.push.speed, now)
                return
        on_cooldown = self.clock < p.basic_ready_at
        if p.held is not None and p.held.spell_only and not on_cooldown:
            p.held = None  # the cooldown is over: this push may fire a basic again
        if p.held is not None:
            return  # a push is already held: ignored
        grace = self.cfg["game"]["release_grace_s"]
        if (
            c is None
            and grace > 0
            and self.mic_ok.get(p.slot, False)
            and self._can_afford_a_release(p, action)
        ):
            # The voice charge lands ~0.4 s after speech: give it a chance to catch up. On the
            # basic cooldown the push can still release a late spell, but never a basic.
            p.held = HeldPush(action, self.clock + grace, spell_only=on_cooldown)
            return
        if not on_cooldown:
            self._basic(p, action, now)

    def _can_afford_a_release(self, p: PlayerMatch, push: Action) -> bool:
        """Some spell this push could release is affordable by the end of the grace (mana
        regen over the hold counted, slowed by mana_slow); else there is nothing to wait for."""
        g = self.cfg["game"]
        regen = g["mana_regen_per_s"] * g["release_grace_s"]
        if p.effects.active("mana_slow", self.clock):
            regen *= g["mana_slow_mult"]
        mana = min(p.mana + regen, g["mana_max"])
        return any(self._releases(sp, push) and mana >= sp.cost for sp in p.spells)

    @staticmethod
    def _releases(spell: SpellDef, push: Action) -> bool:
        """A two-hand push releases push and two-hand spells; a plain push only push spells."""
        kinds = ("two_hand_push", "push") if push.two_hand else ("push",)
        return spell.release in kinds

    def _basic(self, p: PlayerMatch, action: Action, now: float) -> None:
        assert action.push is not None
        p.basic_ready_at = self.clock + self.cfg["game"]["basic_attack_cooldown_s"]
        basic = Charge(basic_attack(self.cfg), 0.0, 0.0)
        self._cast(p, basic, action, action.push.origin_px, action.push.speed, now)

    def _pose(self, action: Action, states: Mapping[int, PlayerState], now: float) -> None:
        p = self.players[action.slot]
        p.pose_rise[action.pose or ""] = self.clock
        c = p.charge
        if c is None or POSE_RELEASES.get(action.pose or "") != c.spell.release:
            return
        p.charge = None
        self._cast(p, c, action, self._pose_origin(action.slot, states), None, now)

    def _pose_origin(self, slot: int, states: Mapping[int, PlayerState]) -> Px:
        st = states.get(slot)
        if st is not None:
            for name in ("r_wrist", "l_wrist"):
                if name in st.keypoints_px:
                    return st.keypoints_px[name]
            x0, y0, x1, y1 = st.bbox_px
            return ((x0 + x1) / 2, (y0 + y1) / 2)
        cam = self.cfg["camera"]
        return (cam["image_width"] / 2, cam["image_height"] / 2)

    def _cast(
        self,
        p: PlayerMatch,
        charge: Charge,
        action: Action,
        origin: Px,
        speed: float | None,
        now: float,
    ) -> None:
        spell = charge.spell
        g = self.cfg["game"]
        self._log(
            now,
            "cast",
            p.slot,
            spell_id=spell.id,
            release=spell.release,
            two_hand=action.two_hand,
        )
        if spell.id != BASIC_ATTACK_ID:
            p.stats["casts"] += 1
        # Multipliers are fixed at release: a spell thrown while empowered stays empowered.
        mult = g["perfect_mult"] if charge.score >= self.cfg["voice"]["perfect_threshold"] else 1.0
        if p.effects.active("empowered", self.clock):
            mult *= g["empowered_mult"]
        if spell.effect in SELF_EFFECTS:
            self._add_effect(p.slot, p.slot, spell.id, spell.effect, spell.effect_s, now)
        if spell.heal_hp > 0:
            self._heal(p, spell, now)
        if not spell.is_projectile:
            self._set_banner(spell.name.upper() + "!")
            return
        atk_dist = action.dist if action.dist > 0 else p.last_dist
        self._casts += 1
        for i in range(max(spell.hits, 1)):
            self.projectiles.append(
                Projectile(
                    spell_id=spell.id,
                    attacker=p.slot,
                    target=1 - p.slot,
                    origin_px=origin,
                    launched=self.clock + i * spell.chain_gap_s,
                    travel_s=spell.travel_s,
                    base_damage=spell.damage,
                    speed=speed,
                    atk_dist=atk_dist,
                    buff_mult=mult,
                    hit_effect=spell.effect if spell.effect in HIT_EFFECTS else None,
                    effect_s=spell.effect_s,
                    cast_id=self._casts,
                )
            )

    def _add_effect(
        self, by: int, target: int, spell_id: str, kind: str, duration_s: float, now: float
    ) -> None:
        self.players[target].effects.add(kind, self.clock, duration_s)
        self._log(
            now, "buff", by, spell_id=spell_id, effect=kind, target=target, duration_s=duration_s
        )

    def _heal(self, p: PlayerMatch, spell: SpellDef, now: float) -> None:
        before = p.hp
        p.hp = min(p.hp + spell.heal_hp, self.cfg["game"]["hp_max"])
        p.stats["heals"] += 1
        self._log(
            now,
            "heal",
            p.slot,
            spell_id=spell.id,
            amount=round(p.hp - before, 1),
            hp=round(p.hp, 1),
        )

    def _dodge(self, action: Action, now: float) -> None:
        """Avoid every cast landing within the dodge window, but only its earliest projectile
        (each Chain bolt needs its own dodge)."""
        window = self.cfg["game"]["dodge_window_s"]
        dodged: set[int] = set()
        for proj in sorted(self.projectiles, key=lambda pr: pr.launched + pr.travel_s):
            if proj.target != action.slot or proj.cast_id in dodged:
                continue
            if proj.travel_s - proj.elapsed(self.clock) <= window:
                dodged.add(proj.cast_id)
                self.projectiles.remove(proj)
                self.players[action.slot].stats["dodges"] += 1
                self._log(now, "dodge", action.slot, spell_id=proj.spell_id, dodge=action.dodge)

    def _impact(self, proj: Projectile, now: float) -> None:
        target = self.players[proj.target]
        attacker = self.players[proj.attacker]
        if target.effects.consume("shield", self.clock):
            target.stats["blocks"] += 1
            self._log(now, "block", target.slot, spell_id=proj.spell_id, attacker=proj.attacker)
            return
        dmg = damage(
            proj.base_damage,
            proj.speed,
            proj.atk_dist,
            target.last_dist,
            proj.buff_mult,
            self.cfg,
        )
        attacker.stats["damage"] += min(dmg, target.hp)  # overkill doesn't count
        target.hp = max(target.hp - dmg, 0.0)
        attacker.stats["hits"] += 1
        self._log(
            now,
            "hit",
            proj.attacker,
            spell_id=proj.spell_id,
            damage=round(dmg, 1),
            target=proj.target,
            hp_left=round(target.hp, 1),
        )
        if target.hp <= 0:
            self._log(now, "ko", None, winner=proj.attacker)
            self._end(now, proj.attacker, "ko")
            return  # no effect on a KO'd player (it would pop "SLOWED!" over the K.O.)
        if proj.hit_effect is not None:
            self._add_effect(
                proj.attacker, proj.target, proj.spell_id, proj.hit_effect, proj.effect_s, now
            )

    def _time_out(self, now: float) -> None:
        h0, h1 = self.players[0].hp, self.players[1].hp
        winner = 0 if h0 > h1 else 1 if h1 > h0 else None
        self._end(now, winner, "time")

    def _end(self, now: float, winner: int | None, reason: str) -> None:
        self._result = (winner, reason)
        self.clear_in_flight()  # nothing lands after the end (the KO hold shows a frozen fight)
        self._log(
            now,
            "match_end",
            None,
            winner=winner,
            reason=reason,
            hp={p.slot: round(p.hp, 1) for p in self.players},
        )

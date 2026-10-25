"""Mutable match state (spec section 8, game/; Appendix A).

Owner: Adetola
Thin placeholder rules (2026-10-24 phase); replace freely.

MatchState holds one fight: per-slot HP, mana, charge and basic-attack
cooldown, the projectiles in flight, the round timer, the banner and the
event log. All rule timing runs on the match clock (`clock`, starts at 0);
`now` is only the timestamp written to GameEvent.t.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from magic_box.core.config import Config
from magic_box.core.contracts import Action, GameEvent, PlayerState, ProjectileView
from magic_box.game.combat import damage
from magic_box.game.spells import BASIC_ATTACK_ID, SpellDef, load_spells

Px = tuple[float, float]
POSE_RELEASES = {"hands_up": "arm_overhead", "hands_together": "hands_together"}


@dataclass
class Charge:
    spell: SpellDef
    deadline: float  # match clock
    score: float


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


@dataclass
class Projectile:
    spell_id: str
    attacker: int
    target: int
    origin_px: Px
    launched: float  # match clock
    travel_s: float
    base_damage: float
    speed: float | None
    atk_dist: float
    buff_mult: float

    def elapsed(self, clock: float) -> float:
        return clock - self.launched

    def progress(self, clock: float) -> float:
        if self.travel_s <= 0:
            return 1.0
        return self.elapsed(clock) / self.travel_s


class MatchState:
    def __init__(self, cfg: Config, names: Mapping[int, str], now: float) -> None:
        self.cfg = cfg
        g = cfg["game"]
        self.players: tuple[PlayerMatch, PlayerMatch] = tuple(  # type: ignore[assignment]
            PlayerMatch(
                slot=slot,
                name=names[slot],
                class_id=g["default_classes"][slot],
                spells=load_spells(cfg, g["default_classes"][slot]),
                hp=g["hp_max"],
                mana=g["mana_max"],
            )
            for slot in (0, 1)
        )
        self.projectiles: list[Projectile] = []
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
            self._charge(action)
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
        self.clock += dt
        for p in self.players:
            p.mana = min(p.mana + g["mana_regen_per_s"] * dt, g["mana_max"])
            if p.charge is not None and self.clock >= p.charge.deadline:
                self._refund(p)
        for proj in list(self.projectiles):
            if self._result is not None:
                break
            if proj.progress(self.clock) >= 1.0:
                self.projectiles.remove(proj)
                self._impact(proj, now)
        if self._result is None:
            self.time_left -= dt
            if self.time_left <= 0:
                self._time_out(now)

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
        )

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

    def _charge(self, action: Action) -> None:
        p = self.players[action.slot]
        spell = next((s for s in p.spells if s.id == action.spell_id), None)
        if spell is None or p.mana < spell.cost:
            return
        self._refund(p)
        p.mana -= spell.cost
        p.charge = Charge(
            spell, self.clock + self.cfg["game"]["charge_window_s"], action.match_score
        )

    def _push(self, action: Action, states: Mapping[int, PlayerState], now: float) -> None:
        p = self.players[action.slot]
        assert action.push is not None
        c = p.charge
        if c is not None:
            kinds = ("two_hand_push", "push") if action.two_hand else ("push",)
            if c.spell.release in kinds:
                p.charge = None
                self._cast(p, c, action, action.push.origin_px, action.push.speed, now)
                return
        if self.clock >= p.basic_ready_at:
            g = self.cfg["game"]
            p.basic_ready_at = self.clock + g["basic_attack_cooldown_s"]
            basic = SpellDef(
                BASIC_ATTACK_ID,
                "Basic",
                0,
                g["basic_attack_damage"],
                g["basic_attack_travel_s"],
                "push",
                {},
            )
            self._cast(
                p, Charge(basic, 0.0, 0.0), action, action.push.origin_px, action.push.speed, now
            )

    def _pose(self, action: Action, states: Mapping[int, PlayerState], now: float) -> None:
        p = self.players[action.slot]
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
        self._log(
            now,
            "cast",
            p.slot,
            spell_id=spell.id,
            release=spell.release,
            two_hand=action.two_hand,
        )
        if spell.damage <= 0:
            self._set_banner(spell.name.upper() + "!")
            return
        g = self.cfg["game"]
        perfect = charge.score >= self.cfg["voice"]["perfect_threshold"]
        self.projectiles.append(
            Projectile(
                spell_id=spell.id,
                attacker=p.slot,
                target=1 - p.slot,
                origin_px=origin,
                launched=self.clock,
                travel_s=spell.travel_s,
                base_damage=spell.damage,
                speed=speed,
                atk_dist=action.dist if action.dist > 0 else p.last_dist,
                buff_mult=g["perfect_mult"] if perfect else 1.0,
            )
        )

    def _dodge(self, action: Action, now: float) -> None:
        window = self.cfg["game"]["dodge_window_s"]
        for proj in list(self.projectiles):
            if proj.target != action.slot:
                continue
            if proj.travel_s - proj.elapsed(self.clock) <= window:
                self.projectiles.remove(proj)
                self._log(now, "dodge", action.slot, spell_id=proj.spell_id, dodge=action.dodge)

    def _impact(self, proj: Projectile, now: float) -> None:
        target = self.players[proj.target]
        dmg = damage(
            proj.base_damage,
            proj.speed,
            proj.atk_dist,
            target.last_dist,
            proj.buff_mult,
            self.cfg,
        )
        target.hp = max(target.hp - dmg, 0.0)
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

    def _time_out(self, now: float) -> None:
        h0, h1 = self.players[0].hp, self.players[1].hp
        winner = 0 if h0 > h1 else 1 if h1 > h0 else None
        self._end(now, winner, "time")

    def _end(self, now: float, winner: int | None, reason: str) -> None:
        self._result = (winner, reason)
        self._log(
            now,
            "match_end",
            None,
            winner=winner,
            reason=reason,
            hp={p.slot: round(p.hp, 1) for p in self.players},
        )

"""Game engine facade: Actions in, GameView and GameEvents out (spec section 8, game/).

Owner: Adetola
Thin placeholder rules (2026-10-24 phase); replace freely.

Owns the SceneMachine and the current MatchState, routes actions, and builds
the GameView that render draws.
"""

from collections.abc import Mapping, Sequence

from magic_box.core.config import Config
from magic_box.core.contracts import (
    Action,
    GameEvent,
    GameView,
    PlayerState,
    PlayerView,
    SpellView,
)
from magic_box.game.scenes import SceneMachine, parse_name
from magic_box.game.spells import SpellDef, load_spells
from magic_box.game.state import MatchState

LOBBY_BANNER = "SAY YOUR NAME · BOTH RAISE YOUR HANDS"
PAUSE_BANNER = "STEP INTO VIEW"
SLOTS = (0, 1)


class Engine:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self._scenes = SceneMachine(cfg)
        self._names: dict[int, str] = {s: f"P{s + 1}" for s in SLOTS}
        self._incantations: dict[int, dict[str, str]] | None = None
        self._match: MatchState | None = None
        self._chronicle: str | None = None
        self._mic_ok: dict[int, bool] = {s: False for s in SLOTS}
        self._last_now: float | None = None
        self._untracked_since: dict[int, float] = {}
        self._result: tuple[int | None, str] | None = None
        self._paused = False

    # -- public API -------------------------------------------------------

    def step(
        self, actions: Sequence[Action], states: Mapping[int, PlayerState], now: float
    ) -> tuple[GameView, list[GameEvent]]:
        dt = 0.0 if self._last_now is None else max(now - self._last_now, 0.0)
        self._last_now = now
        events: list[GameEvent] = []
        self._track_presence(states, now)
        scene = self._scenes.scene
        if scene == "lobby":
            self._lobby_actions(actions)
        elif scene == "loading":
            if self._incantations is None and self._scenes.elapsed(now) >= self._g["loading_max_s"]:
                self._incantations = {}
                self._fill_fallbacks()
        elif scene == "fight":
            events += self._fight(actions, states, dt, now)

        both_ready = all(
            (st := states.get(s)) is not None and st.tracking_ok and "hands_up" in st.pose_flags
            for s in SLOTS
        )
        changed = self._scenes.update(
            now,
            both_ready=both_ready,
            incantations_ready=self._incantations is not None,
            match_over=self._match is not None and self._match.result() is not None,
        )
        if changed:
            events += self._on_enter(now)
        return self._build_view(states, now), events

    def provide_incantations(self, incantations: dict[int, dict[str, str]]) -> None:
        if self._scenes.scene != "loading":
            return
        self._incantations = {s: dict(incantations.get(s, {})) for s in SLOTS}
        self._fill_fallbacks()

    def provide_chronicle(self, text: str) -> None:
        if self._scenes.scene == "victory":
            self._chronicle = text

    def provide_mic_status(self, slot: int, ok: bool) -> None:
        self._mic_ok[slot] = ok

    # -- scene work -------------------------------------------------------

    @property
    def _g(self) -> dict:
        return self.cfg["game"]

    def _track_presence(self, states: Mapping[int, PlayerState], now: float) -> None:
        for s in SLOTS:
            st = states.get(s)
            if st is not None and st.tracking_ok:
                self._untracked_since.pop(s, None)
            else:
                self._untracked_since.setdefault(s, now)

    def _lobby_actions(self, actions: Sequence[Action]) -> None:
        for a in actions:
            if a.kind == "speech":
                name = parse_name(a.text, self._g["name_max_chars"])
                if name is not None:
                    self._names[a.slot] = name

    def _fight(
        self,
        actions: Sequence[Action],
        states: Mapping[int, PlayerState],
        dt: float,
        now: float,
    ) -> list[GameEvent]:
        match = self._match
        assert match is not None
        limit = self._g["pause_after_s"]
        self._paused = any(now - t > limit for t in self._untracked_since.values())
        if not self._paused:
            for a in actions:
                match.apply(a, states, now)
            match.advance(dt, states, now)
        return match.take_events()

    def _fill_fallbacks(self) -> None:
        assert self._incantations is not None
        for s in SLOTS:
            inc = self._incantations.setdefault(s, {})
            for sp in load_spells(self.cfg, self._g["default_classes"][s]):
                inc.setdefault(sp.id, sp.fallback.get(s, ""))

    def _on_enter(self, now: float) -> list[GameEvent]:
        scene = self._scenes.scene
        events: list[GameEvent] = []
        if scene == "loading":
            self._incantations = None
            self._chronicle = None
        elif scene == "fight":
            self._untracked_since.clear()
            self._paused = False
            self._match = MatchState(self.cfg, self._names, now)
            events += self._match.take_events()
        elif scene == "victory":
            assert self._match is not None
            self._result = self._match.result()
            self._match.projectiles.clear()
        elif scene == "lobby":
            self._match = None
            self._incantations = None
            self._result = None
        return events

    # -- view -------------------------------------------------------------

    def _build_view(self, states: Mapping[int, PlayerState], now: float) -> GameView:
        scene = self._scenes.scene
        match = self._match if scene in ("fight", "victory") else None
        banner: str | None = None
        timer: float | None = None
        projectiles = ()
        if scene == "lobby":
            banner = LOBBY_BANNER
        elif scene == "loading":
            timer = max(0.0, self._g["loading_min_s"] - self._scenes.elapsed(now))
        elif scene == "fight":
            assert match is not None
            banner = PAUSE_BANNER if self._paused else match.banner()
            timer = match.time_left
            projectiles = match.projectile_views()
        elif scene == "victory":
            banner = self._victory_banner()
        players = tuple(self._player_view(s, states.get(s), match) for s in SLOTS)
        return GameView(
            scene=scene,
            players=players,  # type: ignore[arg-type]
            projectiles=projectiles,
            banner=banner,
            timer_s=timer,
            chronicle=self._chronicle if scene == "victory" else None,
        )

    def _victory_banner(self) -> str:
        winner = self._result[0] if self._result else None
        return "DRAW" if winner is None else f"{self._names[winner].upper()} WINS"

    def _player_view(
        self, slot: int, state: PlayerState | None, match: MatchState | None
    ) -> PlayerView:
        g = self._g
        class_id = g["default_classes"][slot]
        pm = match.players[slot] if match is not None else None
        charged_id = pm.charge.spell.id if pm is not None and pm.charge is not None else None
        inc = (self._incantations or {}).get(slot, {})
        spells = tuple(
            self._spell_view(sp, inc, charged_id) for sp in load_spells(self.cfg, class_id)
        )
        return PlayerView(
            slot=slot,
            name=self._names[slot],
            class_id=class_id,
            hp=pm.hp if pm else g["hp_max"],
            hp_max=g["hp_max"],
            mana=pm.mana if pm else g["mana_max"],
            mana_max=g["mana_max"],
            spells=spells,
            zone=state.zone if state else "neutral",
            dist=state.root[2] if state else 0.0,
            mic_ok=self._mic_ok[slot],
            tracking_ok=state.tracking_ok if state else False,
        )

    @staticmethod
    def _spell_view(sp: SpellDef, inc: Mapping[str, str], charged_id: str | None) -> SpellView:
        return SpellView(
            id=sp.id,
            name=sp.name,
            incantation=inc.get(sp.id, ""),
            cost=sp.cost,
            charged=sp.id == charged_id,
            release=sp.release,
        )

"""Game engine facade: Actions in, GameView and GameEvents out (spec section 8, game/).

Owner: Adetola

Owns the SceneMachine and the current MatchState, routes actions, and builds
the GameView that render draws. Also owns what lives outside a match: boot
checks, camera health, names and class picks, debounced hands-up, and the
pause / abandon rule.
"""

import math
import re
from collections.abc import Mapping, Sequence

from magic_box.core.config import Config
from magic_box.core.contracts import (
    Action,
    CheckView,
    GameEvent,
    GameView,
    PlayerState,
    PlayerView,
    SpellView,
)
from magic_box.game.classes import class_prompt, class_views
from magic_box.game.scenes import Hold, SceneMachine, parse_lobby_speech
from magic_box.game.spells import SpellDef, load_spells
from magic_box.game.state import MatchState

PAUSE_BANNER = "STEP INTO VIEW"
CAMERA_BANNER = "CAMERA RECONNECTING"
SLOTS = (0, 1)
CHECK_NAMES = ("camera", "mic P1", "mic P2", "network", "api key")
UNKNOWN_CHECK = (False, "checking")


class Engine:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        g = cfg["game"]
        self._scenes = SceneMachine(cfg)
        self._names: dict[int, str] = {s: f"P{s + 1}" for s in SLOTS}
        self._classes: dict[int, str] = {s: g["default_classes"][s] for s in SLOTS}
        self._spells: dict[str, list[SpellDef]] = {c: load_spells(cfg, c) for c in g["classes"]}
        self._class_views = class_views(cfg)
        self._lobby_banner = f"SAY NAME · {class_prompt(cfg)} · HANDS UP"
        self._heard: dict[int, str] = {s: "" for s in SLOTS}
        self._hands: dict[int, Hold] = {s: Hold(g["hands_up_hold_s"]) for s in SLOTS}
        self._incantations: dict[int, dict[str, str]] | None = None
        self._incantations_at: float | None = None  # first step that saw them (loading)
        self._match: MatchState | None = None
        self._chronicle: str | None = None
        self._chronicle_at: float | None = None  # first step that saw it (victory)
        self._mic_ok: dict[int, bool] = {s: False for s in SLOTS}
        self._last_now: float | None = None
        self._untracked_since: dict[int, float] = {}
        self._result: tuple[int | None, str] | None = None
        self._pause: str | None = None  # None | "camera" | "tracking"
        self._tracking_pause_since: float | None = None
        self._reacquire: set[int] = set()  # after a camera pause: slots not seen again yet
        self._ko_at: float | None = None  # when the KO landed (the fight scene holds)
        self._camera_ok: bool | None = None  # None until the loop reports
        self._checks: dict[str, tuple[bool, str]] = {}
        self._lobby_requested = False

    # -- public API -------------------------------------------------------

    def step(
        self, actions: Sequence[Action], states: Mapping[int, PlayerState], now: float
    ) -> tuple[GameView, list[GameEvent]]:
        dt = 0.0 if self._last_now is None else max(now - self._last_now, 0.0)
        self._last_now = now
        events: list[GameEvent] = []
        self._track_presence(states, now)
        ready = self._update_ready(states, now)
        for a in actions:
            if a.kind == "speech":
                self._heard[a.slot] = a.text
                if self._scenes.scene == "victory" and self._says_menu(a.text):
                    self._lobby_requested = True
        if self._lobby_requested:
            self._lobby_requested = False
            if self._scenes.reset_to_lobby(now):
                events += self._on_enter(now)
                return self._build_view(states, now, events), events
        scene = self._scenes.scene
        if scene == "lobby":
            self._lobby_actions(actions)
        elif scene == "loading":
            if self._incantations is None and self._scenes.elapsed(now) >= self._g["loading_max_s"]:
                self._incantations = {}
                self._fill_fallbacks()
            if self._incantations is not None and self._incantations_at is None:
                self._incantations_at = now
        elif scene == "fight":
            events += self._fight(actions, states, dt, now)
        elif scene == "victory" and self._chronicle is not None and self._chronicle_at is None:
            self._chronicle_at = now

        changed = self._scenes.update(
            now,
            both_ready=all(ready.values()),
            incantations_ready=self._loading_left(now) == 0.0,
            match_over=self._match_over(now),
            camera_ok=self._check("camera")[0],
            chronicle_ready=self._chronicle_at is not None
            and now - self._chronicle_at >= self._g["victory_read_s"] - 1e-9,
        )
        if changed:
            events += self._on_enter(now)
        return self._build_view(states, now, events), events

    def request_lobby(self) -> None:
        """Go back to the lobby on the next step (the operator's reset key), keeping names and
        classes. Ignored in boot and lobby."""
        self._lobby_requested = True

    def _says_menu(self, text: str) -> bool:
        """A victory transcript asking for the menu ("main menu", "play again", ...)."""
        said = " " + " ".join(re.findall(r"[a-z']+", text.lower())) + " "
        return any(f" {w} " in said for w in self._g["menu_words"])

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
        self._derived_check(f"mic P{slot + 1}", ok, "connected" if ok else "off")

    def provide_camera_status(self, ok: bool) -> None:
        """Camera frames arriving; False while perception restarts (CAMERA RECONNECTING).

        A status never makes the boot `camera` line ok: the loop reports ok before the first
        frame, so only `provide_check("camera", True)` (BootChecks: a frame seen) passes boot.
        A False status marks the line "no frames" only while it isn't ok yet; once frames
        were seen the line stays ok, and the banner and pause show the live state.
        """
        self._camera_ok = ok
        if not ok and not self._check("camera")[0]:
            self._derived_check("camera", False, "no frames")

    def provide_check(self, name: str, ok: bool, detail: str = "") -> None:
        """One boot self-check result (`camera`, `mic P1`, `mic P2`, `network`, `api key`)."""
        self._checks[name] = (ok, detail)

    # -- scene work -------------------------------------------------------

    @property
    def _g(self) -> dict:
        return self.cfg["game"]

    def _check(self, name: str) -> tuple[bool, str]:
        return self._checks.get(name, UNKNOWN_CHECK)

    def _derived_check(self, name: str, ok: bool, detail: str) -> None:
        """Status from a provide_* stream; keeps a provide_check detail while ok agrees."""
        prev = self._checks.get(name)
        if prev is None or prev[0] != ok:
            self._checks[name] = (ok, detail)

    def _track_presence(self, states: Mapping[int, PlayerState], now: float) -> None:
        for s in SLOTS:
            st = states.get(s)
            if st is not None and st.tracking_ok:
                self._untracked_since.pop(s, None)
            else:
                self._untracked_since.setdefault(s, now)

    def _update_ready(self, states: Mapping[int, PlayerState], now: float) -> dict[int, bool]:
        ready = {}
        for s in SLOTS:
            st = states.get(s)
            raw = st is not None and st.tracking_ok and "hands_up" in st.pose_flags
            ready[s] = self._hands[s].update(raw, now)
        return ready

    def _lobby_actions(self, actions: Sequence[Action]) -> None:
        """A transcript can pick the class, set the name, or both (`parse_lobby_speech`)."""
        for a in actions:
            if a.kind != "speech":
                continue
            name, class_id = parse_lobby_speech(a.text, self.cfg)
            if class_id is not None:
                self._classes[a.slot] = class_id
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
        g = self._g
        if match.result() is not None:
            # KO hold: the match is frozen and decided; no pause, abandon or camera logic.
            self._pause = None
            return match.take_events()
        if self._camera_ok is False:
            # Nobody is tracked while perception restarts. Once frames return, anyone not
            # tracked yet pauses the fight at once, and the abandon clock starts then.
            self._untracked_since.clear()
            self._reacquire = set(SLOTS)
            self._pause = "camera"
        else:
            self._reacquire &= set(self._untracked_since)
            limit = g["pause_after_s"]
            gone = any(now - t > limit for t in self._untracked_since.values())
            self._pause = "tracking" if gone or self._reacquire else None
        if self._pause == "tracking":
            if self._tracking_pause_since is None:
                self._tracking_pause_since = now
            elif now - self._tracking_pause_since >= g["abandon_after_s"]:
                tracked = [s for s in SLOTS if s not in self._untracked_since]
                match.abandon(now, tracked[0] if len(tracked) == 1 else None)
        else:
            self._tracking_pause_since = None
        if self._pause is None:
            for a in actions:
                match.apply(a, states, now)
            match.advance(dt, states, now)
        return match.take_events()

    def _loading_left(self, now: float) -> float | None:
        """Seconds until loading may end: at least `loading_min_s` in all and `loading_read_s`
        after the incantations arrived. None while they haven't (no countdown yet)."""
        if self._incantations_at is None:
            return None
        g = self._g
        # The read time starts once the how-to-play screen is over.
        howto_end = now - self._scenes.elapsed(now) + g["howto_s"]
        read_from = max(self._incantations_at, howto_end)
        left = max(
            g["loading_min_s"] - self._scenes.elapsed(now),
            read_from + g["loading_read_s"] - now,
        )
        return max(0.0, left) if left > 1e-9 else 0.0

    def _howto_left(self, now: float) -> float:
        """Seconds left on loading's how-to-play screen (the first `howto_s` of loading)."""
        return max(0.0, self._g["howto_s"] - self._scenes.elapsed(now))

    def _pause_banner(self, now: float) -> str:
        """'STEP INTO VIEW · 12': whole seconds left until the pause abandons the match."""
        since = self._tracking_pause_since
        if since is None:
            return PAUSE_BANNER
        left = max(0.0, self._g["abandon_after_s"] - (now - since))
        return f"{PAUSE_BANNER} · {math.ceil(left - 1e-9)}"

    def _match_over(self, now: float) -> bool:
        """The match ended; after a KO, only once `ko_hold_s` has passed (finishing FX)."""
        result = self._match.result() if self._match is not None else None
        if result is None:
            return False
        if result[1] != "ko":
            return True
        if self._ko_at is None:
            self._ko_at = now
        return now - self._ko_at >= self._g["ko_hold_s"]

    def _winner_slot(self, scene: str) -> int | None:
        """Victory, and the KO hold (the winner is decided at the KO)."""
        if scene == "victory":
            return self._result[0] if self._result else None
        if scene == "fight" and self._match is not None and self._match.result() is not None:
            return self._match.result()[0]
        return None

    def _fill_fallbacks(self) -> None:
        assert self._incantations is not None
        for s in SLOTS:
            inc = self._incantations.setdefault(s, {})
            for sp in self._spells[self._classes[s]]:
                inc.setdefault(sp.id, sp.fallback.get(s, ""))

    def _on_enter(self, now: float) -> list[GameEvent]:
        scene = self._scenes.scene
        events: list[GameEvent] = []
        if scene == "loading":
            self._incantations = None
            self._incantations_at = None
            self._chronicle = None
            self._chronicle_at = None
        elif scene == "fight":
            self._untracked_since.clear()
            self._pause = None
            self._tracking_pause_since = None
            self._reacquire = set()
            self._ko_at = None
            self._match = MatchState(self.cfg, self._names, now, self._classes, self._mic_ok)
            events += self._match.take_events()
        elif scene == "victory":
            assert self._match is not None
            self._result = self._match.result()
            self._match.clear_in_flight()
            self._pause = None
        elif scene == "lobby":
            self._match = None
            self._incantations = None
            self._result = None
        return events

    # -- view -------------------------------------------------------------

    def _build_view(
        self, states: Mapping[int, PlayerState], now: float, events: Sequence[GameEvent]
    ) -> GameView:
        scene = self._scenes.scene
        match = self._match if scene in ("fight", "victory") else None
        camera_down = self._camera_ok is False
        banner: str | None = None
        timer: float | None = None
        howto: float | None = None
        projectiles = ()
        if scene == "boot":
            # Counts down to when boot will really leave: boot_min_s once the camera is ok.
            end = self._g["boot_min_s"] if self._check("camera")[0] else self._g["boot_max_s"]
            timer = max(0.0, end - self._scenes.elapsed(now))
        elif scene == "lobby":
            banner = CAMERA_BANNER if camera_down else self._lobby_banner
        elif scene == "loading":
            banner = CAMERA_BANNER if camera_down else None
            howto = self._howto_left(now) or None
            # No countdown on the how-to-play screen, then None until there is something to read.
            timer = None if howto else self._loading_left(now)
        elif scene == "fight":
            assert match is not None
            if self._pause == "camera":
                banner = CAMERA_BANNER
            elif self._pause == "tracking":
                banner = self._pause_banner(now)
            else:
                banner = match.banner()
            timer = match.time_left
            projectiles = match.projectile_views()
        elif scene == "victory":
            banner = self._victory_banner()
        players = tuple(self._player_view(s, states.get(s), match, scene) for s in SLOTS)
        return GameView(
            scene=scene,
            players=players,  # type: ignore[arg-type]
            projectiles=projectiles,
            banner=banner,
            timer_s=timer,
            howto_s=howto,
            chronicle=self._chronicle if scene == "victory" else None,
            events=tuple(events),
            classes=self._class_views,
            checks=self._check_views(),
            winner_slot=self._winner_slot(scene),
        )

    def _check_views(self) -> tuple[CheckView, ...]:
        extra = tuple(n for n in self._checks if n not in CHECK_NAMES)
        return tuple(CheckView(n, *self._check(n)) for n in CHECK_NAMES + extra)

    def _victory_banner(self) -> str:
        winner = self._result[0] if self._result else None
        return "DRAW" if winner is None else f"{self._names[winner].upper()} WINS"

    def _player_view(
        self, slot: int, state: PlayerState | None, match: MatchState | None, scene: str
    ) -> PlayerView:
        g = self._g
        pm = match.players[slot] if match is not None else None
        class_id = pm.class_id if pm is not None else self._classes[slot]
        charged_id = pm.charge.spell.id if pm is not None and pm.charge is not None else None
        inc = (self._incantations or {}).get(slot, {})
        spells = tuple(self._spell_view(sp, inc, charged_id) for sp in self._spells[class_id])
        in_fight = match is not None and scene == "fight"
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
            effects=match.effect_views(slot) if in_fight else (),
            charge_s=match.charge_left(slot) if in_fight else 0.0,
            cooldown_s=match.cooldown_left(slot) if in_fight else 0.0,
            ready=self._hands[slot].value and scene in ("lobby", "victory"),
            heard=self._heard[slot],
            stats=match.stats(slot) if match is not None else {},
            can_parry=class_id in g["parry_classes"],
            guard_s=match.guard_left(slot) if in_fight else 0.0,
            guard_cooldown_s=match.guard_cooldown_left(slot) if in_fight else 0.0,
            riposte_s=match.riposte_left(slot) if in_fight else 0.0,
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

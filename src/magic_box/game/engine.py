"""Game engine facade: Actions in, GameView and GameEvents out (spec section 8, game/).

Owner: Adetola

Placeholder: always reports a fight scene with full HP and mana, fallback
incantations, and zone/dist/tracking taken from the given states.
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


class Engine:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self._incantations: dict[int, dict[str, str]] = {}
        self._chronicle: str | None = None

    def step(
        self, actions: Sequence[Action], states: Mapping[int, PlayerState], now: float
    ) -> tuple[GameView, list[GameEvent]]:
        # TODO(Adetola): real rules; this placeholder ignores actions and time.
        game = self.cfg["game"]
        players = tuple(self._player_view(slot, states.get(slot)) for slot in (0, 1))
        view = GameView(
            scene="fight",
            players=players,
            projectiles=(),
            banner=None,
            timer_s=game["round_s"],
            chronicle=None,
        )
        return view, []

    def provide_incantations(self, incantations: dict[int, dict[str, str]]) -> None:
        self._incantations = incantations

    def provide_chronicle(self, text: str) -> None:
        self._chronicle = text

    def _player_view(self, slot: int, state: PlayerState | None) -> PlayerView:
        game = self.cfg["game"]
        class_id = game["default_classes"][slot]
        spells = tuple(
            SpellView(
                id=sp["id"],
                name=sp["name"],
                incantation=sp["fallback"][slot],
                cost=sp["cost"],
                charged=False,
            )
            for sp in game["classes"][class_id]["spells"]
        )
        return PlayerView(
            slot=slot,
            name=f"P{slot + 1}",
            class_id=class_id,
            hp=game["hp_max"],
            hp_max=game["hp_max"],
            mana=game["mana_max"],
            mana_max=game["mana_max"],
            spells=spells,
            zone=state.zone if state else "neutral",
            dist=state.root[2] if state else 0.0,
            mic_ok=False,
            tracking_ok=state.tracking_ok if state else False,
        )

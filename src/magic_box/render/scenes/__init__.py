"""Non-fight scene drawing, dispatched on GameView.scene (spec section 10).

Owner: Adetola
"""

from magic_box.core.config import Config
from magic_box.core.contracts import GameView


def draw_scene(surface, view: GameView, cfg: Config) -> None:
    from magic_box.render.scenes import loading, lobby, victory

    drawers = {"lobby": lobby.draw, "loading": loading.draw, "victory": victory.draw}
    drawer = drawers.get(view.scene)
    if drawer is not None:
        drawer(surface, view, cfg)

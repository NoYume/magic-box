"""Scene state machine lobby -> loading -> fight -> victory -> lobby (spec section 8).

Owner: Adetola
Thin placeholder rules (2026-10-24 phase); replace freely.
"""

import string

from magic_box.core.config import Config

NAME_PREFIXES = ("my name is", "i'm", "i am", "this is", "call me", "it's")


def parse_name(text: str, max_chars: int) -> str | None:
    """Turn a spoken phrase into a display name, or None when nothing is left."""
    s = text.lower().replace("’", "'").strip()
    for prefix in NAME_PREFIXES:
        if s == prefix or s.startswith(prefix + " "):
            s = s[len(prefix) :]
            break
    s = "".join(c for c in s if c.isalpha() or c in " -'")
    s = string.capwords(s)[:max_chars].strip()  # capwords: "ada's" -> "Ada's", not "Ada'S"
    return s if any(c.isalpha() for c in s) else None


class SceneMachine:
    """Scene flow. The lobby -> loading start is edge-triggered.

    Entering the lobby disarms the start; any tick where the players are not both ready
    re-arms it, so hands held up from victory don't start the next match. The first lobby
    at startup starts armed.
    """

    def __init__(self, cfg: Config, now: float = 0.0) -> None:
        self.cfg = cfg
        self.scene = "lobby"
        self.entered_at = now
        self._armed = True

    def elapsed(self, now: float) -> float:
        return now - self.entered_at

    def update(
        self, now: float, *, both_ready: bool, incantations_ready: bool, match_over: bool
    ) -> bool:
        g = self.cfg["game"]
        el = self.elapsed(now)
        nxt: str | None = None
        if self.scene == "lobby":
            if not both_ready:
                self._armed = True
            elif self._armed:
                nxt = "loading"
        elif self.scene == "loading":
            if el >= g["loading_min_s"] and incantations_ready:
                nxt = "fight"
        elif self.scene == "fight":
            if match_over:
                nxt = "victory"
        elif self.scene == "victory":
            if el >= g["victory_max_s"] or (el >= g["victory_min_s"] and both_ready):
                nxt = "lobby"
        if nxt is None:
            return False
        self.scene, self.entered_at = nxt, now
        if nxt == "lobby":
            self._armed = False
        return True

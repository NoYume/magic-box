"""Scene state machine boot -> lobby -> loading -> fight -> victory -> lobby (spec section 8).

Owner: Adetola
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


class Hold:
    """A debounced flag: it flips only after the raw input has held the new value for `hold_s`.

    Body tracking on the Jetson flickers pose flags for a frame or two; this keeps a flicker
    from starting a match (up) or re-arming the lobby start (down).
    """

    def __init__(self, hold_s: float) -> None:
        self.hold_s = hold_s
        self.value = False
        self._since: float | None = None

    def update(self, raw: bool, now: float) -> bool:
        if raw == self.value:
            self._since = None
        else:
            if self._since is None:
                self._since = now
            if now - self._since >= self.hold_s:
                self.value, self._since = raw, None
        return self.value


class SceneMachine:
    """Scene flow. The lobby -> loading start is edge-triggered.

    Boot is first: it leaves for the lobby after `boot_min_s` once the camera is ok, or at
    `boot_max_s` whatever the checks say. Entering the lobby from victory disarms the start;
    any tick where the players are not both ready re-arms it, so hands held up from victory
    don't start the next match. The first lobby, after boot, starts armed.

    `entered_at` is stamped by the first `update` unless `now` is given.
    """

    def __init__(self, cfg: Config, now: float | None = None) -> None:
        self.cfg = cfg
        self.scene = "boot"
        self.entered_at = now
        self._armed = True

    def elapsed(self, now: float) -> float:
        return 0.0 if self.entered_at is None else now - self.entered_at

    def update(
        self,
        now: float,
        *,
        both_ready: bool,
        incantations_ready: bool,
        match_over: bool,
        camera_ok: bool = False,
    ) -> bool:
        if self.entered_at is None:
            self.entered_at = now
        g = self.cfg["game"]
        el = self.elapsed(now)
        nxt: str | None = None
        if self.scene == "boot":
            if el >= g["boot_max_s"] or (el >= g["boot_min_s"] and camera_ok):
                nxt = "lobby"
        elif self.scene == "lobby":
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
        if nxt == "lobby":
            self._armed = self.scene == "boot"
        self.scene, self.entered_at = nxt, now
        return True

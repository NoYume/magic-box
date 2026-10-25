"""Scene state machine boot -> lobby -> loading -> fight -> victory -> lobby (spec section 8).

Owner: Adetola
"""

import re
import string

from magic_box.core.config import Config
from magic_box.game.classes import class_keywords, parse_class

# Name prefixes, searched anywhere in the transcript on word boundaries; the first wins.
# "this is" and "it's" are left out on purpose: "this is cool" must not rename anyone.
NAME_PREFIXES: tuple[tuple[str, ...], ...] = (
    ("my", "name", "is"),
    ("my", "name's"),
    ("call", "me"),
    ("i", "am"),
    ("i'm",),
)
_TOKENS = re.compile(r"[^\W\d_]+(?:['-][^\W\d_]+)*|[^\w\s'-]")  # words, or one punctuation


def _tokens(text: str) -> list[str]:
    return _TOKENS.findall(text.lower().replace("’", "'"))


def _is_word(token: str) -> bool:
    return token[0].isalpha()


def _after_prefix(tokens: list[str]) -> int | None:
    """Index just after the first name prefix in `tokens`, or None."""
    for i in range(len(tokens)):
        for prefix in NAME_PREFIXES:
            if tuple(tokens[i : i + len(prefix)]) == prefix:
                return i + len(prefix)
    return None


def _format_name(words: list[str], max_chars: int) -> str | None:
    s = "".join(c for c in " ".join(words) if c.isalpha() or c in " -'")
    s = string.capwords(s)[:max_chars].strip()  # capwords: "ada's" -> "Ada's", not "Ada'S"
    return s if any(c.isalpha() for c in s) else None


def parse_name(text: str, cfg: Config) -> str | None:
    """A display name from one lobby transcript, or None to keep the current name.

    - After a name prefix anywhere ("hi, my name is Ada"): the words that follow, up to the
      first class keyword, punctuation mark or stop word, at most `game.name_max_words`.
    - No prefix: the transcript is a name only if it is 1 to `name_max_words` words and none
      is a class keyword or stop word ("Ada"); chatter ("so what do I do now") is ignored.
    """
    g = cfg["game"]
    stop = {w.lower() for w in g["name_stop_words"]}
    keywords = class_keywords(cfg)
    max_words = g["name_max_words"]
    tokens = _tokens(text)
    after = _after_prefix(tokens)
    if after is not None:
        words: list[str] = []
        for tok in tokens[after:]:
            if not _is_word(tok) or tok in keywords or tok in stop:
                break
            words.append(tok)
            if len(words) == max_words:
                break
    else:
        words = [t for t in tokens if _is_word(t)]
        if not 1 <= len(words) <= max_words or any(w in stop or w in keywords for w in words):
            return None
    return _format_name(words, g["name_max_chars"])


def parse_lobby_speech(text: str, cfg: Config) -> tuple[str | None, str | None]:
    """(name, class id) from one lobby transcript; either may be None (keep the current one).

    "My name is Ada, fire" gives ("Ada", "fire_mage"); "my name is knight" gives
    (None, "holy_knight"); "so what do I do now" gives (None, None).
    """
    return parse_name(text, cfg), parse_class(text, cfg)


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
        chronicle_ready: bool = True,
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
            # Hands up leaves only once the chronicle is shown (Spark takes up to ai.timeout_s).
            if el >= g["victory_max_s"] or (
                el >= g["victory_min_s"] and both_ready and chronicle_ready
            ):
                nxt = "lobby"
        if nxt is None:
            return False
        if nxt == "lobby":
            self._armed = self.scene == "boot"
        self.scene, self.entered_at = nxt, now
        return True

"""Camera liveness and boot self-checks for the game loop. Nothing here blocks.

Owner: Nikhil
"""

import os
import socket
import threading
import time
from collections.abc import Callable, Mapping
from urllib.parse import urlparse

from magic_box.core.config import Config


class CameraWatch:
    """Decides whether camera frames are arriving.

    Not live (fake, replay): always ok. Live: ok while `frame_idx` keeps changing
    and perception runs. Before the first frame it stays ok until `boot_timeout_s`.
    """

    def __init__(
        self,
        stale_s: float,
        boot_timeout_s: float,
        live: bool,
        perception_alive: Callable[[], bool] | None = None,
    ) -> None:
        self._stale_s = stale_s
        self._boot_timeout_s = boot_timeout_s
        self._live = live
        self._perception_alive = perception_alive
        self._started_t: float | None = None
        self._last_idx: int | None = None
        self._last_change_t = 0.0
        self.seen_frame = False

    def update(self, now: float, frame_idx: int | None) -> bool:
        """Feed the newest frame index (None: no frame yet); returns camera ok."""
        if self._started_t is None:
            self._started_t = now
        if frame_idx is not None and frame_idx != self._last_idx:
            self._last_idx = frame_idx
            self._last_change_t = now
            self.seen_frame = True
        if not self._live:
            return True
        if self._perception_alive is not None and not self._perception_alive():
            return False
        if not self.seen_frame:
            return now - self._started_t < self._boot_timeout_s
        return now - self._last_change_t < self._stale_s


PROBE_MARGIN_S = 1.0  # slack on top of the connect timeout before the check reports a timeout


def probe_host(base_url: str, timeout_s: float) -> tuple[bool, str]:
    """TCP connect to the host of `base_url`. Blocking: run it on a thread."""
    parsed = urlparse(base_url)
    host = parsed.hostname
    if not host:
        return False, "bad ai.base_url"
    port = parsed.port or (80 if parsed.scheme == "http" else 443)
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True, host
    except OSError as e:
        return False, f"{host}: {type(e).__name__}"


class BootChecks:
    """`camera`, `network` and `api key` results, handed to `provide(name, ok, detail)`.

    Never logs or reports the key itself.
    """

    def __init__(
        self,
        cfg: Config,
        provide: Callable[[str, bool, str], None],
        env: Mapping[str, str] | None = None,
        probe: Callable[[str, float], tuple[bool, str]] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._clock = clock
        self._started_t = clock()
        self._provide = provide
        self._reported: set[str] = set()
        self._camera_reported: bool | None = None
        ai = cfg["ai"]
        env = os.environ if env is None else env
        self._enabled = bool(ai["enabled"])
        self._key_present = bool(env.get(ai["api_key_env"]))
        self._result: tuple[bool, str] | None = None
        if self._enabled:
            timeout = float(cfg["pipeline"]["network_probe_timeout_s"])
            self._deadline_s = timeout + PROBE_MARGIN_S

            def work() -> None:
                try:
                    self._result = (probe or probe_host)(ai["base_url"], timeout)
                except Exception as e:  # never let the thread die without a result
                    self._result = (False, type(e).__name__)

            threading.Thread(target=work, name="net-probe", daemon=True).start()
        else:
            self._deadline_s = 0.0
            self._result = (True, "ai disabled")

    @property
    def network_ok(self) -> bool | None:
        """None until the probe finished or timed out, then its verdict."""
        self._expire_probe()
        return None if self._result is None else self._result[0]

    def _expire_probe(self) -> None:
        if self._result is None and self._clock() - self._started_t > self._deadline_s:
            # connect()'s timeout does not bound DNS, so give up on the probe ourselves
            self._result = (False, "timeout")

    def poll(self, seen_frame: bool, camera_ok: bool) -> None:
        """Report newly decided checks; call once per tick."""
        if "api key" not in self._reported:
            self._reported.add("api key")
            if not self._enabled:
                self._provide("api key", True, "ai disabled")
            elif self._key_present:
                self._provide("api key", True, "")
            else:
                self._provide("api key", False, "not set")
        self._expire_probe()
        if "network" not in self._reported and self._result is not None:
            self._reported.add("network")
            self._provide("network", *self._result)
        verdict = True if seen_frame else (False if not camera_ok else None)
        if verdict is not None and verdict != self._camera_reported:
            self._camera_reported = verdict
            self._provide("camera", verdict, "" if verdict else "no frames")

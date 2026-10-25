"""Class table access (spec section 8, game/; Appendix A).

Owner: Adetola
Thin placeholder rules (2026-10-24 phase); replace freely.
"""

from magic_box.core.config import Config


def class_ids(cfg: Config) -> list[str]:
    return list(cfg["game"]["classes"])


def class_name(cfg: Config, class_id: str) -> str:
    return cfg["game"]["classes"][class_id]["name"]

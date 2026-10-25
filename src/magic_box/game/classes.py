"""Class table access (spec section 8, game/; Appendix A).

Owner: Adetola
"""

from magic_box.core.config import Config


def class_ids(cfg: Config) -> list[str]:
    """Return configured class ids in display order."""
    return list(cfg["game"]["classes"])


def class_name(cfg: Config, class_id: str) -> str:
    """Return a class display name, raising ValueError for an unknown id."""
    try:
        return str(cfg["game"]["classes"][class_id]["name"])
    except KeyError as exc:
        raise ValueError(f"unknown class {class_id!r}") from exc

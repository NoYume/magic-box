"""Incantation generation with config fallback (spec section 8, ai/).

Owner: Nikhil
"""

from collections.abc import Mapping

from magic_box.ai.spark_client import SparkClient
from magic_box.core.config import Config


def generate_incantations(
    client: SparkClient, classes: Mapping[int, str], cfg: Config
) -> dict[int, dict[str, str]]:
    """slot -> spell_id -> text, validated for length and distance from the other player's set."""
    raise NotImplementedError("TODO(Nikhil): generate incantations with Spark")


def fallback_incantations(classes: Mapping[int, str], cfg: Config) -> dict[int, dict[str, str]]:
    raise NotImplementedError("TODO(Nikhil): fixed incantations from config")

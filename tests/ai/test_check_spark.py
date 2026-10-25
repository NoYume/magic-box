"""Tests for scripts/check_spark.py with a fake OpenAI factory (no network).

Owner: Nikhil
"""

import importlib.util
import json
from pathlib import Path

import pytest

from magic_box.ai.spark_client import SparkClient
from tests.ai.fakes import FakeOpenAI

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_spark.py"
KEY = "sk-secret-123"


def _load():
    spec = importlib.util.spec_from_file_location("check_spark", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _factory(fake, key=KEY):
    return lambda cfg: SparkClient(cfg, env={"META_MODEL_API_KEY": key}, openai_factory=fake)


def _good() -> dict:
    """A valid short reply for the repo config: each spell's exact word count, distinct sets."""
    import copy  # noqa: PLC0415

    from magic_box.core.config import load_config  # noqa: PLC0415

    cfg = load_config(SCRIPT.parents[1] / "config.yaml")
    words = {
        0: ["amber", "brisk", "cedar", "dusty", "eager", "fable"],
        1: ["mesa", "noble", "opal", "prairie", "quartz", "river"],
    }
    out = {}
    for slot, cls in cfg["game"]["default_classes"].items():
        pool = copy.copy(words[slot])
        out[str(slot)] = {
            sp["id"]: " ".join(pool.pop(0) for _ in range(sp["words"]))
            for sp in cfg["game"]["classes"][cls]["spells"]
        }
    return out


GOOD = _good()


class KeyEchoError(Exception):
    status_code = 401


def test_good_reply_prints_latency_model_and_sources(capsys):
    fake = FakeOpenAI(json.dumps(GOOD))
    assert _load().main(["--chronicle"], client_factory=_factory(fake)) == 0
    out = capsys.readouterr().out
    assert "reply model muse-spark-1.3" in out and "incantations: " in out
    assert f"[spark] {GOOD['0']['fireball']}" in out and "chronicle: " in out
    assert fake.calls[0]["reasoning_effort"] == "minimal"


def test_reasoning_effort_override_default_omits_the_field():
    fake = FakeOpenAI(json.dumps(GOOD))
    assert _load().main(["--reasoning-effort", "default"], client_factory=_factory(fake)) == 0
    assert "reasoning_effort" not in fake.calls[0]


def test_failure_exits_1_with_type_and_status_never_the_key(capsys):
    fake = FakeOpenAI(KeyEchoError(f"Incorrect API key provided: {KEY}"))
    assert _load().main([], client_factory=_factory(fake)) == 1
    captured = capsys.readouterr()
    assert "FAIL incantations" in captured.out and "KeyEchoError 401" in captured.out
    assert KEY not in captured.out + captured.err


def test_unusable_reply_exits_1(capsys):
    assert _load().main([], client_factory=_factory(FakeOpenAI("not json"))) == 1
    assert "all fallback" in capsys.readouterr().out


def test_unknown_class_is_a_usage_error(capsys):
    fake = FakeOpenAI(json.dumps(GOOD))
    with pytest.raises(SystemExit) as err:
        _load().main(["--classes", "fire_mage", "frost_mage"], client_factory=_factory(fake))
    assert err.value.code == 2
    assert "invalid choice: 'frost_mage'" in capsys.readouterr().err and fake.calls == []


def test_missing_key_exits_2(capsys):
    assert _load().main([], client_factory=_factory(FakeOpenAI("x"), key="")) == 2
    assert "META_MODEL_API_KEY" in capsys.readouterr().out

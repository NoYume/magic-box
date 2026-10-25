"""Tests for SparkClient (fake OpenAI factory, no network).

Owner: Nikhil
"""

import copy
from pathlib import Path

import pytest

from magic_box.ai.spark_client import SparkClient, SparkUnavailable, describe_error
from magic_box.core.config import load_config, validate
from tests.ai.fakes import FakeOpenAI

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")


def test_complete_uses_config_and_env_key():
    fake = FakeOpenAI("hello")
    client = SparkClient(CFG, env={"META_MODEL_API_KEY": "k"}, openai_factory=fake)
    assert client.last_model is None
    assert client.complete("sys", "usr") == "hello"
    assert fake.kwargs == {
        "base_url": "https://api.meta.ai/v1",
        "api_key": "k",
        "timeout": 8,
        "max_retries": 0,
    }
    call = fake.calls[0]
    assert call["model"] == "muse-spark-1.3" and call["temperature"] == 0.9
    assert call["reasoning_effort"] == "minimal"  # model default timed out live at 8 s
    assert call["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "usr"},
    ]
    assert client.last_model == "muse-spark-1.3"


def test_null_reasoning_effort_is_omitted():
    cfg = copy.deepcopy(CFG)
    cfg["ai"]["reasoning_effort"] = None
    fake = FakeOpenAI("hello")
    SparkClient(cfg, env={"META_MODEL_API_KEY": "k"}, openai_factory=fake).complete("s", "u")
    assert "reasoning_effort" not in fake.calls[0]


def test_reasoning_effort_is_validated():
    cfg = copy.deepcopy(CFG)
    cfg["ai"]["reasoning_effort"] = "none"  # the live API answers 400 for "none"
    assert any(p.startswith("ai.reasoning_effort") for p in validate(cfg))
    cfg["ai"]["reasoning_effort"] = None
    assert validate(cfg) == []


def test_missing_key_or_disabled_raises_unavailable():
    with pytest.raises(SparkUnavailable):
        SparkClient(CFG, env={}, openai_factory=FakeOpenAI("x")).complete("s", "u")
    with pytest.raises(SparkUnavailable):
        SparkClient(CFG, env={"META_MODEL_API_KEY": "  "}, openai_factory=FakeOpenAI("x")).complete(
            "s", "u"
        )
    cfg = copy.deepcopy(CFG)
    cfg["ai"]["enabled"] = False
    fake = FakeOpenAI("x")
    with pytest.raises(SparkUnavailable):
        SparkClient(cfg, env={"META_MODEL_API_KEY": "k"}, openai_factory=fake).complete("s", "u")
    assert fake.kwargs is None


class EchoError(Exception):
    status_code = 401


def test_describe_error_is_type_and_status_only():
    assert describe_error(EchoError("Incorrect API key provided: sk-secret")) == "EchoError 401"
    assert describe_error(TimeoutError("sk-secret")) == "TimeoutError"

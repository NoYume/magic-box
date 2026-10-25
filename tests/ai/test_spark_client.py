"""Tests for SparkClient (fake OpenAI factory, no network).

Owner: Nikhil
"""

import copy
from pathlib import Path

import pytest

from magic_box.ai.spark_client import SparkClient, SparkUnavailable
from magic_box.core.config import load_config
from tests.ai.fakes import FakeOpenAI

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")


def test_complete_uses_config_and_env_key():
    fake = FakeOpenAI("hello")
    client = SparkClient(CFG, env={"META_MODEL_API_KEY": "k"}, openai_factory=fake)
    assert client.complete("sys", "usr") == "hello"
    assert fake.kwargs == {
        "base_url": "https://api.meta.ai/v1",
        "api_key": "k",
        "timeout": 8,
        "max_retries": 0,
    }
    call = fake.calls[0]
    assert call["model"] == "muse-spark-1.3" and call["temperature"] == 0.9
    assert call["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "usr"},
    ]


def test_missing_key_or_disabled_raises_unavailable():
    with pytest.raises(SparkUnavailable):
        SparkClient(CFG, env={}, openai_factory=FakeOpenAI("x")).complete("s", "u")
    cfg = copy.deepcopy(CFG)
    cfg["ai"]["enabled"] = False
    fake = FakeOpenAI("x")
    with pytest.raises(SparkUnavailable):
        SparkClient(cfg, env={"META_MODEL_API_KEY": "k"}, openai_factory=fake).complete("s", "u")
    assert fake.kwargs is None

import pytest


@pytest.fixture(autouse=True)
def no_real_network_probe(monkeypatch):
    """GameLoop builds BootChecks; keep tests off the network."""
    monkeypatch.setattr("magic_box.pipeline.health.probe_host", lambda url, timeout: (True, "test"))

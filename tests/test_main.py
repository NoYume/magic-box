import pytest

from magic_box.main import parse_args, run


def test_fake_mode_runs_headless():
    assert run(["--fake", "--headless", "--max-ticks", "30"]) == 0


def test_record_then_replay_round_trip(tmp_path):
    out = tmp_path / "session"
    assert run(["--fake", "--headless", "--max-ticks", "20", "--record", str(out)]) == 0
    assert (out / "states.jsonl").read_text().strip()
    assert run(["--replay", str(out), "--headless", "--max-ticks", "20"]) == 0


def test_replay_missing_session_exits_2(capsys):
    assert run(["--replay", "nowhere", "--headless", "--max-ticks", "1"]) == 2
    assert "no session" in capsys.readouterr().err.lower()


def test_fake_and_replay_are_exclusive():
    with pytest.raises(SystemExit):
        parse_args(["--fake", "--replay", "x"])


def test_preload_openai_is_safe_without_the_package(monkeypatch):
    import sys

    from magic_box.main import preload_openai

    assert preload_openai() in (True, False)
    monkeypatch.setitem(sys.modules, "openai", None)  # makes `import openai` raise ImportError
    assert preload_openai() is False


def test_openai_is_preloaded_after_the_live_children_start(monkeypatch):
    import pytest

    from magic_box import main

    order = []

    def fake_start_live(cfg):
        order.append("start_live")
        raise RuntimeError("stop here")

    monkeypatch.setattr(main, "start_live", fake_start_live)
    monkeypatch.setattr(main, "preload_openai", lambda: order.append("preload"))
    with pytest.raises(RuntimeError):
        main.run(["--headless", "--max-ticks", "1"])
    assert order == ["start_live"]  # preload runs after start_live, not before

    order.clear()
    assert main.run(["--fake", "--headless", "--max-ticks", "2"]) == 0
    assert order == ["preload"]

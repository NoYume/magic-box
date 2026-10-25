import pytest

from magic_box.main import parse_args, run


def test_fake_mode_runs_headless():
    assert run(["--fake", "--headless", "--max-ticks", "30"]) == 0


def test_missing_replay_exits_2(capsys):
    assert run(["--replay", "nowhere", "--headless", "--max-ticks", "1"]) == 2
    assert "recording directory does not exist" in capsys.readouterr().err.lower()


def test_fake_and_replay_are_exclusive():
    with pytest.raises(SystemExit):
        parse_args(["--fake", "--replay", "x"])

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ["core", "perception", "pipeline", "intent", "voice", "ai", "game", "render", "replay"]


@pytest.mark.parametrize("pkg", PACKAGES)
def test_package_claude_md(pkg):
    text = (ROOT / "src" / "magic_box" / pkg / "CLAUDE.md").read_text()
    for heading in (
        "**Owner:**",
        "## Inputs → Outputs",
        "## Hard rules",
        "## Files",
        "## Test without the Jetson",
        "## Open TODOs",
    ):
        assert heading in text, f"{pkg}/CLAUDE.md missing {heading}"


def test_root_claude_md_maps_every_package():
    text = (ROOT / "CLAUDE.md").read_text()
    assert all(f"{pkg}/" in text for pkg in PACKAGES)
    assert "python -m magic_box --fake" in text


def test_shared_claude_settings():
    allow = json.loads((ROOT / ".claude" / "settings.json").read_text())["permissions"]["allow"]
    assert "Bash(uv run pytest:*)" in allow


@pytest.mark.parametrize("doc", ["README.md", "docs/game-design.md", "docs/hardware.md"])
def test_docs_exist(doc):
    assert (ROOT / doc).read_text().strip()


@pytest.mark.parametrize(
    "doc", ["CLAUDE.md", "README.md", "docs/hardware.md", "src/magic_box/perception/CLAUDE.md"]
)
def test_docs_name_the_zed_x(doc):
    text = (ROOT / doc).read_text()
    assert "ZED X" in text and "ZED 2" not in text

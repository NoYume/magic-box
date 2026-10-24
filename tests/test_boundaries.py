import ast
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[1] / "src" / "magic_box"
FILES = sorted(PKG.rglob("*.py"))


def _rel(p):
    return p.relative_to(PKG).as_posix()


def _imports(path, top_level_only=False):
    tree = ast.parse(path.read_text())
    nodes = tree.body if top_level_only else ast.walk(tree)
    names = set()
    for node in nodes:
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _roots(path, **kw):
    return {n.split(".")[0] for n in _imports(path, **kw)}


@pytest.mark.parametrize("path", FILES, ids=_rel)
def test_boundaries(path):
    rel, roots = _rel(path), _roots(path)
    if "pyzed" in roots:
        assert rel.startswith("perception/"), "pyzed only in perception/"
    if "pygame" in roots:
        assert rel.startswith("render/"), "pygame only in render/"
    if rel.startswith("game/"):
        assert not roots & {"pygame", "pyzed", "cv2"}
    if rel.startswith("core/"):
        project = {n for n in _imports(path) if n.startswith("magic_box.")}
        assert all(n.startswith("magic_box.core") for n in project)
    assert not _roots(path, top_level_only=True) & {"pyzed", "cv2", "sounddevice"}, (
        "lazy-import heavy deps"
    )

import importlib
import pkgutil

import pytest

import magic_box

MODULES = sorted(m.name for m in pkgutil.walk_packages(magic_box.__path__, "magic_box."))


@pytest.mark.parametrize("name", MODULES)
def test_module_imports_and_names_owner(name):
    module = importlib.import_module(name)
    assert module.__doc__ and "Owner:" in module.__doc__

"""Pytest fixtures — isolate every test in a throwaway SWAPIT_HOME and seed it."""
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))


@pytest.fixture()
def swapit_home(tmp_path, monkeypatch):
    home = tmp_path / "swapit"
    monkeypatch.setenv("SWAPIT_HOME", str(home))
    import knowledge
    import state

    state.ensure_dirs()
    knowledge.seed_into_data_root(force=True)
    if not state.load_rooms():
        state.save_rooms(list(state.DEFAULT_ROOMS))
    return home

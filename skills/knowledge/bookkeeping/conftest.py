"""
Suite-wide hermeticity for the entity coherence gate.

The gate is ON by default whenever a TypeSafe key is present, and it fires
inside `promote_item` — which dozens of existing tests call with brand-new
slugs. Without this fixture an operator with `~/.config/typesafe/api_key` on
disk would turn every one of those calls into a live POST to api.typesafe.ai:
the suite would take seconds per item, cost money, and its verdicts would
depend on a remote model. A test run whose result depends on the network is
not a test run.

Applied to EVERY test, opt-out impossible by forgetting. Tests that exercise
the enabled path (tests/test_coherence_gate.py) set the variable back to "1"
in their own fixture, which runs after this one, and replace the transport.

Lives at the skill root rather than in tests/conftest.py so it stays disjoint
from PR #224's append to that file; pytest loads both.
"""
import pytest


@pytest.fixture(autouse=True)
def _coherence_gate_off_by_default(monkeypatch):
    monkeypatch.setenv("BOOKKEEPING_COHERENCE_GATE", "0")
    # Sentinel only this fixture sets: lets tests/test_coherence_hermeticity.py
    # tell "the conftest loaded" from "the developer happens to export =0".
    monkeypatch.setenv("_BOOKKEEPING_COHERENCE_CONFTEST", "loaded")
    yield

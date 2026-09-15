"""Shared pytest fixtures for bookkeeping tests."""
import sys
from pathlib import Path

# Make scripts/ importable as a package
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


import os

import pytest


@pytest.fixture(autouse=True, scope="session")
def _judge_off_by_default():
    """
    The suite must be HERMETIC with respect to the judge.

    `score_item` consults BOOKKEEPING_JUDGE, so an operator with that variable
    exported in their shell turned every in-band item in every test into a
    live `claude -p` call: the suite stalled in test_promoter_quality_gate
    making real network requests, for minutes per item. A test run whose
    duration and result depend on an ambient environment variable is not a
    test run.

    Cleared for the whole session. Tests that exercise the enabled path set it
    explicitly (see test_judge_transport.py), which is unaffected — this only
    removes the ambient default.
    """
    saved = os.environ.pop("BOOKKEEPING_JUDGE", None)
    yield
    if saved is not None:
        os.environ["BOOKKEEPING_JUDGE"] = saved


@pytest.fixture(autouse=True)
def _isolate_knowledge_graph(tmp_path_factory, monkeypatch):
    """
    No test may touch the operator's live knowledge graph.

    `BROOMVA_ROOT`/`ENTITIES_DIR`/`NOTES_DIR` are resolved at IMPORT, so
    setting KG_ROOT in the environment redirects nothing. Two tests were
    running the real pipeline against the real corpus — 119 items, "Promoting
    58 items" — and the only visible symptom was the suite being ~30s slower.

    Per-test monkeypatching was tried and is not enough: deleting one test's
    patch left the suite green and it silently went back to the real graph.
    Isolation that each test opts into is isolation a future edit removes for
    free, so it is applied to EVERY test here and cannot be opted out of by
    forgetting.
    """
    root = tmp_path_factory.mktemp("kg")
    entities = root / "entities"
    notes = root / "notes"
    entities.mkdir(parents=True, exist_ok=True)
    notes.mkdir(parents=True, exist_ok=True)
    import bookkeeping as bk
    monkeypatch.setattr(bk, "BROOMVA_ROOT", root, raising=False)
    monkeypatch.setattr(bk, "ENTITIES_DIR", entities, raising=False)
    monkeypatch.setattr(bk, "NOTES_DIR", notes, raising=False)
    yield

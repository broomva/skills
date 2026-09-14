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

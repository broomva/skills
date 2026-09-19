"""
The suite-wide "coherence gate off" guard is itself load-bearing, so it is
asserted from a module that does NOT opt back in.

The guard lives in the skill-root conftest.py. If that file stops being loaded
(moved, `--confcutdir tests`, a rootdir change, a different invocation
pattern), tests/test_coherence_gate.py keeps passing — it sets the variable to
"1" itself — while every other promote_item test silently starts POSTing to
api.typesafe.ai on any machine with a key file. CI has no key, so the failure
is invisible there by construction; this is the only place it shows.
Positive control, run by hand: `pytest --confcutdir tests` makes this fail.
"""
import os

import bookkeeping


def test_root_conftest_forces_the_coherence_gate_off():
    # The sentinel is set by the conftest fixture and nothing else, so a
    # developer shell that happens to export BOOKKEEPING_COHERENCE_GATE=0
    # cannot make this pass while the conftest is unloaded.
    assert os.environ.get("_BOOKKEEPING_COHERENCE_CONFTEST") == "loaded", (
        "skills/knowledge/bookkeeping/conftest.py did not load — the suite is "
        "no longer hermetic with respect to the coherence transport")
    assert os.environ.get(bookkeeping.COHERENCE_GATE_ENV) == "0"
    assert bookkeeping.coherence_gate_enabled() is False

"""skill_evals — trigger-eval harness for description-triggered skills (BRO-2005).

Three modules, acyclic:

    transcript.py  parse the agent CLI's stream-json NDJSON into a queryable object
    checks.py      CHECK_REGISTRY — deterministic per-case outcome predicates
    runner.py      workspace isolation, Runner protocol (live/replay), grading, CLI

Kept import-light on purpose: ``runner.py`` puts ``scripts/`` on ``sys.path`` when
executed directly, and an ``__init__`` that imported submodules would run before
that shim lands.
"""

__all__ = ["checks", "runner", "transcript"]

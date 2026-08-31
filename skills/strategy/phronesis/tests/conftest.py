"""Shared pytest fixtures.

The autouse root sandbox below is the most important thing in this file.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

import pytest

# The two roots the extraction pipeline writes to when nobody overrides them.
# Both point into the operator's real environment.
_LIVE_ROOTS = (
    Path.home() / "broomva" / "research" / "entities",
    Path.home() / ".config" / "phronesis" / "extraction-queue",
)


@pytest.fixture(autouse=True)
def _sandbox_phronesis_roots(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Point the extraction roots at a temp dir for EVERY test. Autouse.

    Without this the suite writes into the operator's real knowledge graph and
    review queue. Not through an explicit call — `Engagement.emit()` fires
    `_fire_extraction_hook()` on ENGAGEMENT_CONCLUDED with no kwargs, so merely
    CONSTRUCTING a concluded fixture engagement promotes entity pages and
    queue records. Eight test files do that.

    Measured, sandbox off vs on, over two test files:
        entity pages written to the live graph:  0  vs  0
        queue records written to the live queue: 44 vs  0

    The entity count is 0 in BOTH columns only because the BRO-2404 clobber
    guard refuses to overwrite pages that already exist; on a machine whose
    graph is empty it writes them. The queue has no such guard, which is why
    the queue is the honest detector.

    `pipeline.py`'s module docstring claimed "Tests set them to `tmp_path` so
    the suite never touches the real knowledge graph." Nothing did. This is
    that sentence made true.
    """
    root = tmp_path_factory.mktemp("phronesis-sandbox")
    monkeypatch.setenv("PHRONESIS_ENTITY_GRAPH_ROOT", str(root / "entities"))
    monkeypatch.setenv("PHRONESIS_EXTRACTION_QUEUE_ROOT", str(root / "queue"))


@pytest.fixture(autouse=True)
def _fail_if_a_test_wrote_to_a_live_root():
    """Positive control for the sandbox: assert BOTH live roots stay untouched.

    A sandbox that silently stopped working looks exactly like a passing suite,
    so this has to be able to fail — and it is pinned by a mutation: disabling
    `_sandbox_phronesis_roots` turns the suite red through this fixture.

    Watching only `research/entities/` was not enough, and the reason is worth
    recording: re-extraction skips pages that already exist, so on a populated
    machine the entity root shows zero writes even with the sandbox off. The
    guard masks the leak. A watchdog that saw only the guarded root was
    unfalsifiable.
    """

    def snapshot() -> dict[Path, float]:
        out: dict[Path, float] = {}
        for r in _LIVE_ROOTS:
            if not r.exists():
                continue
            for f in r.rglob("*"):
                if f.is_file():
                    with contextlib.suppress(OSError):
                        out[f] = f.stat().st_mtime
        return out

    before = snapshot()
    yield
    touched = [p for p, m in snapshot().items() if before.get(p) != m]
    assert not touched, (
        f"test wrote to a LIVE phronesis root ({len(touched)} file(s)): "
        f"{[str(p) for p in touched[:5]]}"
    )


@pytest.fixture
def sample_citation_kwargs() -> dict[str, Any]:
    return {
        "kind": "evidence",
        "ref": "interview:cfo-2026-05-01:Q3",
        "excerpt": "We see ~12K Tier-1 tickets per month.",
        "confidence": "high",
    }

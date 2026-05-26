"""Shared pytest fixtures."""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture
def sample_citation_kwargs() -> dict[str, Any]:
    return {
        "kind": "evidence",
        "ref": "interview:cfo-2026-05-01:Q3",
        "excerpt": "We see ~12K Tier-1 tickets per month.",
        "confidence": "high",
    }

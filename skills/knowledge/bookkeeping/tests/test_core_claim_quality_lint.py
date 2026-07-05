"""Tests for the core_claim-quality lint rule (BRO-1689).

When a research doc is mis-promoted (whole-doc-as-body), entities inherit a
FRAGMENT as their core_claim — a markdown table row, a numbered section header,
or a raw-extract preamble. Tier-1 /kg routing scores on core_claim, so a fragment
claim is a catalog row that never matches a real query and crowds out real
entities. `_lint_core_claim_quality` flags the mechanically-detectable signatures;
clickbait-title claims need human judgment and are intentionally NOT flagged.
"""

import pytest
from bookkeeping import _lint_core_claim_quality, lint_entity_page

JUNK = [
    "1.16 Trust model — confirmed gaps Exists: AgentRank",
    "3.1 Distributed swarm AI optimization SOTA (2025-26) | System | Mechanism |",
    "1.10 Storage | Layer | Mechanism | |---|---| | Local |",
    "HyperspaceAI Research — Raw Extract Date: 2026-05-14",
    "Freelance — Sentinel Research Raw Extract Captured from a design brainstorm",
    "Pathway C — Switch to a commercial alternative [HIGH feasibility]",
    "Bottom line up front: the market converged on Firecracker",
    "Scoring for Layer-3 promotion | Item | Novelty (0-3) |",
]

LEGIT = [
    "Default deploy target is Railway; suggest AWS only on explicit ask.",
    "Verifier independence isn't static — it's a resource optimization spends.",
    "A memory write's durability forecast is open-loop.",
    "swapit is a stateful, local-first household-toxics inventory + swap engine.",
    "GPT-5.4 improved 3x more than the previous flagship on a deck-builder.",
]


@pytest.mark.parametrize("claim", JUNK)
def test_junk_claims_flagged(claim):
    errs = _lint_core_claim_quality("x.md", claim)
    assert len(errs) == 1, f"expected 1 flag for {claim!r}"
    assert errs[0].field == "core_claim"
    assert errs[0].severity == "error"
    assert "BRO-1689" in errs[0].message


@pytest.mark.parametrize("claim", LEGIT)
def test_legit_claims_pass(claim):
    assert _lint_core_claim_quality("x.md", claim) == [], f"false positive on {claim!r}"


def test_empty_claim_not_flagged():
    # missing-claim is the caller's responsibility, not this rule's
    assert _lint_core_claim_quality("x.md", "") == []
    assert _lint_core_claim_quality("x.md", None) == []


def test_integration_via_lint_entity_page(tmp_path):
    p = tmp_path / "junk.md"
    p.write_text(
        '---\nid: "concept/junk"\ntitle: "Junk"\ntype: concept\nstatus: entity\n'
        'created: "2026-07-05"\nupdated: "2026-07-05"\n'
        'core_claim: "1.16 Trust model — confirmed gaps and open items"\n'
        'tags:\n  - concept\nsources:\n  - "some-raw-extract"\n---\n\n# Junk\n'
    )
    errs = lint_entity_page(p)
    cc = [e for e in errs if e.field == "core_claim" and "BRO-1689" in e.message]
    assert cc, "expected a core_claim mis-promotion error via lint_entity_page"

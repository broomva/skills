"""Regression set for the ALL-CAPS banner rule (BRO-2526).

Measured against the live corpus 2026-09-13, the rule fired on 7 entity pages and
was WRONG on 6 of them. Every false positive was acronym prose that the tokenizer
could not see as separated:

    SKILL.md, CLAUDE.md, AGENTS.md   ->  `md` is 2 chars; `[A-Za-z]{3,}` never
                                         matched it, so it could not break the run
    RSICS = RCS                      ->  same, for `=`
    NASDAQ: MELI                     ->  same, for `:`
    FIX/DERIVED/CAPTURED             ->  same, for `/`
    OPC UA SCADA                     ->  genuinely space-separated; separated from
                                         a real banner only by POSITION

An error-severity rule with 1-in-7 precision is worse than no rule: it pressures
authors into degrading correct claims to silence it, which is exactly what nearly
happened to six of these pages.
"""

import pytest
from bookkeeping import _claim_is_allcaps_banner


# Real banner artifacts. These are lifted headers and must stay caught.
BANNERS = [
    "VERIFIED VERDICTS (2026-07-20) authoritative list",
    "VERDICT: SURVIVES AS a formal contribution",
    "REFRAME REQUIRED for the harness",
    "PARTIAL YES on the harness question overall",
    "VERIFIED VERDICTS",
]

# Legitimate claims from the live corpus that the old rule rejected.
ACRONYM_PROSE = [
    pytest.param(
        "Barcelona industrial-automation firm (est. 2007) distributing atvise pure-web "
        "OPC UA SCADA across Spain/LatAm, with a training arm (VITC).", id="vester/OPC-UA-SCADA"),
    pytest.param(
        "LatAm's largest e-commerce/fintech (NASDAQ: MELI, $28.9B 2025 revenue); 8 "
        "connections and repeated Meli recruiting threads.", id="mercado/NASDAQ-MELI"),
    pytest.param(
        "Self-evolving skill engine with three-mode FIX/DERIVED/CAPTURED loop and "
        "GDPVal benchmark.", id="openspace/FIX-DERIVED-CAPTURED"),
    pytest.param(
        "RSICS = RCS applied to RSI: self-improvement is a control problem decided by "
        "verifier independence.", id="rsics/RSICS-eq-RCS"),
    pytest.param(
        "skills.sh is the agent-skills install CLI; its SKILL.md YAML parser silently "
        "rejects multi-quoted list items.", id="skills-sh/SKILL.md-YAML"),
    pytest.param(
        "Users routinely cannot distinguish Claude Code's Hooks, Skills, Plugins, "
        "SKILL.md, CLAUDE.md and AGENTS.md.", id="claude-code/our-own-governance-files"),
    pytest.param(
        "UK-HQ'd (London) software-engineering + data/AI consultancy, ~250+ distributed "
        "experts (UK/US/Europe/LATAM/UAE).", id="parser/LATAM-UAE"),
    pytest.param("The AI SDK v6 ships a tool loop.", id="short-acronyms"),
    pytest.param("GPT-5.4 beats the prior flagship on HTML rendering.", id="GPT-HTML"),
]


@pytest.mark.parametrize("claim", BANNERS)
def test_real_banners_still_caught(claim):
    assert _claim_is_allcaps_banner(claim), f"recall lost on: {claim!r}"


@pytest.mark.parametrize("claim", ACRONYM_PROSE)
def test_acronym_prose_is_not_a_banner(claim):
    assert not _claim_is_allcaps_banner(claim), f"false positive on: {claim!r}"


def test_punctuation_breaks_a_run():
    """The tokenizer bug in one assertion: identical words, separated vs not."""
    assert _claim_is_allcaps_banner("ALPHA BRAVO leads this claim")      # space: a run
    assert not _claim_is_allcaps_banner("ALPHA/BRAVO leads this claim")  # slash: not


def test_position_separates_banner_from_embedded_acronyms():
    """The same shouted pair is a banner at the front and prose in the middle."""
    assert _claim_is_allcaps_banner("SIGMA DELTA is the reported status of the run")
    assert not _claim_is_allcaps_banner(
        "The pipeline converts each frame before the SIGMA DELTA stage runs downstream")

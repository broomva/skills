"""Every shipped prompt set validates (BRO-2663).

CI validated two sets by name (checkit, arc), so four of the thirteen shipped
sets failed the runner's own validation while CI stayed green: three carried
cases with no ``expected_checks``, and legal-readiness used a
``should_trigger`` / ``should_not_trigger`` list format the runner does not read.
This module validates every ``skills/**/evals/prompts.json`` on disk, so a new
or edited set is checked without anyone adding it to a list.

The validator is also run on the two broken shapes, so a green result here
cannot come from a validator that accepts everything.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from skill_evals import runner as R

REPO = Path(__file__).resolve().parents[2]
PROMPT_SETS = sorted((REPO / "skills").rglob("evals/prompts.json"))

#: The four sets repaired in BRO-2663. Named so that a glob that stops finding
#: them fails here instead of quietly validating fewer sets.
REPAIRED = {"unslop", "resume", "audit-harness-usage", "legal-readiness"}


def _rel(p: Path) -> str:
    return str(p.relative_to(REPO))


def test_the_glob_finds_every_repaired_set():
    assert PROMPT_SETS, "no prompt sets found; every test below would be vacuous"
    found = {p.parent.parent.name for p in PROMPT_SETS}
    assert REPAIRED <= found, f"not found: {sorted(REPAIRED - found)}"


@pytest.mark.parametrize("path", PROMPT_SETS, ids=_rel)
def test_shipped_prompt_set_validates(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    errors, _warnings = R.validate_prompt_set(data)
    assert errors == [], f"{_rel(path)}:\n  " + "\n  ".join(errors)


def test_validator_rejects_a_case_with_no_checks():
    data = {
        "skill": "demo",
        "version": 1,
        "cases": [{"id": "golden-01", "prompt": "do the thing", "should_trigger": True,
                   "expected_checks": []}],
    }
    errors, _ = R.validate_prompt_set(data)
    assert any("'expected_checks' is empty" in e for e in errors), errors


def test_validator_rejects_the_trigger_list_format():
    data = {"skill": "demo", "should_trigger": ["do the thing"], "should_not_trigger": ["other"]}
    errors, _ = R.validate_prompt_set(data)
    assert any("'cases' must be a non-empty list" in e for e in errors), errors

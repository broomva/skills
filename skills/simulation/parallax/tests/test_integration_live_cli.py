"""Integration: drive the REAL `parallax` binary and feed its output to the core.

The unit tests build their own status documents and error envelopes, which makes
them a test of the script against MY IDEA of what Parallax emits. That is the
vacuity this file exists to close: here the documents come out of the actual
binary, so a change in the CLI's shape breaks the skill rather than silently
making it wrong.

Skipped when `parallax` is not on PATH (`bun link` in this skill's `runtime/` puts
it there). SKIPPED is reported honestly rather than passing on an absent binary.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[1]
SCRIPT = SKILL / "scripts" / "parallax_next.py"

spec = importlib.util.spec_from_file_location("parallax_next", SCRIPT)
assert spec and spec.loader
pn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pn)

pytestmark = pytest.mark.skipif(
    shutil.which("parallax") is None,
    reason="`parallax` not on PATH — run `bun link` in this skill's `runtime/`",
)


@pytest.fixture
def workspace():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "ledger").mkdir()
        (p / "ledger" / "stock.csv").write_text("sku,qty\nA1,7\n", encoding="utf-8")
        (p / "README.md").write_text("notes\n", encoding="utf-8")
        yield p


def px(workspace: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["parallax", *args], cwd=workspace, capture_output=True, text=True
    )


def test_a_fresh_workspace_reports_IDLE_and_routes_to_propose(workspace):
    r = px(workspace, "status", "--json")
    assert r.returncode == 0, r.stderr
    step = pn.next_step(pn._unwrap(json.loads(r.stdout)))
    assert step is not None and step[0] == "parallax propose"


def test_after_proposing_the_real_status_routes_to_answer(workspace):
    assert px(workspace, "propose", "--json").returncode == 0
    r = px(workspace, "status", "--json")
    step = pn.next_step(pn._unwrap(json.loads(r.stdout)))
    assert step is not None
    assert step[0].startswith("parallax answer")
    # The ref in the suggested command must be the one the CLI actually printed,
    # not a placeholder: a suggestion the caller cannot paste is not a suggestion.
    assert "<ref>" not in step[0]


def test_a_real_refusal_carries_a_code_this_skill_has_a_remedy_for(workspace):
    """The important one: an UNPLANNED real refusal must not be unrecognised."""
    r = px(workspace, "run", "--json")
    assert r.returncode == 2, "expected a typed refusal, got %r" % r.returncode
    err = pn._unwrap(json.loads(r.stderr))
    assert err["code"] == "NO_ACCEPTED_ONTOLOGY"
    assert pn.remedy(err["code"]) is not None


def test_the_reconciliation_gate_fires_and_is_recognised(workspace):
    """The refusal most likely to be misread as a bug, produced for real."""
    p = px(workspace, "propose", "--json")
    ref = json.loads(p.stdout)["value"]["ref"]
    px(workspace, "answer", "--proposal", ref, "--answer", "1=pieces")
    r = px(workspace, "accept", "--proposal", ref, "--by", "tester", "--json")
    assert r.returncode == 2
    err = pn._unwrap(json.loads(r.stderr))
    assert err["code"] == "RECONCILIATION_UNACKNOWLEDGED"
    fix = pn.remedy(err["code"])
    assert fix is not None and "TELL THE HUMAN FIRST" in fix
    # The remedy names a field that is actually present on the real error.
    assert "unmappedFromContext" in err.get("detail", {})


def test_the_whole_flow_lands_on_RAN_and_routes_to_receipt(workspace):
    p = px(workspace, "propose", "--json")
    ref = json.loads(p.stdout)["value"]["ref"]
    px(workspace, "answer", "--proposal", ref, "--answer", "1=pieces")
    a = px(workspace, "accept", "--proposal", ref, "--by", "tester",
           "--acknowledge-unmapped", "--json")
    assert a.returncode == 0, a.stderr
    assert px(workspace, "run", "--json").returncode == 0
    r = px(workspace, "status", "--json")
    step = pn.next_step(pn._unwrap(json.loads(r.stdout)))
    assert step is not None and step[0] == "parallax receipt"


def test_answering_does_not_accept(workspace):
    """The capability `accept --answer` cannot express, verified end to end."""
    p = px(workspace, "propose", "--json")
    ref = json.loads(p.stdout)["value"]["ref"]
    px(workspace, "answer", "--proposal", ref, "--answer", "1=pieces")
    s = json.loads(px(workspace, "status", "--json").stdout)["value"]
    assert s["accepted"] == [], "answering must not accept"
    assert s["state"] == "READY"


def test_every_command_the_skill_documents_exists_in_the_binary(workspace):
    """Guards the SKILL.md table against a rename in the CLI."""
    out = px(workspace, "help").stdout
    for command in (
        "propose", "render", "parse-reply", "answer",
        "accept", "run", "receipt", "status", "reject",
    ):
        assert f"\n  {command}" in out, f"`{command}` is documented but not in `parallax help`"

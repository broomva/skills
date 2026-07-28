"""Integration tests — the CLI as a user actually invokes it.

The unit suite exercises the analysis functions directly. These drive the real
entrypoint as a subprocess, which is the only thing that covers argparse
wiring, the render() path, JSON emission, and exit codes.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "context_audit.py"

GOVERNANCE_FIXTURE = """# Example Repo

## Rules
Never commit directly to main. You must always open a pull request.
Enforced by `hooks/gate.sh` on every write.

## Style
Prefer bun over npm. Write code that reads like the surrounding code.

## Comments
Do not add documentation comments to generated files.

## Reviewing
Leave documentation comments as appropriate for the reader.

## Layout
src/
tests/
docs/
scripts/
"""


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
    )


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "CLAUDE.md").write_text(GOVERNANCE_FIXTURE)
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    (hooks / "gate.sh").write_text("#!/bin/sh\nexit 0\n")
    return tmp_path


def test_cli_renders_markdown_report(repo):
    r = run(str(repo / "CLAUDE.md"), "--repo-root", str(repo), "--budget", "50")
    assert r.returncode == 0, r.stderr
    assert "# Context audit" in r.stdout
    assert "**Budget**" in r.stdout
    assert "Sections by weight" in r.stdout
    # The evidence-only disclaimer is load-bearing: it is what stops a reader
    # treating the table as a delete list.
    assert "Evidence only" in r.stdout


def test_cli_reports_over_budget(repo):
    r = run(str(repo / "CLAUDE.md"), "--repo-root", str(repo), "--budget", "10")
    assert "over by" in r.stdout


def test_cli_reports_within_budget(repo):
    r = run(str(repo / "CLAUDE.md"), "--repo-root", str(repo), "--budget", "100000")
    assert "→ within" in r.stdout


def test_cli_json_is_valid_and_structured(repo):
    r = run(str(repo / "CLAUDE.md"), "--repo-root", str(repo), "--json")
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert set(data) >= {
        "tokenizer",
        "budget",
        "files",
        "polarity_total",
        "rules_ratio",
        "sections",
        "duplication",
        "contradictions",
        "disclosure",
    }
    assert data["polarity_total"]["prohibition"] >= 1


def test_cli_surfaces_the_planted_contradiction(repo):
    r = run(str(repo / "CLAUDE.md"), "--repo-root", str(repo), "--json")
    topics = {c["topic"] for c in json.loads(r.stdout)["contradictions"]}
    assert "documentation" in topics


def test_cli_marks_the_hook_backed_section_anchored(repo):
    r = run(str(repo / "CLAUDE.md"), "--repo-root", str(repo), "--json")
    rules = next(
        s for s in json.loads(r.stdout)["sections"] if s["heading"] == "Rules"
    )
    assert rules["anchored_candidate"] is True
    assert rules["rules_ratio"] == 1.0


def test_cli_flags_the_derivable_layout_section(repo):
    r = run(str(repo / "CLAUDE.md"), "--repo-root", str(repo), "--json")
    layout = next(
        s for s in json.loads(r.stdout)["sections"] if s["heading"] == "Layout"
    )
    assert layout["derivable"] is True


def test_cli_directory_walk(repo):
    r = run(str(repo), "--repo-root", str(repo), "--json")
    assert r.returncode == 0, r.stderr
    assert len(json.loads(r.stdout)["files"]) == 1


def test_cli_prompt_mode_text(repo):
    r = run("--prompt-text", "Never do X. You must always do Y instead.")
    assert r.returncode == 0, r.stderr
    assert "# Prompt audit" in r.stdout
    assert "rules-ratio 1.0" in r.stdout


def test_cli_prompt_mode_file(tmp_path):
    p = tmp_path / "prompt.md"
    p.write_text("Prefer clarity over cleverness. Consider the reader first.")
    r = run("--prompt-file", str(p), "--json")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["rules_ratio"] == 0.0


def test_cli_missing_path_exits_nonzero():
    r = run("/nonexistent/path/xyz.md")
    assert r.returncode == 2
    assert "no such path" in r.stderr


def test_cli_no_args_prints_help():
    r = run()
    assert r.returncode == 2
    assert "usage:" in r.stdout.lower() or "usage:" in r.stderr.lower()


def test_cli_audits_its_own_skill_md():
    """Dogfood — the skill must survive its own audit."""
    skill_md = SCRIPT.parents[1] / "SKILL.md"
    r = run(str(skill_md), "--repo-root", str(SCRIPT.parents[1]), "--json")
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    # It preaches judgement over prohibition; it had better practise it.
    assert data["rules_ratio"] < 0.75, (
        f"unhobble's own SKILL.md is {data['rules_ratio']} hard rules"
    )


def test_cli_own_skill_md_defers_to_references():
    """The disclosure flag must actually fire, then report deferral.

    Forced under threshold rather than relying on SKILL.md's natural size — at
    its current ~1.9k tokens the default 2500 threshold produces an empty
    disclosure list, and asserting over an empty list proves nothing.
    """
    root = SCRIPT.parents[1]
    r = run(
        str(root / "SKILL.md"),
        "--repo-root",
        str(root),
        "--split-threshold",
        "500",
        "--json",
    )
    disclosure = json.loads(r.stdout)["disclosure"]
    assert len(disclosure) == 1, "expected the disclosure check to fire"
    assert disclosure[0]["defers"] is True
    assert disclosure[0]["has_reference_dir"] is True

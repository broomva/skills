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


# ------------------------------------------------------ exit-code gates (P20 #4)


def test_default_run_never_fails_however_bad_the_surface(tmp_path):
    """No gate flag => a report, not a judge. This is the documented default."""
    p = tmp_path / "CLAUDE.md"
    p.write_text("# evil\nNever do this. Never do that. You must always obey.\n")
    r = run(str(p), "--repo-root", str(tmp_path), "--budget", "1")
    assert r.returncode == 0


def test_max_rules_ratio_gate_fails_on_pure_prohibition(tmp_path):
    p = tmp_path / "CLAUDE.md"
    p.write_text("# evil\nNever do this. Never do that. You must always obey.\n")
    r = run(str(p), "--repo-root", str(tmp_path), "--max-rules-ratio", "0.6")
    assert r.returncode == 1
    assert "rules-ratio" in r.stderr


def test_max_rules_ratio_gate_passes_judgement_framed_surface(tmp_path):
    p = tmp_path / "CLAUDE.md"
    p.write_text(
        "# calm\nPrefer bun over npm. Write code that reads like the surrounding "
        "code. Default to a worktree unless the change is a typo.\n"
    )
    r = run(str(p), "--repo-root", str(tmp_path), "--max-rules-ratio", "0.6")
    assert r.returncode == 0, r.stderr


def test_fail_over_budget_gate(tmp_path):
    p = tmp_path / "CLAUDE.md"
    p.write_text("# a\n" + "some governance prose here. " * 50)
    assert run(str(p), "--repo-root", str(tmp_path), "--budget", "1").returncode == 0
    over = run(
        str(p), "--repo-root", str(tmp_path), "--budget", "1", "--fail-over-budget"
    )
    assert over.returncode == 1
    assert "over budget" in over.stderr


@pytest.mark.parametrize(
    "threshold,expected_rc",
    [("0.75", 0), ("0.749", 1), ("0.8", 0), ("0.7", 1)],
)
def test_max_rules_ratio_boundary_is_strict_greater(tmp_path, threshold, expected_rc):
    # A ratio EQUAL to the threshold must pass; `>` vs `>=` was unpinned.
    p = tmp_path / "CLAUDE.md"
    p.write_text(
        "# s\nNever do A here. Never do B here. You must do C here.\n"
        "Prefer D over E here.\n"
    )
    probe = json.loads(run(str(p), "--repo-root", str(tmp_path), "--json").stdout)
    assert probe["rules_ratio"] == 0.75, "fixture must sit exactly on the boundary"
    r = run(str(p), "--repo-root", str(tmp_path), "--max-rules-ratio", threshold)
    assert r.returncode == expected_rc


def test_fail_over_budget_is_refused_in_prompt_mode():
    """The round-1 MAJOR-4 shape, in the other mode.

    A prompt report has no budget key, so the gate silently defaulted to pass —
    a CI step wired this way would be green forever. Refused outright instead.
    """
    r = run("--prompt-text", "You must never merge red.", "--budget", "1", "--fail-over-budget")
    assert r.returncode == 2
    assert "does not apply in prompt mode" in r.stderr


def test_empty_prompt_text_is_audited_not_treated_as_missing():
    r = run("--prompt-text", "")
    assert r.returncode == 0, r.stderr
    assert "Prompt audit" in r.stdout


def test_own_ci_gate_invocation_passes():
    """The exact command test-unhobble.yml runs. If this fails, CI fails."""
    root = SCRIPT.parents[1]
    r = run(
        str(root / "SKILL.md"),
        "--repo-root",
        str(root),
        "--budget",
        "3000",
        "--fail-over-budget",
        "--max-rules-ratio",
        "0.6",
    )
    assert r.returncode == 0, r.stderr


# --------------------------------------------------------- error paths (P20 #10/11)


def test_directory_with_no_surfaces_is_an_error_not_a_clean_bill(tmp_path):
    empty = tmp_path / "nothing"
    empty.mkdir()
    r = run(str(empty))
    assert r.returncode == 2
    assert "no CLAUDE.md" in r.stderr
    assert "within" not in r.stdout


def test_prompt_file_missing_is_a_clean_error():
    r = run("--prompt-file", "/nonexistent/nope.md")
    assert r.returncode == 2
    assert "cannot read prompt file" in r.stderr
    assert "Traceback" not in r.stderr


def test_prompt_file_directory_is_a_clean_error(tmp_path):
    r = run("--prompt-file", str(tmp_path))
    assert r.returncode == 2
    assert "cannot read prompt file" in r.stderr
    assert "Traceback" not in r.stderr


def test_prompt_file_non_utf8_does_not_crash(tmp_path):
    p = tmp_path / "prompt.md"
    p.write_bytes(b"Never do \xff\xfe this thing here at all.\n")
    r = run("--prompt-file", str(p))
    assert r.returncode == 0, r.stderr
    assert "Prompt audit" in r.stdout


# -------------------------------------------------- truncation honesty (P20 #8)


def test_contradiction_truncation_is_disclosed(tmp_path):
    pairs = "\n".join(
        f"## Sec{i}\nNever use the widget{i} adapter here.\n"
        f"## Alt{i}\nUse the widget{i} adapter as appropriate.\n"
        for i in range(30)
    )
    p = tmp_path / "CLAUDE.md"
    p.write_text(pairs)
    data = json.loads(
        run(str(p), "--repo-root", str(tmp_path), "--json", "--max-contradictions", "5").stdout
    )
    assert len(data["contradictions"]) == 5
    # Must be the TRUE total, not the cap. Asserting merely ">5" passed even
    # when the count was itself silently clipped to the 20 default.
    assert data["contradictions_total"] >= 30, (
        "contradictions_total must count every candidate, not the emitted slice"
    )

    rendered = run(str(p), "--repo-root", str(tmp_path)).stdout
    assert "showing" in rendered and "of" in rendered


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

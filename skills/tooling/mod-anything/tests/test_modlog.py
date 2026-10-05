"""Tests for scripts/modlog.py — the journal, the route record and the stall breaker."""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "modlog.py"
spec = importlib.util.spec_from_file_location("modlog", SCRIPT)
modlog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(modlog)


def run(d: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), "--dir", str(d), *args],
                          capture_output=True, text=True)


@pytest.fixture
def journal(tmp_path: Path) -> Path:
    assert run(tmp_path, "init", "--target", "Obsidian 1.9", "--idea", "show claims").returncode == 0
    return tmp_path


def test_init_writes_journal_and_state(journal: Path):
    assert (journal / "MODLOG.md").read_text().startswith("# MODLOG — Obsidian 1.9")
    state = json.loads((journal / ".modlog.json").read_text())
    assert state["idea"] == "show claims" and state["routes"] == []


def test_init_refuses_to_overwrite(journal: Path):
    r = run(journal, "init", "--target", "x", "--idea", "y")
    assert r.returncode == 2 and "already exists" in r.stderr


def test_commands_refuse_without_journal(tmp_path: Path):
    r = run(tmp_path, "route", "--rung", "2", "--name", "n", "--reason", "r")
    assert r.returncode == 2 and "init" in r.stderr


def test_route_rejects_unknown_rung_and_empty_reason(journal: Path):
    assert run(journal, "route", "--rung", "6", "--name", "n", "--reason", "r").returncode == 2
    assert run(journal, "route", "--rung", "2", "--name", "n", "--reason", "  ").returncode == 2
    assert run(journal, "route", "--rung", "passthrough", "--name", "bridge", "--reason", "two apps").returncode == 0


def test_ok_requires_a_route_and_existing_evidence(journal: Path):
    shot = journal / "shot.png"
    shot.write_bytes(b"png")
    r = run(journal, "ok", "--step", "loads", "--evidence", "shot.png")
    assert r.returncode == 2 and "no route" in r.stderr
    run(journal, "route", "--rung", "2", "--name", "plugin API", "--reason", "sanctioned")
    r = run(journal, "ok", "--step", "loads", "--evidence", "missing.png")
    assert r.returncode == 2 and "missing.png" in r.stderr
    r = run(journal, "ok", "--step", "loads")
    assert r.returncode == 2 and "artifact" in r.stderr
    assert run(journal, "ok", "--step", "loads", "--evidence", "shot.png").returncode == 0
    assert "`shot.png`" in (journal / "MODLOG.md").read_text()


def test_breaker_stalls_on_third_repeat_with_rerank_text(journal: Path):
    run(journal, "route", "--rung", "5", "--name", "rebuild crypto", "--reason", "no key")
    assert run(journal, "fail", "--sig", "Decrypt fails").returncode == 0
    assert run(journal, "fail", "--sig", "  decrypt FAILS. ").returncode == 0
    r = run(journal, "fail", "--sig", "decrypt fails")
    assert r.returncode == 3
    assert "STALL" in r.stdout and "Can the original simply be run?" in r.stdout
    assert "- STALL:" in (journal / "MODLOG.md").read_text()
    assert len(json.loads((journal / ".modlog.json").read_text())["stalls"]) == 1


def test_breaker_does_not_merge_different_failures(journal: Path):
    run(journal, "route", "--rung", "3", "--name", "inject", "--reason", "r")
    for sig in ("timeout", "crash on load", "timeout 2"):
        assert run(journal, "fail", "--sig", sig).returncode == 0


def test_new_route_resets_the_count(journal: Path):
    run(journal, "route", "--rung", "5", "--name", "rebuild", "--reason", "r")
    run(journal, "fail", "--sig", "same")
    run(journal, "fail", "--sig", "same")
    run(journal, "route", "--rung", "2", "--name", "run the original", "--reason", "re-ranked")
    assert run(journal, "fail", "--sig", "same").returncode == 0
    assert run(journal, "fail", "--sig", "same").returncode == 0
    assert run(journal, "fail", "--sig", "same").returncode == 3


def test_limit_is_configurable_and_validated(journal: Path):
    run(journal, "route", "--rung", "4", "--name", "hook", "--reason", "r")
    assert run(journal, "fail", "--sig", "x", "--limit", "1").returncode == 3
    assert run(journal, "fail", "--sig", "y", "--limit", "0").returncode == 2


def test_normalize_sig_is_conservative():
    assert modlog.normalize_sig("  Foo   Bar.  ") == "foo bar"
    assert modlog.normalize_sig("error 401") != modlog.normalize_sig("error 403")


def test_note_scaffold_fails_lint_until_filled(journal: Path):
    (journal / "e.txt").write_text("log")
    run(journal, "route", "--rung", "2", "--name", "plugin API", "--reason", "sanctioned")
    run(journal, "ok", "--step", "command runs", "--evidence", "e.txt")
    run(journal, "fail", "--sig", "manifest rejected")
    note = journal / "note.md"
    assert run(journal, "note", "--out", str(note)).returncode == 0
    r = run(journal, "lint-note", str(note))
    assert r.returncode == 1 and "unfilled placeholders" in r.stdout
    text = note.read_text()
    # The agent decides each journal file on purpose: here it cites a copy beside the note.
    text = re.sub(rf"{re.escape(modlog.TODO)}: e\.txt is in the working folder[^\n]*", "`e.txt`", text)
    filled = text.replace(f"{modlog.TODO}: ", "").replace(modlog.TODO, "x")
    note.write_text(filled)
    r = run(journal, "lint-note", str(note))
    assert r.returncode == 0, r.stdout
    assert run(journal, "note", "--out", str(note)).returncode == 2  # no silent overwrite


GOOD_NOTE = """# T: idea

## Versions
- App 1.2

## Route
1. Rung 2 (sanctioned API): plugin

## What it really does
It reads the vault.

## Verification
- loads: `evidence/shot.png`

## Gotchas
1. Plugin missing → manifest id mismatch → match folder name to id

## Envelope
- Rung: 2
- Disclosure: none found
"""


def test_lint_accepts_a_complete_note():
    assert modlog.lint_note(GOOD_NOTE) == []


@pytest.mark.parametrize("mutation,expect", [
    (lambda t: t.replace("## Versions", "## Version"), "missing section: ## Versions"),
    (lambda t: t.replace("`evidence/shot.png`", "it worked"), "cites no evidence"),
    (lambda t: t.replace("1. Plugin missing → manifest id mismatch → match folder name to id",
                         "1. Plugin missing, fixed it"), "symptom → cause → fix"),
    (lambda t: t.replace("1. Plugin missing → manifest id mismatch → match folder name to id", "none"),
     "no numbered items"),
    (lambda t: t.replace("1. Rung 2 (sanctioned API): plugin", "1. we used the plugin"), "does not name a rung"),
])
def test_lint_catches_each_defect(mutation, expect):
    problems = modlog.lint_note(mutation(GOOD_NOTE))
    assert any(expect in p for p in problems), problems


def test_lint_note_cli_exit_codes(tmp_path: Path):
    good = tmp_path / "good.md"
    good.write_text(GOOD_NOTE)
    r = run(tmp_path, "lint-note", str(good))
    assert r.returncode == 1 and "does not exist" in r.stdout  # cited evidence is missing
    (tmp_path / "evidence").mkdir()
    (tmp_path / "evidence" / "shot.png").write_bytes(b"png")
    assert run(tmp_path, "lint-note", str(good)).returncode == 0
    assert run(tmp_path, "lint-note", str(tmp_path / "nope.md")).returncode == 2


# --- added after the first dogfood run (BRO-2816 friction report) -------------------

def test_log_needs_no_route_and_checks_evidence(journal: Path):
    assert run(journal, "log", "--text", "recon: Obsidian is Electron, plugin API").returncode == 0
    r = run(journal, "log", "--text", "restore", "--evidence", "nope.txt")
    assert r.returncode == 2 and "nope.txt" in r.stderr
    assert "- NOTE (" in (journal / "MODLOG.md").read_text()


def test_supersedes_marks_the_old_route_and_validates(journal: Path):
    run(journal, "route", "--rung", "3", "--name", "devtools", "--reason", "installer too old (guess)")
    assert run(journal, "route", "--rung", "2", "--name", "cli", "--reason", "x", "--supersedes", "9").returncode == 2
    assert run(journal, "route", "--rung", "2", "--name", "cli", "--reason", "sampled: keychain prompt",
               "--supersedes", "1").returncode == 0
    state = json.loads((journal / ".modlog.json").read_text())
    assert state["routes"][0]["superseded_by"] == 2
    note = journal / "n.md"
    run(journal, "note", "--out", str(note))
    assert "(superseded by #2)" in note.read_text()


def test_fail_keeps_the_original_text_for_humans(journal: Path):
    run(journal, "route", "--rung", "2", "--name", "api", "--reason", "r")
    run(journal, "fail", "--sig", "First SIGTERM leaves the App running")
    assert "First SIGTERM leaves the App running" in (journal / "MODLOG.md").read_text()
    note = journal / "n.md"
    run(journal, "note", "--out", str(note))
    assert "1. First SIGTERM leaves the App running →" in note.read_text()


def test_stall_text_names_sampling_a_hang(journal: Path):
    run(journal, "route", "--rung", "2", "--name", "api", "--reason", "r")
    r = run(journal, "fail", "--sig", "hang", "--limit", "1")
    assert r.returncode == 3 and "sample <pid> 1" in r.stdout


def test_note_leaves_journal_evidence_as_a_decision_not_a_citation(journal: Path):
    # Journal evidence lives in the working folder, which never ships. The scaffold must not
    # cite it as a path (a ../ citation would lint clean and point outside the ship tree).
    (journal / "evidence").mkdir()
    (journal / "evidence" / "shot.png").write_bytes(b"png")
    run(journal, "route", "--rung", "2", "--name", "api", "--reason", "r")
    run(journal, "ok", "--step", "renders", "--evidence", "evidence/shot.png")
    note = journal / "ship" / "field-notes" / "app" / "n.md"
    run(journal, "note", "--out", str(note))
    text = note.read_text()
    assert "`" not in text.split("## Verification")[1].split("##")[0]
    assert f"{modlog.TODO}: evidence/shot.png is in the working folder" in text


def test_lint_note_refuses_citations_outside_the_root(tmp_path: Path):
    ship = tmp_path / "ship"
    (tmp_path / "evidence").mkdir()
    (tmp_path / "evidence" / "dom.html").write_text("<p>logged-in page</p>")
    note = ship / "field-notes" / "app" / "n.md"
    note.parent.mkdir(parents=True)
    escape = GOOD_NOTE.replace("`evidence/shot.png`", "`../../../evidence/dom.html`")
    note.write_text(escape)
    r = run(tmp_path, "lint-note", str(note), "--root", str(ship))
    assert r.returncode == 1 and "outside ship/" in r.stdout, r.stdout
    absolute = GOOD_NOTE.replace("`evidence/shot.png`", f"`{tmp_path / 'evidence' / 'dom.html'}`")
    note.write_text(absolute)
    r = run(tmp_path, "lint-note", str(note), "--root", str(ship))
    assert r.returncode == 1 and "absolute path" in r.stdout, r.stdout
    # Without --root and with no SKILL.md above, the root is the note's own folder.
    note.write_text(escape)
    assert "outside" in run(tmp_path, "lint-note", str(note)).stdout


def test_lint_note_blocks_an_embargoed_disclosure():
    embargoed = GOOD_NOTE.replace("- Disclosure: none found", "- Disclosure: embargoed until the vendor answers")
    assert any("under embargo" in p for p in modlog.lint_note(embargoed))
    missing = GOOD_NOTE.replace("- Disclosure: none found\n", "")
    assert any("no 'Disclosure:' line" in p for p in modlog.lint_note(missing))


def test_an_unwritable_working_folder_exits_2_not_1(tmp_path: Path):
    ro = tmp_path / "ro"
    ro.mkdir()
    ro.chmod(0o500)
    try:
        r = run(ro, "init", "--target", "T", "--idea", "I")
        assert r.returncode == 2 and "cannot read or write" in r.stderr, (r.returncode, r.stderr)
        assert "Traceback" not in r.stderr
    finally:
        ro.chmod(0o700)


def test_envelope_rung_ignores_subgoal_and_superseded_routes(journal: Path):
    run(journal, "route", "--rung", "2", "--name", "plugin API", "--reason", "the mod")
    run(journal, "route", "--rung", "3", "--name", "lab devtools", "--reason", "lab only", "--subgoal", "lab")
    note = journal / "n.md"
    run(journal, "note", "--out", str(note))
    assert "- Rung: 2\n" in note.read_text()


def test_lint_joins_wrapped_gotchas():
    wrapped = GOOD_NOTE.replace(
        "1. Plugin missing → manifest id mismatch → match folder name to id",
        "1. Plugin missing after install → the folder name differs\n   from the manifest id → rename the folder to the id")
    assert modlog.lint_note(wrapped) == []


def test_lint_flags_cited_evidence_that_does_not_exist(tmp_path: Path):
    (tmp_path / "evidence").mkdir()
    note = GOOD_NOTE  # cites `evidence/shot.png`
    assert any("does not exist" in p for p in modlog.lint_note(note, base=tmp_path))
    (tmp_path / "evidence" / "shot.png").write_bytes(b"png")
    assert modlog.lint_note(note, base=tmp_path) == []
    # a command in backticks is not a path
    cmd = note.replace("`evidence/shot.png`", "`evidence/shot.png` via `obsidian dev:dom`")
    assert modlog.lint_note(cmd, base=tmp_path) == []


def test_lint_accepts_paths_relative_to_the_skill_root(tmp_path: Path):
    skill = tmp_path / "skill"
    (skill / "examples" / "x" / "evidence").mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: s\ndescription: d\n---\n")
    (skill / "examples" / "x" / "evidence" / "shot.png").write_bytes(b"png")
    notes = skill / "field-notes" / "app"
    notes.mkdir(parents=True)
    note = notes / "n.md"
    note.write_text(GOOD_NOTE.replace("`evidence/shot.png`", "`examples/x/evidence/shot.png`"))
    assert run(tmp_path, "lint-note", str(note)).returncode == 0
    note.write_text(GOOD_NOTE.replace("`evidence/shot.png`", "`examples/x/evidence/gone.png`"))
    r = run(tmp_path, "lint-note", str(note))
    assert r.returncode == 1 and "gone.png" in r.stdout


# --- added after P20 round 1 (BRO-2816) ---------------------------------------------

def test_stall_text_rechecks_the_rules_first(journal: Path):
    run(journal, "route", "--rung", "2", "--name", "api", "--reason", "r")
    r = run(journal, "fail", "--sig", "x", "--limit", "1")
    assert r.returncode == 3 and "must pass the skill's Rules again" in r.stdout


@pytest.mark.parametrize("a,b", [
    ("café timeout", "café timeout"),      # NFD vs NFC (macOS hands back NFD)
    ("ＥＲＲＯＲ", "error"),                       # full-width letters
    ("same​", "same"),                       # zero-width space
    ("Straße", "STRASSE"),                        # casefold, not lower
])
def test_normalize_sig_unifies_unicode_forms(a: str, b: str):
    assert modlog.normalize_sig(a) == modlog.normalize_sig(b)


def test_lowered_limit_persists_for_the_journal(journal: Path):
    run(journal, "route", "--rung", "2", "--name", "api", "--reason", "r")
    assert run(journal, "fail", "--sig", "x", "--limit", "2").returncode == 0
    r = run(journal, "fail", "--sig", "x")  # no --limit: the stored 2 applies
    assert r.returncode == 3


def test_evidence_must_be_a_file_and_not_the_journal(journal: Path):
    run(journal, "route", "--rung", "2", "--name", "api", "--reason", "r")
    (journal / "d").mkdir()
    for ev in (".", "d", "MODLOG.md", ".modlog.json"):
        r = run(journal, "ok", "--step", "s", "--evidence", ev)
        assert r.returncode == 2, ev


def test_a_route_cannot_be_superseded_twice(journal: Path):
    run(journal, "route", "--rung", "3", "--name", "a", "--reason", "r")
    assert run(journal, "route", "--rung", "2", "--name", "b", "--reason", "r", "--supersedes", "1").returncode == 0
    r = run(journal, "route", "--rung", "2", "--name", "c", "--reason", "r", "--supersedes", "1")
    assert r.returncode == 2 and "already superseded" in r.stderr


def test_corrupt_or_wrong_inputs_exit_2_not_a_traceback(journal: Path, tmp_path: Path):
    (journal / ".modlog.json").write_text("{not json")
    r = run(journal, "status")
    assert r.returncode == 2 and "unreadable" in r.stderr
    assert run(tmp_path, "lint-note", str(tmp_path)).returncode == 2           # a directory
    bad = tmp_path / "latin1.md"
    bad.write_bytes("caf\xe9".encode("latin-1"))
    assert run(tmp_path, "lint-note", str(bad)).returncode == 2


def test_note_out_must_not_be_a_directory(journal: Path):
    run(journal, "route", "--rung", "2", "--name", "api", "--reason", "r")
    (journal / "notes").mkdir()
    r = run(journal, "note", "--out", str(journal / "notes"), "--force")
    assert r.returncode == 2 and "directory" in r.stderr


def test_lint_checks_evidence_paths_with_spaces(tmp_path: Path):
    note = GOOD_NOTE.replace("`evidence/shot.png`", "`evidence/run 2.png`")
    assert any("run 2.png" in p for p in modlog.lint_note(note, base=tmp_path))
    (tmp_path / "evidence").mkdir()
    (tmp_path / "evidence" / "run 2.png").write_bytes(b"png")
    assert modlog.lint_note(note, base=tmp_path) == []
    cmd = note.replace("`evidence/run 2.png`", "`evidence/run 2.png` via `cd tools/x && make`")
    assert modlog.lint_note(cmd, base=tmp_path) == []  # a command is not a path


def test_lint_reports_duplicate_sections():
    dup = GOOD_NOTE + "\n## Verification\n- again: `other.png`\n"
    assert any("duplicate section: ## Verification" in p for p in modlog.lint_note(dup))


# --- added after P20 round 2 (BRO-2816) ---------------------------------------------

def test_wrong_shape_journal_exits_2(journal: Path):
    for bad in ('{"routes":[{"n":1}],"failures":5}', '{"routes":[],"steps":[]}', '[]'):
        (journal / ".modlog.json").write_text(bad)
        r = run(journal, "status")
        assert r.returncode == 2 and "not a modlog journal" in r.stderr, bad


def test_the_stall_limit_cannot_be_raised(journal: Path):
    run(journal, "route", "--rung", "2", "--name", "api", "--reason", "r")
    r = run(journal, "fail", "--sig", "x", "--limit", "99")
    assert r.returncode == 2 and "re-rank" in r.stderr
    assert run(journal, "fail", "--sig", "x", "--limit", "2").returncode == 0
    r = run(journal, "fail", "--sig", "x", "--limit", "3")  # back up: refused
    assert r.returncode == 2


def test_markdown_link_evidence_is_checked(tmp_path: Path):
    note = GOOD_NOTE.replace("`evidence/shot.png`", "[screenshot](evidence/missing.png)")
    assert any("missing.png" in p for p in modlog.lint_note(note, base=tmp_path))
    url = GOOD_NOTE.replace("`evidence/shot.png`", "[docs](https://example.com/a.png)")
    assert modlog.lint_note(url, base=tmp_path) == []


@pytest.mark.parametrize("tok,expect", [
    ("evidence/shot.png", "evidence/shot.png"),
    ("evidence/run 2.png", "evidence/run 2.png"),
    ("evidence/run.txt:12", "evidence/run.txt"),
    ("evidence/run 2.mp3", "evidence/run 2.mp3"),
    ("sample 4242 1 > evidence/run.txt", None),
    ("screencapture -x evidence/shot.png", None),
    ("n/a", None),
    ("text/html", None),
    ("github.com/obsidianmd/obsidian-api", None),
    ("evidence/*.png", None),
    ("https://example.com/x.png", None),
])
def test_evidence_path_heuristic(tok, expect):
    assert modlog._evidence_path(tok) == expect


def test_concurrent_fails_do_not_lose_counts(journal: Path):
    run(journal, "route", "--rung", "2", "--name", "api", "--reason", "r")
    procs = [subprocess.Popen([sys.executable, str(SCRIPT), "--dir", str(journal), "fail",
                               "--sig", f"sig {i}", "--limit", "3"], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL) for i in range(12)]
    for p in procs:
        p.wait()
    assert len(json.loads((journal / ".modlog.json").read_text())["failures"]) == 12
    assert not (journal / ".modlog.lock").exists()


def test_malformed_route_in_an_otherwise_valid_journal_exits_2(journal: Path):
    state = json.loads((journal / ".modlog.json").read_text())
    for bad_route in ({"n": 1}, {"n": 2, "rung": "2", "name": "x"}, {"n": 1, "rung": "9", "name": "x"}):
        state["routes"] = [bad_route]
        (journal / ".modlog.json").write_text(json.dumps(state))
        r = run(journal, "status")
        assert r.returncode == 2 and "not a modlog journal" in r.stderr, bad_route


@pytest.mark.parametrize("patch", [
    {"failures": [{}]},
    {"failures": [{"sig": "x", "route": "1", "count": 1}]},
    {"steps": [{"step": "s", "evidence": "e.png", "route": 1}]},
    {"limit": "abc"}, {"limit": None}, {"limit": 0}, {"limit": 99}, {"limit": True},
    {"steps": [{"step": "s", "evidence": [1], "route": 1}]},
    {"logs": [{"text": "t", "evidence": [""]}]},
    {"target": ""},
    {"routes": [{"n": 1, "rung": "2", "name": "a", "reason": "r", "superseded_by": "zz"}]},
])
def test_every_entry_and_the_limit_are_validated(journal: Path, patch: dict):
    run(journal, "route", "--rung", "2", "--name", "api", "--reason", "r")
    state = json.loads((journal / ".modlog.json").read_text())
    state.update(patch)
    (journal / ".modlog.json").write_text(json.dumps(state))
    for cmd in (["status"], ["fail", "--sig", "x"], ["note", "--out", str(journal / "n.md")]):
        r = run(journal, *cmd)
        assert r.returncode == 2 and "not a modlog journal" in r.stderr, (patch, cmd, r.stderr)


# --- fresh round 2 (BRO-2816) -------------------------------------------------------------

def test_init_refuses_a_working_folder_inside_a_git_repo(tmp_path: Path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    work = repo / "examples" / "run"
    r = run(work, "init", "--target", "T", "--idea", "I")
    assert r.returncode == 2 and "inside the git repo" in r.stderr
    assert run(work, "init", "--target", "T", "--idea", "I", "--in-repo").returncode == 0


def test_lint_note_root_resolves_citations_in_the_tree_you_will_ship(tmp_path: Path):
    ship = tmp_path / "ship"
    (ship / "examples" / "x" / "evidence").mkdir(parents=True)
    (ship / "examples" / "x" / "evidence" / "shot.png").write_bytes(b"png")
    note = ship / "field-notes" / "app" / "n.md"
    note.parent.mkdir(parents=True)
    note.write_text(GOOD_NOTE.replace("`evidence/shot.png`", "`examples/x/evidence/shot.png`"))
    assert run(tmp_path, "lint-note", str(note)).returncode == 1          # no SKILL.md above: unresolved
    assert run(tmp_path, "lint-note", str(note), "--root", str(ship)).returncode == 0


@pytest.mark.parametrize("patch", [
    {"done": 123},
    {"steps": [{"step": "s", "evidence": ["e.png"], "route": 9}]},
    {"failures": [{"sig": "x", "route": 1, "count": 0}]},
])
def test_cross_references_in_the_journal_are_validated(journal: Path, patch: dict):
    run(journal, "route", "--rung", "2", "--name", "api", "--reason", "r")
    state = json.loads((journal / ".modlog.json").read_text())
    state.update(patch)
    (journal / ".modlog.json").write_text(json.dumps(state))
    r = run(journal, "status")
    assert r.returncode == 2 and "not a modlog journal" in r.stderr


def test_a_run_with_no_failure_scaffolds_none_hit_and_lints_clean(journal: Path):
    # Dogfood (Codex, 2026-10-05): with no failure recorded, a template demanding a numbered
    # gotcha made the agent invent three. "None hit" is the honest entry and must lint clean.
    run(journal, "route", "--rung", "1", "--name", "alias", "--reason", "documented config")
    note = journal / "n.md"
    run(journal, "note", "--out", str(note))
    text = note.read_text()
    assert modlog.NONE_HIT in text
    gotchas = text.split("## Gotchas")[1].split("##")[0]
    assert modlog.lint_note(GOOD_NOTE.replace(
        "1. Plugin missing → manifest id mismatch → match folder name to id", gotchas.strip())) == []

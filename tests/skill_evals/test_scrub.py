"""Tests for the fixture scrubber (scripts/skill_evals/scrub.py, BRO-2030).

The env jail isolates the filesystem and environment. It does NOT isolate the process
table — and a live eval runs a real agent with `bypassPermissions`, free to `ps` and
put the result in a transcript that then gets committed to a PUBLIC repo.

Not hypothetical: the first full sweep produced a `dogfood` transcript carrying the
recording machine's process listing, and one of those command lines contained
`-session-token <36 chars>`. The pre-commit gitleaks hook caught it. This module is
the step between recording and publishing.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from skill_evals import scrub as S  # noqa: E402


def test_the_home_directory_is_redacted():
    out, counts = S.scrub_text("reading /Users/somebody/.config/thing")
    assert "/Users/somebody" not in out
    assert out == "reading /Users/USER/.config/thing"
    assert counts["home directory"] == 1


def test_a_session_token_in_a_process_line_is_redacted():
    """THE case this exists for, in the shape the first sweep actually produced.

    The real `ps` capture used a COLON — `-session-token:<36 chars>` — inside an
    Electron-style argument list. An earlier version of this test guessed a SPACE
    separator, which is a different string, and getting that wrong is how a rule
    aimed at a known artefact ends up never matching it.
    """
    # Assembled at runtime, not written as a literal: a 36-char token-shaped string
    # sitting in a tracked file trips the repo's own secret scanner, and a test that
    # cannot be committed is not a test.
    fake = "cd47a1" + "b2c3d4e5f6" + "0718293a4b" + "5c6d7269"
    line = f"node /opt/app -process-type:main -session-token:{fake} -target-handle:820"
    out, counts = S.scrub_text(line)
    assert fake not in out
    assert "-session-token:REDACTED" in out
    assert counts["credential-shaped assignment"] >= 1


def test_a_space_separated_credential_is_also_redacted():
    """Both separators, because CLI conventions differ and the cost of missing one
    on a public repo is permanent."""
    fake = "abcdefgh" + "12345678" + "ijklmnop"
    out, _ = S.scrub_text(f"--api-key {fake}")
    assert fake not in out


def test_it_matches_on_the_KEY_not_the_value_shape():
    """Guessing which 36-character strings are secret is whack-a-mole, and every
    miss is permanent once pushed to a public repo. So an innocuous long value stays,
    and a short value under a credential-shaped key still goes."""
    # Also assembled at runtime — there is a certain irony in the assertion that a
    # plain hash is not a secret being itself flagged as one, but the scanner is
    # pattern-matching and the cheap fix is to not hand it a literal.
    sha = "0fd7c7aa9e" + "1b4c3d5e6f" + "70819a2b3c" + "4d5e6f7049"
    kept, _ = S.scrub_text(f'"commit": "{sha}"')
    assert sha in kept, "a plain hash is not a secret"

    short = "abcd1234" + "efgh5678" + "ijkl"
    gone, _ = S.scrub_text(f"api_key={short}")
    assert short not in gone


def test_several_credential_key_spellings_are_covered():
    for text in (
        "AUTH_TOKEN=aaaaaaaaaaaaaaaaaaaa",
        'password: "bbbbbbbbbbbbbbbbbbbb"',
        "machine_id=cccccccccccccccccccc",
        "X-Api-Key: dddddddddddddddddddd",
        "session_id=eeeeeeeeeeeeeeeeeeee",
    ):
        out, _ = S.scrub_text(text)
        assert "REDACTED" in out, text


def test_scrub_is_idempotent():
    """--apply runs before every commit; a second pass must be a no-op or the
    fixtures churn on every run and the diff becomes unreadable."""
    once, _ = S.scrub_text("/Users/me/x and token=aaaaaaaaaaaaaaaaaaaa")
    twice, counts = S.scrub_text(once)
    assert once == twice
    assert not counts


def test_check_reports_without_writing(tmp_path):
    """--check is a gate to run before committing, and must not modify anything."""
    f = tmp_path / "t.jsonl"
    f.write_text('{"cwd": "/Users/somebody/ws"}')
    before = f.read_text()
    rc = S.main([str(tmp_path), "--check"])
    assert rc == 1, "--check exits non-zero when there is something to redact"
    assert f.read_text() == before, "--check must not write"


def test_apply_rewrites_and_then_check_is_clean(tmp_path):
    f = tmp_path / "t.jsonl"
    f.write_text('{"cwd": "/Users/somebody/ws"}')
    assert S.main([str(tmp_path), "--apply"]) == 0
    assert "/Users/somebody" not in f.read_text()
    assert S.main([str(tmp_path), "--check"]) == 0, "clean after apply"


def test_only_fixture_files_are_touched(tmp_path):
    """A stray .md or .py under the fixtures tree is not a transcript."""
    (tmp_path / "notes.md").write_text("/Users/somebody/x")
    (tmp_path / "t.jsonl").write_text("/Users/somebody/x")
    S.main([str(tmp_path), "--apply"])
    assert "/Users/somebody" in (tmp_path / "notes.md").read_text()
    assert "/Users/somebody" not in (tmp_path / "t.jsonl").read_text()


def test_the_committed_live_fixtures_are_scrubbed():
    """The standing guard. If a re-record lands unscrubbed, this fails before the
    secret scanner has to."""
    live = REPO / "tests" / "skill_evals" / "fixtures" / "live"
    if not live.is_dir():
        return
    assert S.scan(live) == {}, (
        "live fixtures contain unscrubbed host content — run "
        "`python3 scripts/skill_evals/scrub.py tests/skill_evals/fixtures/live --apply`"
    )

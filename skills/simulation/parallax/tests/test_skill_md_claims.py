"""SKILL.md's own claims about itself must be true.

This file exists because the Tests section shipped wrong. It told a reader to run
`python3 -m pytest skills/tooling/parallax/tests/` -- the repo-relative path at the
time -- which does not resolve from an install (`~/.claude/skills/parallax/` has no
`skills/tooling/` prefix), and it claimed 29 tests when there were 36.

That path reads as stale now, because the skill has since moved to
`skills/simulation/parallax/`. It is left as it was ON PURPOSE: this paragraph is a
record of a defect that shipped, and silently updating the quoted string to the
current path would make the record describe a mistake nobody made. The defect was
never about which directory was named; it was about naming a repo-relative path in
a document read from an install.

It was found by installing the skill from skills.sh and following its own
instructions -- not by any test, because no test read the document. Same class as
the README defect the runtime already had, which is guarded by
`runtime/test/docs.test.ts`. This is that guard, over the skill's own document.

The counts here are deliberately derived from pytest's own collector rather than
hardcoded twice. A number asserted against a copy of itself is not a measurement.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
SKILL_MD = SKILL / "SKILL.md"


def _text() -> str:
    return SKILL_MD.read_text(encoding="utf-8")


def _collected(target: str) -> int:
    """How many tests pytest actually collects under `target`, via --collect-only."""
    r = subprocess.run(
        [sys.executable, "-m", "pytest", target, "--collect-only", "-q"],
        cwd=SKILL,
        capture_output=True,
        text=True,
    )
    m = re.search(r"(\d+) tests? collected", r.stdout + r.stderr)
    assert m, f"could not read a collected count from:\n{r.stdout}\n{r.stderr}"
    return int(m.group(1))


def test_the_documented_pytest_path_resolves_from_the_skill_root():
    """The exact path in the fenced block must exist relative to SKILL.md.

    An install has no `skills/simulation/` prefix, so a path carrying one is a
    command that fails for every reader who installed the skill rather than cloning
    it.
    """
    blocks = re.findall(r"```bash\n(.*?)```", _text(), re.S)
    targets = re.findall(r"python3 -m pytest (\S+)", "\n".join(blocks))
    assert targets, "SKILL.md documents no pytest invocation"
    for t in targets:
        assert (SKILL / t).exists(), (
            f"SKILL.md tells the reader to run pytest on {t!r}, "
            f"which does not exist relative to the skill root ({SKILL})"
        )


def test_every_documented_script_invocation_resolves():
    """`python3 <path>` in SKILL.md must point at a file this skill ships.

    The pytest-path test above checked one KIND of documented path and this one was
    the kind it missed: SKILL.md told the reader to run
    `python3 scripts/parallax_next.py` from the target workspace, where that file
    does not exist. Worse than a plain failure -- the obvious repair is to cd into
    the skill directory, which makes the SKILL DIRECTORY the workspace Parallax
    reads, and that succeeds on the wrong context instead of failing.

    Third instance of one class in this skill's short life (a monorepo-only pytest
    path, a stale test count, this). So the assertion is over EVERY python3
    invocation in the document, not the ones already known to be wrong.
    """
    blocks = re.findall(r"```bash\n(.*?)```", _text(), re.S)
    body = "\n".join(blocks)
    # Resolve the documented ways of naming the skill root back to this directory.
    body = body.replace('"$HOME/.claude/skills/parallax"', str(SKILL))
    body = body.replace("$SKILL", str(SKILL))
    targets = [
        t.strip('"').strip("'")
        for t in re.findall(r"python3\s+((?!-m\b)[^\s|;&]+)", body)
    ]
    assert targets, "SKILL.md documents no direct python3 script invocation"
    for t in targets:
        path = Path(t) if Path(t).is_absolute() else (SKILL / t)
        assert path.exists(), (
            f"SKILL.md tells the reader to run `python3 {t}`, which does not exist "
            f"(resolved to {path})"
        )


def test_the_core_section_does_not_use_a_bare_relative_script_path():
    """A relative script path is wrong HERE specifically, and silently so.

    These commands run in the workspace being read, not in the skill directory, so
    `python3 scripts/...` cannot resolve -- and the repair a reader reaches for
    (cd into the skill) quietly changes which directory Parallax reports on.
    """
    for block in re.findall(r"```bash\n(.*?)```", _text(), re.S):
        for m in re.finditer(r"python3\s+((?!-m\b)[^\s|;&]+)", block):
            tok = m.group(1)
            assert not tok.startswith("scripts/"), (
                f"`python3 {tok}` is relative; address the script from the skill root "
                "(e.g. \"$SKILL/scripts/...\") so it resolves from the workspace"
            )


def test_the_documented_test_count_matches_what_pytest_collects():
    """The `# N passed` comment has to be N."""
    m = re.search(r"python3 -m pytest \S+ -q\s+#\s*(\d+) passed", _text())
    assert m, "SKILL.md's pytest line does not carry a `# N passed` count"
    claimed = int(m.group(1))
    assert claimed == _collected("tests/"), (
        f"SKILL.md claims {claimed} tests; pytest collects {_collected('tests/')}"
    )


def test_the_hermetic_and_live_split_adds_up():
    """`(N hermetic + M live-CLI)` must match the two files' real counts."""
    m = re.search(r"\((\d+) hermetic \+ (\d+) live-CLI\)", _text())
    assert m, "SKILL.md does not state the hermetic/live split"
    hermetic, live = int(m.group(1)), int(m.group(2))
    total = _collected("tests/")
    live_real = _collected("tests/test_integration_live_cli.py")
    # "hermetic" is defined as everything that is NOT the live-CLI file, so adding
    # another hermetic file moves the number without redefining the term. The first
    # draft pinned it to one filename and went red the moment this file existed --
    # which is the guard working, but on the wrong invariant.
    assert live == live_real, f"SKILL.md says {live} live-CLI tests; pytest collects {live_real}"
    assert hermetic == total - live_real, (
        f"SKILL.md says {hermetic} hermetic; pytest collects {total - live_real}"
    )


def test_the_remedy_count_claimed_in_prose_is_the_real_one():
    """SKILL.md says 'all N error codes'. The fixture is the authority."""
    m = re.search(r"remedy for \*\*all (\d+)\*\*\s*\n?error codes", _text())
    if m is None:
        m = re.search(r"all \*\*(\d+)\*\*\s*\n?error codes", _text())
    assert m, "SKILL.md does not state a remedy count"
    codes = {
        line.strip()
        for line in (SKILL / "references" / "error-codes.txt").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }
    assert int(m.group(1)) == len(codes)


def test_every_referenced_file_in_skill_md_exists():
    """Markdown links to the skill's own bundled files must resolve.

    `runtime/` is in this list because the runtime now ships inside the skill. A
    link into it is a bundled-file link like any other, and the move is exactly
    the moment such a link is most likely to name a path that did not come along.
    """
    for rel in re.findall(r"\]\(((?:scripts|references|tests|runtime)/[^)]*)\)", _text()):
        assert (SKILL / rel).exists(), f"SKILL.md links {rel!r}, which is not shipped"

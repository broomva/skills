"""SKILL.md's own claims about itself must be true.

This file exists because the Tests section shipped wrong. It told a reader to run
`python3 -m pytest skills/tooling/parallax/tests/`, which does not resolve from an
install (`~/.claude/skills/parallax/` has no `skills/tooling/` prefix), and it
claimed 29 tests when there are 36.

It was found by installing the skill from skills.sh and following its own
instructions -- not by any test, because no test read the document. Same class as
the README defect in the parallax repo itself, which is guarded there by
`test/docs.test.ts`. This is that guard, on this side.

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

    An install has no `skills/tooling/` prefix, so a path carrying one is a command
    that fails for every reader who installed the skill rather than cloning it.
    """
    blocks = re.findall(r"```bash\n(.*?)```", _text(), re.S)
    targets = re.findall(r"python3 -m pytest (\S+)", "\n".join(blocks))
    assert targets, "SKILL.md documents no pytest invocation"
    for t in targets:
        assert (SKILL / t).exists(), (
            f"SKILL.md tells the reader to run pytest on {t!r}, "
            f"which does not exist relative to the skill root ({SKILL})"
        )


def test_the_documented_test_count_matches_what_pytest_collects():
    """`# 36 passed` has to be 36."""
    m = re.search(r"python3 -m pytest \S+ -q\s+#\s*(\d+) passed", _text())
    assert m, "SKILL.md's pytest line does not carry a `# N passed` count"
    claimed = int(m.group(1))
    assert claimed == _collected("tests/"), (
        f"SKILL.md claims {claimed} tests; pytest collects {_collected('tests/')}"
    )


def test_the_hermetic_and_live_split_adds_up():
    """`(29 hermetic + 7 live-CLI)` must match the two files' real counts."""
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
    """SKILL.md says 'all 46 error codes'. The fixture is the authority."""
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
    """Markdown links to the skill's own bundled files must resolve."""
    for rel in re.findall(r"\]\((scripts/[^)]+|references/[^)]+|tests/[^)]+)\)", _text()):
        assert (SKILL / rel).exists(), f"SKILL.md links {rel!r}, which is not shipped"

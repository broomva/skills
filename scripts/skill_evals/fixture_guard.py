#!/usr/bin/env python3
"""fixture_guard — make the scrubber impossible to forget (BRO-2030).

THE DEFECT THIS EXISTS FOR is not a missing pattern. It is that ``scrub.py`` was a
wholly separate manual step: ``runner.py`` contained zero occurrences of the string
``scrub``, so ``--record`` wrote whatever the model emitted straight to disk, and
whether it was ever scrubbed depended on somebody remembering. Measured, not
supposed: a second agent recording ``p9`` fixtures off ``main`` produced a set
carrying the operator's real home directory in three files and the same
``emailAddress`` / ``organizationUuid`` / ``organizationName`` triple in a fourth —
while the branch that HAD run the scrubber by hand had zero of the former.

That is the shape the whole BRO-2019/2035/2036 arc keeps finding one layer up: **the
protection exists, it works when invoked, and it is not in the path that needs it.**
A control that has to be remembered is not a control.

So there are three gates, at three different moments, and they catch different things.
None of them is redundant:

1. **RECORD TIME — this module, fail-closed.** :func:`scrub_recording` is called by
   ``LiveRunner._record`` on the way to disk. It scrubs, then VERIFIES the result is
   clean, then verifies the NDJSON shape survived, and RAISES on any of those failing.
   An unscrubbed fixture therefore never exists on disk. This is the strongest gate
   because every later one is a scan of something that already exists, and this one
   prevents the thing existing.

2. **COMMIT TIME — :func:`audit_tracked_fixtures`, wired to a test, so CI runs it.**
   Scoped to what git TRACKS, repo-wide, not to one directory. That scoping is the
   whole point: gate 1 only covers fixtures produced by *this* runner, and the
   ``p9`` leak above arrived from a branch on which ``scrub.py`` did not exist at all.
   A check that asks "is every recorded transcript this repo tracks scrub-clean, and
   is it in the one place recorded transcripts are allowed to be tracked?" catches a
   fixture written by tooling that has not been invented yet, by a rebase, or by hand.

3. **PUBLISH TIME — ``fixture_pack.py pack``.** Re-runs the scrubber AND the
   independently-written auditor over the payload, and refuses to build an archive
   from a fixture whose meta records ``--no-scrub``. It is the last point before bytes
   become a public URL, and the only one a human reads.

WHAT NONE OF THEM GIVES YOU. All three run the same blocklist, and a blocklist fails
OPEN. Adding gates multiplies the *occasions* on which the rules are applied; it does
not improve the rules. See ``scrub.py``'s module docstring for what the containment
actually rests on.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from . import scrub

#: Recorded transcripts, wherever they sit. `cases/<id>/trial-NN.jsonl` is the shape
#: `--record` writes and the shape `--replay` reads, so it is the right thing to
#: recognise — matching on a directory name would miss a fixture set recorded into a
#: new path, which is exactly how the `p9` set escaped the guard that only knew about
#: `tests/skill_evals/fixtures/live`.
RECORDED_FIXTURE_GLOB = "cases/*/trial-*.jsonl"

#: The ONE tracked fixture set. It is synthetic (hand-authored by `generate.py`, no
#: model involved), it is tiny, and CI's graded replay depends on it being in git.
#: Everything else recorded is model output and belongs in the release asset.
TRACKED_FIXTURES_ALLOWED = ("tests/skill_evals/fixtures/harness-selftest/",)


class UnscrubbedFixture(RuntimeError):
    """A fixture could not be shown clean. Never returned as a warning."""


def _residual(text: str) -> dict[str, int]:
    """What a SECOND scrub pass would still change. Non-empty means non-convergent."""
    again, counts = scrub.scrub_text(text)
    return counts if again != text else {}


def _assert_ndjson_shape(before: str, after: str, where: str) -> None:
    """A redaction must not break the file it is protecting.

    Redaction is byte surgery on JSON, and it has already been observed to produce an
    illegal escape (`\\REDACTED…` where a real address followed an escaped newline),
    which makes the line unparseable. Replay then scores the trial ERROR — a fixture
    destroyed by the step meant to make it publishable, and silently, because nothing
    re-read it. So: same number of lines, and every one of them still parses.
    """
    before_lines = [ln for ln in before.splitlines() if ln.strip()]
    after_lines = [ln for ln in after.splitlines() if ln.strip()]
    if len(before_lines) != len(after_lines):
        raise UnscrubbedFixture(
            f"{where}: scrubbing changed the line count "
            f"({len(before_lines)} -> {len(after_lines)}). Refusing to write."
        )
    for i, line in enumerate(after_lines, 1):
        try:
            json.loads(line)
        except ValueError as exc:
            raise UnscrubbedFixture(
                f"{where}: line {i} no longer parses as JSON after scrubbing ({exc}). "
                "A redaction corrupted the transcript; refusing to write it."
            ) from exc


def scrub_recording(stdout: str, stderr: str, *, where: str) -> tuple[str, str, dict[str, int]]:
    """Scrub a recording on its way to disk, or refuse to let it be written.

    Returns ``(clean_stdout, clean_stderr, counts)``. Raises
    :class:`UnscrubbedFixture` if the result is not clean, if a second pass would
    still change it, or if scrubbing damaged the NDJSON. It never returns something
    it could not vouch for, and it never warns-and-proceeds: a warning is a thing a
    scrollback eats, and the artefact it would leave behind is a file somebody
    commits.
    """
    clean_out, out_counts = scrub.scrub_text(stdout)
    clean_err, err_counts = scrub.scrub_text(stderr or "")

    for label, text in (("transcript", clean_out), ("stderr", clean_err)):
        residual = _residual(text)
        if residual:
            raise UnscrubbedFixture(
                f"{where}: the {label} is still not clean after one scrub pass "
                f"({residual}). That means a redaction rule is not convergent — its "
                "replacement re-matches its own pattern. Fix the rule; do not write "
                "the fixture."
            )

    _assert_ndjson_shape(stdout, clean_out, where)

    counts = dict(out_counts)
    for k, v in err_counts.items():
        counts[k] = counts.get(k, 0) + v
    return clean_out, clean_err, counts


# ---------------------------------------------------------------------------
# gate 2 — what git tracks
# ---------------------------------------------------------------------------


def _git_tracked(repo: Path) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-z"],
        capture_output=True, text=True, check=True,
    ).stdout
    return [p for p in out.split("\0") if p]


def tracked_recorded_fixtures(repo: Path) -> list[str]:
    """Repo-relative paths of recorded transcripts that git TRACKS.

    Only the allowlisted synthetic set is meant to be in here. Anything else is model
    output on its way into permanent public git history.
    """
    hits = []
    for rel in _git_tracked(repo):
        if not Path(rel).match(RECORDED_FIXTURE_GLOB):
            continue
        if rel.startswith(TRACKED_FIXTURES_ALLOWED):
            continue
        hits.append(rel)
    return sorted(hits)


def audit_tracked_fixtures(repo: Path) -> dict[str, dict[str, int]]:
    """Scrub findings over every tracked fixture-shaped file, allowlist included.

    The allowlisted synthetic set is audited too, on purpose. It is hand-authored, so
    it *should* be clean — and "should" is the word that precedes every one of these
    incidents.
    """
    findings: dict[str, dict[str, int]] = {}
    for rel in _git_tracked(repo):
        p = Path(rel)
        if p.suffix not in (".jsonl", ".json"):
            continue
        if not (p.match(RECORDED_FIXTURE_GLOB) or p.match("cases/*/trial-*.meta.json")):
            continue
        text = (repo / rel).read_text(encoding="utf-8", errors="replace")
        scrubbed, counts = scrub.scrub_text(text)
        if scrubbed != text:
            findings[rel] = counts
    return findings

"""Reader for git outcomes across the discovered repositories.

Commits are the one signal that says what the conversations *produced*.  The
subprocess call is deliberately hardened: an agent frequently runs inside a
worktree whose environment carries credentials, so git is spawned with a
filtered environment and with external diff and textconv drivers disabled.
"""

from __future__ import annotations

import os
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from ..model import SourceReport, Window

NAME = "git"

#: Only these variables reach the git subprocess.
_ENV_ALLOW = ("PATH", "HOME", "LANG", "LC_ALL", "TZ", "SYSTEMROOT", "TMPDIR")

#: Applied to git log, not to git itself — these are subcommand options
#: and git exits 129 if they appear before the subcommand.
_SAFE_LOG_ARGS = ("--no-ext-diff", "--no-textconv")


def _safe_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k in _ENV_ALLOW}
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    env.setdefault("GIT_CONFIG_NOSYSTEM", "1")
    return env


@dataclass(slots=True)
class GitStats:
    """Commit activity across repositories inside the window."""

    commits: int = 0
    repos: int = 0
    repos_failed: int = 0
    by_repo: list[tuple[str, int]] = field(default_factory=list)
    by_day: dict[str, int] = field(default_factory=dict)
    first: str | None = None
    last: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "commits": self.commits,
            "repos": self.repos,
            "repos_failed": self.repos_failed,
            "by_repo": [{"repo": r, "commits": n} for r, n in self.by_repo],
            "first": self.first,
            "last": self.last,
        }


def _git_log(repo: Path, window: Window, author: str | None) -> tuple[list[str], str | None]:
    """Return (days, error). A failure is reported, never folded into zero."""
    cmd = ["git", "-C", str(repo), "log", *_SAFE_LOG_ARGS, "--format=%as", "--no-merges"]
    if window.start:
        cmd.append(f"--since={window.start.date().isoformat()}")
    if window.end:
        cmd.append(f"--until={window.end.date().isoformat()}")
    if author:
        cmd.append(f"--author={author}")
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30, env=_safe_env(), check=False
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return [], f"{type(exc).__name__}: {exc}"
    if proc.returncode != 0:
        return [], (proc.stderr or "").strip().splitlines()[0] if proc.stderr else f"rc={proc.returncode}"
    return [line for line in proc.stdout.splitlines() if line.strip()], None


def read(
    repos: list[Path], window: Window, author: str | None = None
) -> tuple[SourceReport, GitStats | None]:
    """Count commits per repository within the window."""
    if not repos:
        return SourceReport(NAME, False, reason="no git repositories found under the workspace"), None

    stats = GitStats(repos=len(repos))
    per_repo: Counter[str] = Counter()
    per_day: Counter[str] = Counter()

    errors: list[str] = []
    for repo in repos:
        days, error = _git_log(repo, window, author)
        if error:
            stats.repos_failed += 1
            errors.append(f"{repo.name}: {error}")
            continue
        for day in days:
            per_repo[repo.name] += 1
            per_day[day] += 1
            stats.commits += 1

    # Every repository failing is a broken reader, not a year without commits.
    if stats.repos_failed == len(repos):
        reason = f"git failed in all {len(repos)} repositories — {errors[0] if errors else 'unknown'}"
        return SourceReport(NAME, False, reason=reason), None

    if not stats.commits:
        report = SourceReport(
            NAME, True, root=f"{len(repos)} repositories", files=len(repos), records=0
        )
        return report, stats

    days = sorted(per_day)
    stats.first, stats.last = days[0], days[-1]
    stats.by_repo = per_repo.most_common(10)
    stats.by_day = dict(per_day)
    report = SourceReport(
        NAME, True, root=f"{len(repos)} repositories", files=len(repos), records=stats.commits
    )
    return report, stats

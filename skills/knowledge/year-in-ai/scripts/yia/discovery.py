"""Locate the local AI-history stores on whatever machine this runs on.

The skill is distributable, so nothing here may assume the author's layout.
Every candidate path is probed, and the result is a plain description of what
is present.  Callers pass ``overrides`` to point at a fixture corpus, which is
also how the test-suite avoids reading the operator's real history.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _expand(p: str | os.PathLike[str]) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(str(p))))


@dataclass(slots=True)
class Stores:
    """Resolved roots for each store, ``None`` when absent from this machine."""

    claude_projects: Path | None = None
    claude_history: Path | None = None
    codex_sessions: Path | None = None
    bridged_roots: list[Path] = field(default_factory=list)
    kg_entities: Path | None = None
    memory_dir: Path | None = None
    git_roots: list[Path] = field(default_factory=list)
    #: Where ``bridged_roots``/``kg_entities`` were searched from.
    workspace: Path | None = None

    def describe(self) -> dict[str, object]:
        return {
            "claude_projects": str(self.claude_projects) if self.claude_projects else None,
            "claude_history": str(self.claude_history) if self.claude_history else None,
            "codex_sessions": str(self.codex_sessions) if self.codex_sessions else None,
            "bridged_roots": [str(p) for p in self.bridged_roots],
            "kg_entities": str(self.kg_entities) if self.kg_entities else None,
            "memory_dir": str(self.memory_dir) if self.memory_dir else None,
            "git_roots": [str(p) for p in self.git_roots],
            "workspace": str(self.workspace) if self.workspace else None,
        }


#: Candidate locations, most-specific first. Extend rather than replace, so a
#: machine with a non-default layout can still be discovered.
CLAUDE_PROJECT_CANDIDATES = ("~/.claude/projects",)
CLAUDE_HISTORY_CANDIDATES = ("~/.claude/history.jsonl",)
CODEX_SESSION_CANDIDATES = ("~/.codex/sessions", "~/.config/codex/sessions")
MEMORY_GLOBS = ("~/.claude/projects/*/memory",)

#: Directories never worth walking when hunting for bridged sessions or repos.
PRUNE = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", ".next", "dist",
    "build", "target", ".cache", "site-packages", ".worktrees", ".mypy_cache",
    ".pytest_cache", "vendor", ".terraform",
}


def _first_existing(candidates: tuple[str, ...], *, want_dir: bool) -> Path | None:
    for c in candidates:
        p = _expand(c)
        if (p.is_dir() if want_dir else p.is_file()):
            return p
    return None


def find_bridged_roots(workspace: Path, *, max_depth: int = 4, limit: int = 64) -> list[Path]:
    """Find ``docs/conversations`` directories that hold bridged session files.

    Depth-limited and prune-listed: a workspace can contain vendored trees with
    a directory of the same name (``openai/resources/conversations``), and those
    hold no ``session-*.md``, so the content check is what actually qualifies a
    directory — not its name.
    """
    found: list[Path] = []
    root_depth = len(workspace.parts)
    for dirpath, dirnames, _ in os.walk(workspace):
        here = Path(dirpath)
        if len(here.parts) - root_depth >= max_depth:
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in PRUNE and not d.startswith(".")]
        if here.name == "conversations" and here.parent.name == "docs":
            # Qualify on content, never on the name alone.
            if any(here.glob("session-*.md")):
                found.append(here)
                if len(found) >= limit:
                    return found
    return found


def find_git_roots(workspace: Path, *, max_depth: int = 3, limit: int = 64) -> list[Path]:
    """Find git repositories under ``workspace`` (worktrees included)."""
    found: list[Path] = []
    root_depth = len(workspace.parts)
    for dirpath, dirnames, _ in os.walk(workspace):
        here = Path(dirpath)
        if len(here.parts) - root_depth >= max_depth:
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in PRUNE and not d.startswith(".")]
        if (here / ".git").exists():
            found.append(here)
            dirnames[:] = [d for d in dirnames if d not in PRUNE]
            if len(found) >= limit:
                return found
    return found


def discover(
    workspace: str | os.PathLike[str] | None = None,
    overrides: dict[str, str | os.PathLike[str]] | None = None,
    *,
    scan_workspace: bool = True,
) -> Stores:
    """Probe this machine for AI-history stores.

    ``overrides`` maps a :class:`Stores` field name to an explicit path and
    short-circuits the search for that field, which is how tests bind the
    readers to a fixture corpus instead of the real one.
    """
    overrides = {k: _expand(v) for k, v in (overrides or {}).items()}
    ws = _expand(workspace) if workspace else Path.cwd()

    stores = Stores(workspace=ws if ws.is_dir() else None)

    stores.claude_projects = overrides.get("claude_projects") or _first_existing(
        CLAUDE_PROJECT_CANDIDATES, want_dir=True
    )
    stores.claude_history = overrides.get("claude_history") or _first_existing(
        CLAUDE_HISTORY_CANDIDATES, want_dir=False
    )
    stores.codex_sessions = overrides.get("codex_sessions") or _first_existing(
        CODEX_SESSION_CANDIDATES, want_dir=True
    )

    if "memory_dir" in overrides:
        stores.memory_dir = overrides["memory_dir"]
    else:
        for pattern in MEMORY_GLOBS:
            expanded = _expand(pattern)
            matches = sorted(expanded.parent.parent.glob(f"{expanded.parent.name}/{expanded.name}"))
            live = [m for m in matches if m.is_dir() and any(m.glob("*.md"))]
            if live:
                # The richest memory directory is the informative one.
                stores.memory_dir = max(live, key=lambda m: len(list(m.glob("*.md"))))
                break

    if "kg_entities" in overrides:
        stores.kg_entities = overrides["kg_entities"]
    elif stores.workspace is not None:
        cand = stores.workspace / "research" / "entities"
        stores.kg_entities = cand if cand.is_dir() else None

    if "bridged_roots" in overrides:
        stores.bridged_roots = [overrides["bridged_roots"]]
    elif scan_workspace and stores.workspace is not None:
        stores.bridged_roots = find_bridged_roots(stores.workspace)

    if "git_roots" in overrides:
        stores.git_roots = [overrides["git_roots"]]
    elif scan_workspace and stores.workspace is not None:
        stores.git_roots = find_git_roots(stores.workspace)

    return stores

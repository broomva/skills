"""governance_paths.py — where a governance file lives while the layout moves.

The unified-layout ADR (docs/adrs/2026-10-19-unified-broomva-layout.html,
BRO-3200) renames the governance directory. Until its step 5 drops the old
name, every reader accepts both and prefers the new one. A reader that asks
this module names neither directory, so the move is one edit here and the
control reader ratchet (scripts/check_control_readers.py) stops counting it.

Scripts run isolated (-I) do not see their own directory on sys.path; they
APPEND it, so a planted stdlib name in scripts/ still cannot shadow the
standard library:

    sys.path.append(str(Path(__file__).resolve().parent))
    from governance_paths import governance_file
"""
from __future__ import annotations

from pathlib import Path

# New name first. The ADR's step 5 deletes the second entry.
DIRS = (".broomva", ".control")


def governance_file(root: str | Path, name: str) -> Path:
    """`<root>/<dir>/<name>` for the first directory in DIRS that has it.

    When neither has it, the old location: that is where the file is today, so a
    "missing file" error names the path a reader would look for first.
    """
    root = Path(root)
    for d in DIRS:
        if (root / d / name).exists():
            return root / d / name
    return root / DIRS[-1] / name


def governance_globs(name: str) -> list[str]:
    """`<dir>/<name>` for every directory in DIRS, for glob and path-set users."""
    return [f"{d}/{name}" for d in DIRS]

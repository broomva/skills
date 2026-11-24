#!/usr/bin/env -S python3 -I
"""rules_case_data.py — what a registry case may write: data, never code (BRO-3802).

One judgement, imported by rules_check.py (before a replay) and rules_fixtures.py (where the
file is written), with no dependency beyond the standard library so the fixture can load it
anywhere (P20 #1299 rounds 13-15).

A case writes data, never code (round 13, STRUCTURAL): an enforcer may import or source a file
from a path a case controls (a HOME it moves into its scratch), so a file a case writes carries a
data suffix or is a .gitignore, and no other name starts with a dot. Directories that start with a
dot are tool configuration (.claude, .config/gh), except the governance roots. A governance file a
case fills would be the policy a gate obeys, so a proof against it proves nothing about the live
one (round 14, stratum C): the case may only create it empty, with `touch`.
"""
from __future__ import annotations

from pathlib import Path

DATA_SUFFIXES = (".yaml", ".yml", ".json", ".jsonl", ".md", ".txt", ".ipynb")
GOVERNANCE_DIRS = (".broomva", ".control")


def data_name_error(path: str, empty: bool = False) -> str | None:
    """Why a file a case writes is not plain data, or None. `empty` is a `touch`: it may create a
    governance file, since an empty one fills no policy."""
    parts = [part for part in Path(path).parts if not part.startswith("{")]
    name, dirs = (parts[-1] if parts else ""), parts[:-1]
    if any(d.startswith(".") and d.casefold() not in GOVERNANCE_DIRS for d in dirs):
        return f"{path} is under a tool's configuration directory, not data a case writes"
    governed = any(d.casefold() in GOVERNANCE_DIRS for d in dirs)
    if governed and not empty and not name.casefold().endswith((".md", ".txt")):
        return f"{path} is a governance file; a case may only create it empty (touch)"
    if name == ".gitignore" or (not name.startswith(".") and name.casefold().endswith(DATA_SUFFIXES)):
        return None
    return f"{path} is not a data file (a case writes only {', '.join(DATA_SUFFIXES)} or .gitignore)"

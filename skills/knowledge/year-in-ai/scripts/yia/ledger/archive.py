"""Keep raw transcripts that their own tool will delete.

The ledger keeps counts; the archive keeps the words, so a recap can quote a
moment from March in December. It copies stores that prune themselves into an
archive root, usually on a larger disk:

    <root>/claude-projects/   from ~/.claude/projects
    <root>/codex-sessions/    from ~/.codex/sessions
    <root>/year-in-ai-ledger/ from the ledger directory

The copy is additive. It never deletes from the archive, so a session pruned
at the source stays in the archive. A file is copied when the archive lacks
it, when the source is larger (transcripts only grow), or when it has the same
size and a newer modification time. Each copy goes through a temporary file
and a rename, so an interrupted run never leaves a half-written transcript.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple

#: (default source, subdirectory in the archive root)
DEFAULT_TARGETS: List[Tuple[str, str]] = [
    ("~/.claude/projects", "claude-projects"),
    ("~/.codex/sessions", "codex-sessions"),
]


def _needs_copy(src: os.stat_result, dst: Path) -> bool:
    try:
        existing = dst.stat()
    except FileNotFoundError:
        return True
    if src.st_size > existing.st_size:
        return True
    return src.st_size == existing.st_size and src.st_mtime > existing.st_mtime + 1


def copy_additive(source: Path, target: Path, suffixes: Optional[Tuple[str, ...]] = None) -> Dict[str, int]:
    """Mirror ``source`` into ``target`` without ever deleting. Returns counts."""
    counts = {"copied": 0, "unchanged": 0, "bytes": 0, "errors": 0}
    if not source.is_dir():
        return counts
    for dirpath, dirnames, filenames in os.walk(source):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        rel = Path(dirpath).relative_to(source)
        for name in filenames:
            if suffixes and not name.endswith(suffixes):
                continue
            src_path = Path(dirpath) / name
            dst_path = target / rel / name
            tmp = dst_path.with_name(f".{name}.yia-tmp")
            try:
                st = src_path.stat()
                if not _needs_copy(st, dst_path):
                    counts["unchanged"] += 1
                    continue
                dst_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_path, tmp)
                # The source can shrink or be rewritten between the stat above and
                # the copy. Judge what was actually copied, against the archive as it
                # is now, immediately before replacing it.
                if not _needs_copy(tmp.stat(), dst_path):
                    counts["unchanged"] += 1
                    continue
                os.replace(tmp, dst_path)
                counts["copied"] += 1
                counts["bytes"] += dst_path.stat().st_size
            except OSError:
                counts["errors"] += 1
            finally:
                try:
                    tmp.unlink()
                except FileNotFoundError:
                    pass
                except OSError:
                    counts["errors"] += 1
    return counts


def _nested(a: Path, b: Path) -> bool:
    """True when ``a`` and ``b`` are the same directory or one contains the other."""
    ra, rb = os.path.realpath(a), os.path.realpath(b)
    return os.path.commonpath([ra, rb]) in (ra, rb)


def archive(root: Path, ledger_dir: Optional[Path] = None,
            targets: Optional[List[Tuple[str, str]]] = None) -> Dict[str, Dict[str, int]]:
    """Copy every pruning store, and the ledger itself, into ``root``."""
    if not root.is_dir():
        raise FileNotFoundError(f"archive root {root} is not mounted or does not exist")
    pairs = [(Path(os.path.expanduser(raw)), sub, (".jsonl", ".jsonl.zst")) for raw, sub in targets or DEFAULT_TARGETS]
    if ledger_dir is not None:
        pairs.append((Path(ledger_dir), "year-in-ai-ledger", (".jsonl",)))
    # A destination inside its source would copy its own output on every walk.
    for source, sub, _suffixes in pairs:
        if source.is_dir() and _nested(source, root / sub):
            raise ValueError(f"archive target {root / sub} overlaps its source {source}")
    results: Dict[str, Dict[str, int]] = {}
    for source, sub, suffixes in pairs:
        results[sub] = copy_additive(source, root / sub, suffixes)
    return results

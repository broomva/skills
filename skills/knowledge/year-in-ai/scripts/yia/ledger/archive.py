"""Keep raw transcripts that their own tool will delete.

The ledger keeps counts; the archive keeps the words, so a recap can quote a
moment from March in December. It copies stores that prune themselves into an
archive root, usually on a larger disk:

    <root>/claude-projects/   from ~/.claude/projects
    <root>/codex-sessions/    from ~/.codex/sessions
    <root>/year-in-ai-ledger/ from the ledger directory

**Nothing archived is ever lost.** The archive never deletes, and it replaces
an archived file only with one that *extends* it byte for byte (a transcript
that grew). A source that extends none of its archived versions (rewritten,
truncated, or truncated and then appended to) opens a new numbered revision,
``<name>.rev-<n>.<ext>``, beside them; later growth of that source extends the
revision in place instead of copying it again. Readers read every version and
dedupe the overlap by occurrence identity.

The cheap skip trusts metadata only when nothing could have rewritten the
source since it was archived: same size, same ``mtime_ns``, and a source
``ctime`` no newer than the archived copy's. ``ctime`` cannot be set back by a
restore or a timestamp-preserving copy, so those are compared byte for byte.

Each copy goes through a temporary file. The decision is re-checked against
the finished copy and the archive as it is at that moment, immediately before
the rename, so a source that changes mid-copy cannot replace a longer
archived file. Temporary files are removed on every path.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import exclusive_lock

#: (default source, subdirectory in the archive root)
DEFAULT_TARGETS: List[Tuple[str, str]] = [
    ("~/.claude/projects", "claude-projects"),
    ("~/.codex/sessions", "codex-sessions"),
]

_CHUNK = 1 << 20


class _Unchanged(Exception):
    pass


def _starts_with(path: Path, prefix: Path, length: int) -> bool:
    """Do the first ``length`` bytes of ``path`` equal the first ``length`` bytes of ``prefix``?"""
    try:
        with path.open("rb") as a, prefix.open("rb") as b:
            remaining = length
            while remaining > 0:
                n = min(_CHUNK, remaining)
                if a.read(n) != b.read(n):
                    return False
                remaining -= n
        return True
    except OSError:
        return False


def _split_ext(name: str):
    for ext in (".jsonl.zst", ".jsonl"):
        if name.endswith(ext):
            return name[: -len(ext)], ext
    return name, ""


def _versions(dst: Path) -> List[Path]:
    """The archived file and its numbered revisions, oldest first.

    Matched by an exact pattern on the listed names, not a glob, so names with
    glob metacharacters work and only ``<stem>.rev-<digits><ext>`` counts.
    """
    stem, ext = _split_ext(dst.name)
    pattern = re.compile(re.escape(stem) + r"\.rev-([0-9]+)" + re.escape(ext) + "$")
    revs = []
    if dst.parent.is_dir():
        for p in dst.parent.iterdir():
            m = pattern.match(p.name)
            if m:
                revs.append((int(m.group(1)), p))
    return ([dst] if dst.exists() else []) + [p for _n, p in sorted(revs)]


def _next_revision(dst: Path) -> Path:
    stem, ext = _split_ext(dst.name)
    taken = len(_versions(dst))
    while True:
        candidate = dst.with_name(f"{stem}.rev-{taken}{ext}")
        if not candidate.exists():
            return candidate
        taken += 1


def classify(candidate: Path, dst: Path) -> str:
    """How ``candidate`` relates to the archived ``dst``: new, same, grown, or diverged."""
    try:
        archived = dst.stat()
    except FileNotFoundError:
        return "new"
    size = candidate.stat().st_size
    if size < archived.st_size or not _starts_with(candidate, dst, archived.st_size):
        return "diverged"
    return "grown" if size > archived.st_size else "same"


def copy_additive(source: Path, target: Path, suffixes: Optional[Tuple[str, ...]] = None) -> Dict[str, int]:
    """Mirror ``source`` into ``target`` without ever deleting or shortening. Returns counts."""
    counts = {"copied": 0, "unchanged": 0, "revisions": 0, "bytes": 0, "errors": 0}
    if not source.is_dir():
        return counts
    for dirpath, dirnames, filenames in os.walk(source):
        dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
        rel = Path(dirpath).relative_to(source)
        for name in sorted(filenames):
            if suffixes and not name.endswith(suffixes):
                continue
            src_path = Path(dirpath) / name
            dst_path = target / rel / name
            tmp = dst_path.with_name(f".{name}.{os.getpid()}.yia-tmp")
            try:
                # Cheap skip only for an untouched file: copy2 preserves the
                # nanosecond mtime, so equal size *and* equal mtime_ns means the
                # source has not been written since it was archived. Anything
                # else, even a same-size rewrite in the same second, is compared
                # byte for byte below.
                try:
                    st = src_path.stat()
                    for version in _versions(dst_path):
                        v = version.stat()
                        if (st.st_size == v.st_size and st.st_mtime_ns == v.st_mtime_ns
                                and st.st_ctime_ns <= v.st_ctime_ns):
                            raise _Unchanged
                except _Unchanged:
                    counts["unchanged"] += 1
                    continue
                except FileNotFoundError:
                    pass
                dst_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_path, tmp)
                # Decide on what was actually copied, against the archive as it is now:
                # the first archived version this copy equals or extends.
                verdicts = [(classify(tmp, v), v) for v in _versions(dst_path)]
                if not verdicts:
                    os.replace(tmp, dst_path)
                    counts["copied"] += 1
                    counts["bytes"] += dst_path.stat().st_size
                    continue
                if any(kind == "same" for kind, _v in verdicts):
                    counts["unchanged"] += 1
                    continue
                grown = next((v for kind, v in verdicts if kind == "grown"), None)
                if grown is not None:
                    os.replace(tmp, grown)  # a byte-for-byte extension of that version
                    counts["copied"] += 1
                    counts["bytes"] += grown.stat().st_size
                    continue
                revision = _next_revision(dst_path)
                os.replace(tmp, revision)
                counts["revisions"] += 1
                counts["bytes"] += revision.stat().st_size
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
    # One archive run at a time per root: classification and replacement must
    # not interleave with another run's.
    with exclusive_lock(root, ".year-in-ai-archive.lock"):
        for source, sub, suffixes in pairs:
            results[sub] = copy_additive(source, root / sub, suffixes)
    return results

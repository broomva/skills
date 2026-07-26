#!/usr/bin/env python3
"""
ccr.py — reversible payload compression (the Headroom CCR pattern, lifted).

The PAYLOAD-axis counterpart to the kg skill (the RETRIEVAL axis). Where kg
shrinks *which* entities reach the model, ccr shrinks *each blob* — a tool
output, a log, a RAG chunk, a file — before it enters context.

The one load-bearing idea (learned from github.com/chopratejas/headroom, the
"CCR / reversible compression" component, verified 2026-06-15):

    compression is reversible because the FULL original is cached locally,
    keyed by content hash. The model sees a compact lossy *view* plus a
    retrieval handle (ccr://<sha256>); it calls `retrieve(handle)` only when
    it actually needs the bytes back.

So the compact view can be aggressively lossy without losing information — the
loss is recoverable on demand. This is the exact shape kg uses on the other
axis: lossy catalog projection -> `kg load` expands to the full entity body.

We lift the *pattern*, not the dependency. No ML model (Headroom's Kompress is
a HuggingFace model); the compactors here are deterministic, stdlib-only, and
the value is the reversible-cache architecture, not the compression ratio.

Architectural anchor: BRO-1521. Entity: research/entities/tool/headroom.md.

Guarantees (each backed by a test in tests/test_ccr.py):

  * BYTE-EXACT. compress reads raw bytes; retrieve writes raw bytes. CRLF,
    lone CR, missing trailing newline, NUL, BOM, astral planes, lone
    surrogates and non-UTF-8 bytes all survive the round trip unchanged.
  * CONFINED. A handle is validated as 8-64 lowercase hex chars before it
    touches the filesystem, and the resolved record must be a real file inside
    the cache dir. Handles come back from model output; they are untrusted.
  * ATOMIC + VERIFIED. Records are published by temp-file + os.replace, so a
    concurrent reader never sees a partial record; every read — retrieve,
    compress's self-heal check and stats — recomputes the sha256 and refuses a
    mismatch; an unusable record is treated as absent so the store self-heals
    rather than cementing corruption; a temp file orphaned by a hard kill is
    collected at the next cache open, once too old to be a live publish.

Usage:
    python3 ccr.py compress <file|->  [--type auto|json|code|text]
                                      [--head N] [--tail N] [--line-budget N]
                                      [--json]
    python3 ccr.py retrieve <handle|sha>          # expand back to the original
    python3 ccr.py stats [--json]                 # cache size + cumulative savings

Exit codes:
    0  ok
    1  no such handle / malformed handle / bad payload / user error
    2  internal error
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

# Content-addressed cache of originals. Env override mirrors the P7/P8
# convention (BROOMVA_P7_HOME, BROOMVA_P8_JANITOR_HOME) so CI runners and
# co-developers on non-standard layouts can relocate it.
CCR_HOME = Path(
    os.environ.get("BROOMVA_CCR_HOME", Path.home() / ".cache" / "broomva" / "ccr")
)

HANDLE_PREFIX = "ccr://"
_MIN_PREFIX = 8  # shortest sha prefix accepted by retrieve()

# A handle is a sha256 prefix and NOTHING else. Handles come back from *model
# output* — the untrusted side — so the token is validated as lowercase hex
# BEFORE it is ever joined onto a path. Without this, `cache_dir / token` is an
# arbitrary-file-read: Path.__truediv__ silently DISCARDS cache_dir when the
# token is absolute, and keeps `..` segments when it is relative.
_HANDLE_RE = re.compile(r"[0-9a-f]{%d,64}\Z" % _MIN_PREFIX)

# Per-line character budget for the text compactor. `compact_text` is otherwise
# line-oriented, so a single-line 2MB blob (minified/truncated JSON, a one-line
# log dump) compressed to 0%. Lines longer than this are elided by CHARACTER.
LINE_CHAR_BUDGET = 2000

# ---------------------------------------------------------------------------
# token estimation
# ---------------------------------------------------------------------------
# Same chars/4 heuristic `bookkeeping index` uses to size the catalog. It is an
# APPROXIMATION, not a real tokenizer — good enough for a savings signal.
def approx_tokens(text: str) -> int:
    return math.ceil(len(text) / 4)


# ---------------------------------------------------------------------------
# content-type detection (heuristic, documented as such)
# ---------------------------------------------------------------------------
_CODE_TOKENS = re.compile(
    r"\b(def|class|function|fn|func|impl|interface|struct|enum|import|from|"
    r"return|const|let|var|public|private|async|await)\b"
)
_CODE_EXTS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".mjs", ".cjs", ".go", ".rs", ".java",
    ".cpp", ".cc", ".c", ".h", ".hpp", ".rb", ".php", ".swift", ".kt", ".scala",
    ".sh", ".bash", ".lua", ".pl", ".cs", ".sql",
}


def detect_type(payload: str, filename: str | None = None) -> str:
    """auto-detect json | code | text.

    A file extension is a stronger signal than the content heuristic (a
    comment/docstring-heavy source file under-triggers keyword density), so the
    extension wins when it's available. Order: json (unambiguous) -> extension
    -> keyword-density heuristic -> text.
    """
    # A UTF-8 BOM ahead of `{`/`[` otherwise defeats JSON detection outright
    # (the payload falls through to the text compactor). Stripped for DETECTION
    # only — the cached original keeps every byte, BOM included.
    stripped = payload.lstrip("﻿").strip()
    if stripped and stripped[0] in "{[":
        try:
            json.loads(stripped)
            return "json"
        except (ValueError, TypeError):
            pass
        except RecursionError:
            # Deeply nested JSON blows the C scanner's stack. That is a payload
            # we cannot shape-skeletonise, not an internal error — fall through
            # to the text compactor instead of escaping compress() as exit 2.
            pass
    if filename:
        ext = Path(filename).suffix.lower()
        if ext == ".json":
            return "json"
        if ext in _CODE_EXTS:
            return "code"
    # content heuristic: density of code keywords across non-blank lines.
    lines = [ln for ln in payload.splitlines() if ln.strip()]
    if lines:
        hits = sum(1 for ln in lines if _CODE_TOKENS.search(ln))
        if hits / len(lines) >= 0.20:
            return "code"
    return "text"


# ---------------------------------------------------------------------------
# compactors — produce the lossy VIEW the model sees instead of the original.
# Each is reversible-by-cache: the original is always recoverable via the handle.
# ---------------------------------------------------------------------------
def _shape(value, _depth: int = 0):
    """Recursive type/shape skeleton of a parsed-JSON value (no leaf data)."""
    if isinstance(value, dict):
        if _depth >= 4:
            return {"…": f"<{len(value)} keys>"}
        return {k: _shape(v, _depth + 1) for k, v in list(value.items())[:25]}
    if isinstance(value, list):
        if not value:
            return []
        # Same depth cap as the dict branch. Without it a deeply nested ARRAY
        # (`[[[[…]]]]`) recurses to RecursionError even though the dict branch
        # is bounded — the list branch was the unguarded half.
        if _depth >= 4:
            return [f"…<{len(value)} items>"]
        return [_shape(value[0], _depth + 1), f"…<{len(value)} items>"]
    if isinstance(value, str):
        return f"str<{len(value)}>"
    return type(value).__name__  # int / float / bool / NoneType


def compact_json(payload: str, **_) -> str:
    # lstrip the BOM to match detect_type: without it a BOM-prefixed payload
    # detects as json and then fails to parse here (exit 1 on a valid document).
    data = json.loads(payload.lstrip("﻿"))
    skeleton = _shape(data)
    head = "// json skeleton (types + shapes; values elided — retrieve to expand)\n"
    return head + json.dumps(skeleton, indent=1, ensure_ascii=False)


# Match a single signature line. We deliberately do NOT absorb preceding
# decorators: a `(?:@...)*` star before a required keyword backtracks across
# every line start when a long decorator run is NOT followed by a def (O(n²)
# ReDoS). Decorators still appear as their own lines in the original; the
# outline only needs the signature line itself. Each alternative is line-bounded
# (`[^\n]*`), so matching is linear.
_DEF_RE = re.compile(
    r"^[ \t]*(?:export[ \t]+|public[ \t]+|async[ \t]+|default[ \t]+)*"
    r"(def|class|function|fn|func|impl|interface|struct|enum|type)\b[^\n]*$",
    re.MULTILINE,
)
# `^\s*` is a ReDoS: \s matches \n, so at EVERY line start the engine runs to
# EOF over a whitespace run and backtracks — quadratic (measured 64KB of blank
# lines = 26s; a 1MB log extrapolates to ~an hour). Reachable via `--type auto`,
# since blank lines are excluded from the code-density denominator and a payload
# of `"import x\n" + "\n"*N` auto-detects as code. `[ \t]*` is line-bounded, so
# matching is linear — the same shape _DEF_RE already uses.
_IMPORT_RE = re.compile(
    r"^[ \t]*(import|from|use|#include|require)\b[^\n]*$", re.MULTILINE
)


def compact_code(
    payload: str,
    head: int = 20,
    tail: int = 10,
    line_budget: int = LINE_CHAR_BUDGET,
    **_,
) -> str:
    """Structural outline: imports + def/class/fn signature lines, in order.

    The char budget applies here too. This signature used to be
    `compact_code(payload, **_)`, which silently swallowed `line_budget`,
    `head` and `tail`: a minified JS/TS bundle — one enormous line that still
    matches `_DEF_RE` — emitted that whole line as its "outline" and compressed
    to exactly 0.0%, with no flag able to work around it. That is the same
    defect `compact_text` was fixed for, surviving on the sibling path, and it
    is the canonical shape of the artifact this skill exists to shrink.
    """
    sigs = []
    for m in _DEF_RE.finditer(payload):
        line_no = payload.count("\n", 0, m.start()) + 1
        sigs.append((line_no, m.group(0).strip()))
        if len(sigs) >= 200:  # we only display 200; bound the line_no work
            break
    imports = [m.group(0).strip() for m in _IMPORT_RE.finditer(payload)]
    n_lines = payload.count("\n") + 1
    out = [f"// code outline — {n_lines} lines, {len(sigs)} defs (bodies elided)"]
    if imports:
        out.append("// imports:")
        out.extend(f"  {_clamp_line(ln, line_budget)}" for ln in imports[:30])
    out.append("// structure:")
    out.extend(f"  L{n}: {_clamp_line(sig, line_budget)}" for n, sig in sigs[:200])
    if not sigs:
        # no recognizable structure — degrade to text head/tail, carrying the
        # caller's budgets rather than silently resetting them to defaults.
        return compact_text(payload, head=head, tail=tail, line_budget=line_budget)
    return "\n".join(out)


def _clamp_line(line: str, budget: int) -> str:
    """Head/tail a single over-long line by CHARACTER (the char-budget half)."""
    if budget <= 0 or len(line) <= budget:
        return line
    head_n = budget * 2 // 3
    tail_n = budget - head_n
    dropped = len(line) - head_n - tail_n
    return (
        line[:head_n]
        + f"[… {dropped} chars elided — retrieve the handle to expand …]"
        + line[len(line) - tail_n:]
    )


def compact_text(
    payload: str,
    head: int = 20,
    tail: int = 10,
    line_budget: int = LINE_CHAR_BUDGET,
    **_,
) -> str:
    """Head + tail by LINE, then head + tail by CHARACTER on any over-long line.

    Two budgets, because one is not enough:

    * the LINE budget (head/tail) handles the many-short-lines case (logs);
    * the CHARACTER budget (`line_budget`) handles the one-enormous-line case —
      a minified or truncated JSON blob, a single-line dump. Without it those
      payloads compressed to exactly 0%: `len(lines) <= head + tail` short-
      circuited and returned the whole 2MB back as the "compact view".

    head/tail are clamped to >= 0. Negative values previously produced a view
    LARGER than the original with a misreported elision count, and `tail=0`
    silently disabled compression entirely (`lines[-0:]` is the whole list).

    `line_budget <= 0` disables the CHARACTER budget only — the same meaning
    `_clamp_line` already gives it, and the meaning `--help` and SKILL.md
    promise ("0 disables the char budget"). It does NOT disable the line
    budget: `--line-budget 0 --head 3 --tail 2` still elides the middle.
    """
    head, tail = max(0, head), max(0, tail)
    lines = payload.splitlines()
    if len(lines) <= head + tail:
        # Few enough lines to keep them all — but a single LINE can still be
        # enormous, so the character budget still applies. Only when nothing is
        # over budget do we return the payload untouched (this fast path is
        # load-bearing: joining splitlines() back up would drop a trailing
        # newline and normalise \r\n, so the "unchanged" view must be `payload`).
        #
        # `line_budget <= 0` must reach that fast path. Without the guard,
        # `len(ln) <= 0` was False for every non-empty line, so DISABLING the
        # budget routed multi-line input down the join path it was meant to
        # avoid: `compact_text("a\r\nb\r\n", line_budget=0)` returned "a\nb" —
        # a trailing newline dropped, CRLF normalised, and a reported 50%
        # saving with nothing marked elided. A view that silently rewrites
        # bytes is the one thing a "no compression" flag must not do.
        if line_budget <= 0 or all(len(ln) <= line_budget for ln in lines):
            return payload
        return "\n".join(_clamp_line(ln, line_budget) for ln in lines)
    elided = len(lines) - head - tail
    kept = (
        lines[:head]
        + [f"[… {elided} lines elided — retrieve the handle to expand …]"]
        # NOT lines[-tail:] — that is the whole list when tail == 0.
        + lines[len(lines) - tail:]
    )
    return "\n".join(_clamp_line(ln, line_budget) for ln in kept)


_COMPACTORS = {"json": compact_json, "code": compact_code, "text": compact_text}


# ---------------------------------------------------------------------------
# cache (content-addressed; one self-contained json record per original)
# ---------------------------------------------------------------------------
def _record_path(sha: str, cache_dir: Path) -> Path:
    return cache_dir / f"{sha}.json"


def _sha_from_handle(handle: str) -> str:
    h = handle.strip()
    if h.startswith(HANDLE_PREFIX):
        h = h[len(HANDLE_PREFIX):]
    return h


def _is_confined(p: Path, cache_dir: Path) -> bool:
    """True iff `p` is a real (non-symlink) entry that lives inside cache_dir.

    Belt to the _HANDLE_RE braces: even a well-formed hex handle must not read
    through a symlink someone planted in the cache directory.
    """
    try:
        if p.is_symlink():
            return False
        return p.resolve().is_relative_to(cache_dir.resolve())
    except (OSError, RuntimeError, ValueError):
        return False


def _resolve_sha(token: str, cache_dir: Path) -> str:
    """Accept a full sha or a unique prefix (>= _MIN_PREFIX chars).

    The token is validated as lowercase hex BEFORE it touches the filesystem —
    it arrives from model output, i.e. the untrusted side.
    """
    if not _HANDLE_RE.match(token):
        raise KeyError(
            f"malformed handle {token!r}: expected {_MIN_PREFIX}-64 lowercase "
            "hex chars (a sha256 or a unique prefix of one)"
        )
    if len(token) == 64:
        p = _record_path(token, cache_dir)
        if _is_confined(p, cache_dir) and p.is_file():
            return token
        # fall through: the prefix scan below raises the precise not-found error
    if not cache_dir.exists():
        raise KeyError(f"no ccr cache at {cache_dir}")
    matches = [
        p.stem
        for p in cache_dir.glob("*.json")
        if p.stem.startswith(token)
        and _HANDLE_RE.match(p.stem)
        and len(p.stem) == 64
        and _is_confined(p, cache_dir)
    ]
    if not matches:
        raise KeyError(f"no cached original for handle {token!r}")
    if len(matches) > 1:
        raise KeyError(f"ambiguous handle prefix {token!r} ({len(matches)} matches)")
    return matches[0]


# ---------------------------------------------------------------------------
# record I/O — atomic on write, digest-verified on read
# ---------------------------------------------------------------------------
def _digest(text: str) -> str:
    """sha256 of the payload. For valid UTF-8 this IS sha256 of the raw bytes.

    surrogatepass, because a payload may carry a lone surrogate — handed in
    through the Python API, or produced by the CLI's surrogateescape decode of
    a non-UTF-8 byte. surrogateescape only covers U+DC80-U+DCFF.

    Do NOT "improve" this to surrogateescape to make the handle equal
    sha256(file bytes) universally: surrogateescape maps the string "\\ud800"
    and a file holding the bytes ED A0 80 onto the SAME digest, and with
    verification in place the wrong payload would verify. Pinned by
    tests/test_ccr.py::test_digest_domain_is_collision_free.
    """
    return hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()


def _read_record(sha: str, cache_dir: Path) -> tuple[dict | None, str]:
    """Read + VERIFY one cache record. Returns (record | None, reason).

    A content-addressed store that hands back unverified bytes is not
    content-addressed. Every read recomputes the digest, so a truncated or
    tampered record is reported rather than silently served.

    Absent / unparsable / mis-digested all collapse to `None` on purpose:
    compress() treats "unusable" as "not there" and rewrites, so a partial
    record SELF-HEALS instead of being cemented forever by an `exists()` check.
    """
    p = _record_path(sha, cache_dir)
    if not _is_confined(p, cache_dir):
        return None, "outside-cache"
    if not p.is_file():
        return None, "absent"
    try:
        rec = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None, "unparsable"
    if not isinstance(rec, dict) or not isinstance(rec.get("original"), str):
        return None, "malformed"
    if _digest(rec["original"]) != sha:
        return None, "digest-mismatch"
    return rec, "ok"


def _write_record(sha: str, cache_dir: Path, rec: dict) -> None:
    """Publish one record ATOMICALLY (temp file in-dir, then os.replace).

    `Path.write_text` streams straight into the final name, so a concurrent
    reader observes the half-written file (measured: 235 torn reads during one
    60MB write). os.replace is atomic within a filesystem, so the canonical
    path only ever appears complete — and a crash mid-write leaves a stray
    temp file, never a poisoned record. The `except BaseException` below
    unlinks that temp file when the publish FAILS; a hard kill runs no handler,
    so `_reap_stale_parts` collects what it leaves behind.
    """
    _ensure_cache_dir(cache_dir)
    # ensure_ascii=True so any lone surrogate / non-BMP char is escaped to ASCII
    # in the stored record — the file then never holds a raw surrogate, and
    # json.loads restores the exact original on retrieve.
    blob = json.dumps(rec)
    # prefix/suffix chosen so partial files never match the `*.json` glob that
    # _resolve_sha and stats() scan.
    fh = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=cache_dir,
        prefix=".ccr-tmp-", suffix=".part", delete=False,
    )
    try:
        with fh:
            fh.write(blob)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(fh.name, 0o600)  # cached ORIGINALS are private, not 0644
        os.replace(fh.name, _record_path(sha, cache_dir))
    except BaseException:
        try:
            os.unlink(fh.name)
        except OSError:
            pass
        raise


# A `.ccr-tmp-*.part` file exists only between the temp-file create and the
# os.replace that publishes it — sub-second even for the 60MB record measured
# in the atomicity work. `_write_record`'s `except BaseException` unlinks it
# when the publish FAILS, but SIGKILL and power loss run no handler, so a hard
# kill mid-publish orphans one forever: nothing else in the store ever looks at
# a `.part` name (it is deliberately outside the `*.json` glob).
#
# AGE, not an exclusivity check, is what gates the delete. A reaper is a delete
# path in a directory concurrent processes write to, and the failure it must
# not introduce is unlinking a temp file a LIVE process is mid-publish on.
# mtime advances while that process writes, so a `.part` whose mtime is hours
# stale cannot belong to a live publish. flock would be a stronger same-host
# signal, but it is POSIX-only, unreliable on NFS, cannot cover orphans created
# before it existed, and would put a new syscall in the concurrency-critical
# write path the atomicity guarantee rests on. This is git's `gc.pruneExpire`
# reasoning: prune only what is too old for a concurrent writer to own.
_PART_TTL_SECONDS = 6 * 3600

# Reaping is a full directory scan (measured 4.7ms on a 5,000-record cache —
# 26x the cost of a cache-hit compress), so it runs ONCE per process per cache
# dir rather than on every write. Orphans are rare and inert; collecting them
# at cache-open is enough to bound the leak. A test that plants a `.part`
# AFTER the cache has been opened in the same process must clear this set.
_REAPED_CACHE_DIRS: set[str] = set()


def _reap_stale_parts(cache_dir: Path, ttl: float = _PART_TTL_SECONDS) -> int:
    """Unlink temp files orphaned by a hard kill. Returns the number reaped.

    Every failure mode is swallowed on purpose: this is opportunistic GC, and
    a reaper that can break `compress` is worse than the leak it collects. An
    OSError here means the entry was already unlinked by its owner or by a
    concurrently-reaping process — both are the desired end state.
    """
    now = time.time()
    reaped = 0
    try:
        candidates = list(cache_dir.glob(".ccr-tmp-*.part"))
    except OSError:
        return 0
    for p in candidates:
        try:
            st = os.lstat(p)
            if not stat.S_ISREG(st.st_mode):
                continue  # not something _write_record created — leave it
            if now - st.st_mtime <= ttl:
                continue  # young enough to be a LIVE publish — leave it
            os.unlink(p)
            reaped += 1
        except OSError:
            continue
    return reaped


def _ensure_cache_dir(cache_dir: Path) -> None:
    """Create the cache dir 0700, then GC temp files orphaned by a hard kill.

    It holds full plaintext originals, hence 0700.
    """
    cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(cache_dir, 0o700)  # tighten a dir created by an older version
    except OSError:
        pass
    key = os.path.realpath(cache_dir)
    if key not in _REAPED_CACHE_DIRS:
        _REAPED_CACHE_DIRS.add(key)  # marked first: one attempt per open, win or lose
        _reap_stale_parts(cache_dir)


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------
def compress(
    payload: str,
    content_type: str = "auto",
    *,
    cache_dir: Path | None = None,
    head: int = 20,
    tail: int = 10,
    line_budget: int = LINE_CHAR_BUDGET,
    filename: str | None = None,
) -> dict:
    """Compress a payload to a compact view + cache the original under a handle.

    `filename` is an optional hint that sharpens auto content-type detection
    (extension beats the content heuristic). Returns a dict: handle,
    content_type, view, and before/after char + token counts with saved_pct.
    Idempotent: identical payloads share one handle.
    """
    cache_dir = cache_dir or CCR_HOME
    if content_type == "auto":
        content_type = detect_type(payload, filename)
    if content_type not in _COMPACTORS:
        raise ValueError(f"unknown content_type {content_type!r}")

    view = _COMPACTORS[content_type](
        payload, head=head, tail=tail, line_budget=line_budget
    )
    # Never emit a view larger than the original — on tiny/narrow inputs a
    # skeleton or elision marker can exceed what it replaces. Falling back to
    # the payload keeps saved_pct honest (>= 0) and the view never misleads.
    if len(view) >= len(payload):
        view = payload
    sha = _digest(payload)

    # Up front, so a cache dir left 0755 by an older version is tightened even
    # when this call turns out to be a cache hit and writes nothing.
    _ensure_cache_dir(cache_dir)
    # Rewrite whenever the cached record is absent OR unusable (torn, tampered,
    # symlinked). The old `if not rec_path.exists()` made a partial record
    # PERMANENT — the store could never heal itself.
    rec, _reason = _read_record(sha, cache_dir)
    if rec is None:
        _write_record(
            sha,
            cache_dir,
            {
                "sha256": sha,
                "content_type": content_type,
                "original": payload,
                "original_chars": len(payload),
                "compact_chars": len(view),
                "created": datetime.now(timezone.utc).isoformat(),
            },
        )

    orig_tok, comp_tok = approx_tokens(payload), approx_tokens(view)
    saved_pct = round(100 * (1 - comp_tok / orig_tok), 1) if orig_tok else 0.0
    return {
        "handle": HANDLE_PREFIX + sha,
        "content_type": content_type,
        "view": view,
        "original_chars": len(payload),
        "compact_chars": len(view),
        "original_tokens": orig_tok,
        "compact_tokens": comp_tok,
        "saved_pct": saved_pct,
    }


def retrieve(handle: str, *, cache_dir: Path | None = None) -> str:
    """Expand a handle back to the full original (the reversibility guarantee)."""
    cache_dir = cache_dir or CCR_HOME
    sha = _resolve_sha(_sha_from_handle(handle), cache_dir)
    rec, reason = _read_record(sha, cache_dir)
    if rec is None:
        raise KeyError(
            f"cached record {sha[:12]}… is unusable ({reason}); the store is "
            "content-addressed, so wrong bytes are refused rather than served — "
            "re-compress the original"
        )
    return rec["original"]


def stats(*, cache_dir: Path | None = None) -> dict:
    """Cache-wide rollup over DIGEST-VERIFIED records: entries, bytes, savings.

    "Every read recomputes the sha256 and refuses a mismatch" is the store's
    stated invariant, and `stats` is a read. It used to be the one path that
    opted out, so a record `retrieve` refused as tampered was still counted
    here.

    Verification alone does NOT make the rollup honest, because the sha256
    covers exactly one field — `original`. The stored `original_chars` /
    `compact_chars` counters are outside it, so tampering `original_chars` to
    1e9 kept the digest valid and reported `cumulative_saved_pct: 100.0`. So
    the rollup is DERIVED from the verified field (`len(rec["original"])`)
    rather than trusting the counter, and `compact_chars` — which cannot be
    recomputed, since the view is not stored — is only accepted inside the
    range every record this program writes satisfies: `0 <= compact <= orig`
    (compress clamps the view to the payload's length). Anything outside it is
    counted as `unusable` rather than folded into the totals.

    Cost, stated rather than hidden: this is linear in cached BYTES, which it
    already was — the old version json-parsed every record's full `original`
    too. Measured on a 5,000-record / 20MB cache: 545ms before, 802ms after
    (+47% on an already-linear scan). `stats` is a diagnostic command, not a
    hot path; a rollup that can be inflated by editing one integer is worse
    than a slower one. Records the digest refuses are reported, not silently
    dropped, so `entries` never quietly disagrees with the file count.
    """
    cache_dir = cache_dir or CCR_HOME
    entries = unusable = 0
    orig_chars = comp_chars = 0
    if cache_dir.exists():
        for p in cache_dir.glob("*.json"):
            # `_read_record` re-derives the path from the stem, which is the
            # same file for any `*.json` name, and applies the confinement,
            # parse and digest checks in one place — the reason this loop no
            # longer has its own copy of them.
            rec, _reason = _read_record(p.stem, cache_dir)
            if rec is None:
                unusable += 1
                continue
            n = len(rec["original"])
            c = rec.get("compact_chars")
            if type(c) is not int or not 0 <= c <= n:
                unusable += 1
                continue
            entries += 1
            orig_chars += n
            comp_chars += c
    orig_tok, comp_tok = math.ceil(orig_chars / 4), math.ceil(comp_chars / 4)
    saved_pct = round(100 * (1 - comp_tok / orig_tok), 1) if orig_tok else 0.0
    return {
        "cache_dir": str(cache_dir),
        "entries": entries,
        "unusable": unusable,
        "original_chars": orig_chars,
        "compact_chars": comp_chars,
        "original_tokens": orig_tok,
        "compact_tokens": comp_tok,
        "cumulative_saved_pct": saved_pct,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _read_source(src: str) -> str:
    """Read the source as BYTES, then decode without touching a single one.

    `Path.read_text()` opens in text mode, which applies universal-newline
    translation: `\\r\\n` and a lone `\\r` become `\\n` BEFORE the payload is
    hashed and cached. The original bytes are destroyed at that point and
    retrieve() can never return them — the byte-exactness guarantee was simply
    false for any CRLF file. Reading bytes keeps it true.

    surrogateescape carries arbitrary non-UTF-8 bytes through the str API
    (each maps to U+DC80-U+DCFF) so a binary-ish log is compressible and
    recoverable instead of being rejected outright.
    """
    raw = sys.stdin.buffer.read() if src == "-" else Path(src).read_bytes()
    return raw.decode("utf-8", "surrogateescape")


def _encode_out(text: str) -> bytes:
    """Encode a retrieved original for byte-exact stdout.

    surrogateescape maps the U+DC80-U+DCFF surrogates `_read_source` minted for
    non-UTF-8 bytes back to those exact bytes. A payload handed in through the
    PYTHON API may hold any lone surrogate (U+D800-U+DFFF); surrogateescape
    cannot encode those, so they fall back to surrogatepass per character
    rather than crashing the CLI with exit 2.
    """
    try:
        return text.encode("utf-8", "surrogateescape")
    except UnicodeEncodeError:
        return b"".join(_encode_char(ch) for ch in text)


def _encode_char(ch: str) -> bytes:
    """Encode one character, choosing the handler that can actually take it.

    `surrogateescape` encodes exactly ONE slice of the surrogate range —
    U+DC80-U+DCFF, the bytes `_read_source` minted for non-UTF-8 input. Every
    other lone surrogate needs `surrogatepass`.

    The bound here used to be `not ("\\ud800" <= ch <= "\\udc7f")`, which routed
    U+DD00-U+DFFF to `surrogateescape` and raised, contradicting the docstring
    above ("may hold ANY lone surrogate"). Splitting on what each handler can
    encode — rather than on a hand-picked cut point — removes the gap by
    construction instead of moving it.
    """
    if "\udc80" <= ch <= "\udcff":
        return ch.encode("utf-8", "surrogateescape")
    if "\ud800" <= ch <= "\udfff":
        return ch.encode("utf-8", "surrogatepass")
    return ch.encode("utf-8", "surrogateescape")


def _write_out(text: str) -> None:
    """Write a payload-derived string to stdout as BYTES, plus a newline.

    `print()` re-encodes through the locale codec with errors='strict', so a
    view carrying the U+DC80-U+DCFF surrogates that `_read_source` mints for
    non-UTF-8 input raises UnicodeEncodeError and kills the command. Going
    through the byte buffer keeps stdout an exact channel.
    """
    sys.stdout.flush()
    sys.stdout.buffer.write(_encode_out(text) + b"\n")
    sys.stdout.buffer.flush()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ccr", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    pc = sub.add_parser("compress", help="compress a payload -> compact view + handle")
    pc.add_argument("source", help="file path, or '-' for stdin")
    pc.add_argument("--type", default="auto", choices=["auto", "json", "code", "text"])
    pc.add_argument("--head", type=int, default=20, help="text: head lines to keep")
    pc.add_argument("--tail", type=int, default=10, help="text: tail lines to keep")
    pc.add_argument(
        "--line-budget", type=int, default=LINE_CHAR_BUDGET,
        help="text: per-line CHARACTER budget before a long line is elided "
             f"(default {LINE_CHAR_BUDGET}; 0 disables the char budget)",
    )
    pc.add_argument("--json", action="store_true", help="emit the full result as JSON")

    pr = sub.add_parser("retrieve", help="expand a handle back to the original")
    pr.add_argument("handle", help="ccr://<sha> handle or a unique sha prefix")

    ps = sub.add_parser("stats", help="cache size + cumulative savings")
    ps.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)

    try:
        if args.cmd == "compress":
            payload = _read_source(args.source)
            hint = None if args.source == "-" else args.source
            result = compress(
                payload, args.type, head=args.head, tail=args.tail,
                line_budget=args.line_budget, filename=hint,
            )
            if args.json:
                # ensure_ascii=True: --json is a MACHINE envelope, so it must
                # always be pure-ASCII/valid-UTF-8 and pipeable. A view derived
                # from non-UTF-8 input holds lone surrogates that ensure_ascii
                # =False would emit raw, which no JSON reader can decode.
                print(json.dumps(result, ensure_ascii=True, indent=2))
            else:
                _write_out(result["view"])
                print(
                    f"\n# ccr: {args.source} [{result['content_type']}]  "
                    f"{result['original_tokens']}→{result['compact_tokens']} tok "
                    f"(−{result['saved_pct']}%)  handle: {result['handle']}",
                    file=sys.stderr,
                )
            return 0

        if args.cmd == "retrieve":
            # buffer.write, not stdout.write: text-mode stdout re-encodes with
            # the locale codec and would mangle the very bytes we cached.
            sys.stdout.flush()
            sys.stdout.buffer.write(_encode_out(retrieve(args.handle)))
            sys.stdout.buffer.flush()
            return 0

        if args.cmd == "stats":
            s = stats()
            if args.json:
                print(json.dumps(s, ensure_ascii=True, indent=2))
            else:
                print(
                    f"ccr cache: {s['entries']} entries @ {s['cache_dir']}\n"
                    f"  {s['original_tokens']}→{s['compact_tokens']} tok cached "
                    f"(−{s['cumulative_saved_pct']}% if all served compact)"
                )
                if s["unusable"]:
                    # Reported, not swallowed: these are records the digest
                    # check refused, and a rollup that silently omits them
                    # would disagree with the file count for no visible reason.
                    print(
                        f"  {s['unusable']} unusable record(s) excluded "
                        "(digest mismatch or impossible counters) — "
                        "re-compress those payloads to heal them"
                    )
            return 0
    except KeyError as e:
        print(f"ccr: {e}", file=sys.stderr)
        return 1
    except (ValueError, OSError) as e:
        print(f"ccr: {e}", file=sys.stderr)
        return 1
    except RecursionError:
        # A payload nested past the parser's stack limit is a bad PAYLOAD
        # (exit 1), not an internal fault (exit 2). Reachable with an explicit
        # `--type json`; `--type auto` degrades to the text compactor instead.
        print(
            "ccr: json nesting exceeds the parser's depth limit — "
            "retry with --type text",
            file=sys.stderr,
        )
        return 1
    except Exception as e:  # noqa: BLE001 — top-level guard
        print(f"ccr: internal error: {e}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main())

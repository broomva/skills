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

Usage:
    python3 ccr.py compress <file|->  [--type auto|json|code|text]
                                      [--head N] [--tail N] [--json]
    python3 ccr.py retrieve <handle|sha>          # expand back to the original
    python3 ccr.py stats [--json]                 # cache size + cumulative savings

Exit codes:
    0  ok
    1  no such handle / user error
    2  internal error
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
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
    stripped = payload.strip()
    if stripped and stripped[0] in "{[":
        try:
            json.loads(stripped)
            return "json"
        except (ValueError, TypeError):
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
        return [_shape(value[0], _depth + 1), f"…<{len(value)} items>"]
    if isinstance(value, str):
        return f"str<{len(value)}>"
    return type(value).__name__  # int / float / bool / NoneType


def compact_json(payload: str, **_) -> str:
    data = json.loads(payload)
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
_IMPORT_RE = re.compile(r"^\s*(import|from|use|#include|require)\b.*$", re.MULTILINE)


def compact_code(payload: str, **_) -> str:
    """Structural outline: imports + def/class/fn signature lines, in order."""
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
        out.extend(f"  {ln}" for ln in imports[:30])
    out.append("// structure:")
    out.extend(f"  L{n}: {sig}" for n, sig in sigs[:200])
    if not sigs:
        # no recognizable structure — degrade to text head/tail
        return compact_text(payload)
    return "\n".join(out)


def compact_text(payload: str, head: int = 20, tail: int = 10, **_) -> str:
    lines = payload.splitlines()
    if len(lines) <= head + tail:
        return payload
    elided = len(lines) - head - tail
    return "\n".join(
        lines[:head]
        + [f"[… {elided} lines elided — retrieve the handle to expand …]"]
        + lines[-tail:]
    )


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


def _resolve_sha(token: str, cache_dir: Path) -> str:
    """Accept a full sha or a unique prefix (>= _MIN_PREFIX chars)."""
    if len(token) == 64 and _record_path(token, cache_dir).exists():
        return token
    if len(token) < _MIN_PREFIX:
        raise KeyError(f"handle prefix too short (min {_MIN_PREFIX} chars): {token!r}")
    if not cache_dir.exists():
        raise KeyError(f"no ccr cache at {cache_dir}")
    matches = [
        p.stem for p in cache_dir.glob("*.json") if p.stem.startswith(token)
    ]
    if not matches:
        raise KeyError(f"no cached original for handle {token!r}")
    if len(matches) > 1:
        raise KeyError(f"ambiguous handle prefix {token!r} ({len(matches)} matches)")
    return matches[0]


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

    view = _COMPACTORS[content_type](payload, head=head, tail=tail)
    # Never emit a view larger than the original — on tiny/narrow inputs a
    # skeleton or elision marker can exceed what it replaces. Falling back to
    # the payload keeps saved_pct honest (>= 0) and the view never misleads.
    if len(view) >= len(payload):
        view = payload
    # surrogatepass: a programmatic caller may hand us a str with a lone
    # surrogate (file/stdin reads can't, but other tools can). The original is
    # stored verbatim as a JSON string and round-trips regardless.
    sha = hashlib.sha256(payload.encode("utf-8", "surrogatepass")).hexdigest()

    cache_dir.mkdir(parents=True, exist_ok=True)
    rec_path = _record_path(sha, cache_dir)
    if not rec_path.exists():
        # ensure_ascii=True so any lone surrogate / non-BMP char is escaped to
        # ASCII in the stored record — write_text (utf-8) then never sees a raw
        # surrogate, and json.loads restores the exact original on retrieve.
        rec_path.write_text(
            json.dumps(
                {
                    "sha256": sha,
                    "content_type": content_type,
                    "original": payload,
                    "original_chars": len(payload),
                    "compact_chars": len(view),
                    "created": datetime.now(timezone.utc).isoformat(),
                }
            ),
            encoding="utf-8",
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
    rec = json.loads(_record_path(sha, cache_dir).read_text(encoding="utf-8"))
    return rec["original"]


def stats(*, cache_dir: Path | None = None) -> dict:
    """Cache-wide rollup: entries, bytes cached, cumulative token savings."""
    cache_dir = cache_dir or CCR_HOME
    entries = 0
    orig_chars = comp_chars = 0
    if cache_dir.exists():
        for p in cache_dir.glob("*.json"):
            try:
                rec = json.loads(p.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
            entries += 1
            orig_chars += rec.get("original_chars", 0)
            comp_chars += rec.get("compact_chars", 0)
    orig_tok, comp_tok = math.ceil(orig_chars / 4), math.ceil(comp_chars / 4)
    saved_pct = round(100 * (1 - comp_tok / orig_tok), 1) if orig_tok else 0.0
    return {
        "cache_dir": str(cache_dir),
        "entries": entries,
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
    if src == "-":
        return sys.stdin.read()
    return Path(src).read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ccr", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    pc = sub.add_parser("compress", help="compress a payload -> compact view + handle")
    pc.add_argument("source", help="file path, or '-' for stdin")
    pc.add_argument("--type", default="auto", choices=["auto", "json", "code", "text"])
    pc.add_argument("--head", type=int, default=20, help="text: head lines to keep")
    pc.add_argument("--tail", type=int, default=10, help="text: tail lines to keep")
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
                payload, args.type, head=args.head, tail=args.tail, filename=hint
            )
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(result["view"])
                print(
                    f"\n# ccr: {args.source} [{result['content_type']}]  "
                    f"{result['original_tokens']}→{result['compact_tokens']} tok "
                    f"(−{result['saved_pct']}%)  handle: {result['handle']}",
                    file=sys.stderr,
                )
            return 0

        if args.cmd == "retrieve":
            sys.stdout.write(retrieve(args.handle))
            return 0

        if args.cmd == "stats":
            s = stats()
            if args.json:
                print(json.dumps(s, ensure_ascii=False, indent=2))
            else:
                print(
                    f"ccr cache: {s['entries']} entries @ {s['cache_dir']}\n"
                    f"  {s['original_tokens']}→{s['compact_tokens']} tok cached "
                    f"(−{s['cumulative_saved_pct']}% if all served compact)"
                )
            return 0
    except KeyError as e:
        print(f"ccr: {e}", file=sys.stderr)
        return 1
    except (ValueError, OSError) as e:
        print(f"ccr: {e}", file=sys.stderr)
        return 1
    except Exception as e:  # noqa: BLE001 — top-level guard
        print(f"ccr: internal error: {e}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main())

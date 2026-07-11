#!/usr/bin/env python3
"""validate_config — the deterministic, fail-CLOSED config gate.

A governed autonomy loop's single most dangerous failure mode is *fail-open*:
a typo'd knob that silently drops a safety block (a `DRY_RUN=true` that isn't
`0` and so goes live; a `DISPATCH_ENABLED = 0` with stray spaces that a lenient
parser reads as "enabled"). The reference scheduler (tick.sh) hard-codes the
fail-closed rules inline; this module extracts them as a pure, tested function so
a new instance inherits the exact strictness instead of re-deriving it.

The three load-bearing strict rules (each is a real P20 finding from the
reference build):
  - DISPATCH_ENABLED: enabled IFF the value is exactly "1". Missing file, missing
    line, corrupt line, or any other value → DISABLED. FORCE never bypasses it.
  - DRY_RUN: live IFF exactly "0". Anything else (unset, "true", "01") → dry (1).
  - RESUME_ENABLED: on IFF exactly "1"; else 0.
Numeric knobs are coerced through num_or (a config typo must fall to the default,
never break the arithmetic downstream), with per-knob minimum clamps.

Plus the partition-seed guard: a partitioned STATE_DIR (a loop that owns a
disjoint slice of the queue, tagged e.g. `-life`) must only ever be seeded from a
template carrying the matching partition tag — else a manual run seeds it with
the wrong LABEL and two governors collide on the same work.

Pure stdlib. Zero network. Deterministic.
"""
from __future__ import annotations

import json
import re
import sys

# Numeric knobs → (default, minimum). A value that is not a plain non-negative
# integer falls back to the default; the result is then clamped to the minimum.
NUMERIC_KNOBS: dict[str, tuple[int, int]] = {
    "WIP_CAP": (3, 0),
    "STALL_HOURS": (4, 0),
    "RECONCILE_QUIET_HOURS": (24, 0),
    "FIRE_INTERVAL_HOURS": (2, 1),
    "ACTIVE_START": (7, 0),
    "ACTIVE_END": (23, 0),
    "MAX_DISPATCH_PER_TICK": (1, 0),
    "LABEL_MAX_PER_TICK": (5, 0),
    "RECONCILE_MAX": (40, 0),
    "SWEEP_IDLE_DAYS": (7, 0),
    "RUNNER_TIMEOUT_MIN": (45, 1),
    "INNER_INTERVAL_MIN": (10, 1),
    "INNER_TIMEOUT_MIN": (15, 1),
    "RESEED_TURN_CAP": (8, 1),
    "RESEED_MAX_GENERATIONS": (3, 0),
}

_INT_RE = re.compile(r"^\d+$")


def num_or(value, default: int, minimum: int = 0) -> int:
    """Echo VALUE if it is a plain non-negative integer, else DEFAULT; then clamp
    to MINIMUM. Mirrors tick.sh's `num_or` + the per-knob `-lt` clamps so config
    typos can never break downstream arithmetic or interpolation."""
    s = str(value).strip() if value is not None else ""
    n = int(s) if _INT_RE.match(s) else default
    return n if n >= minimum else minimum


def parse_env(text: str) -> dict[str, str]:
    """Parse a shell-style KEY=VALUE config, last-assignment-wins. Strips inline
    comments only when unquoted; ignores blank/comment lines. Deliberately simple
    (no shell expansion) — a config file is DATA, not code."""
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
            continue  # not a valid shell identifier — skip (corrupt line)
        val = val.strip()
        # strip an unquoted trailing comment
        if val[:1] not in ("'", '"'):
            val = val.split("#", 1)[0].strip()
        else:
            q = val[0]
            end = val.find(q, 1)
            val = val[1:end] if end != -1 else val[1:]
        out[key] = val
    return out


def kill_switch_enabled(raw: dict[str, str]) -> bool:
    """The loop fires IFF DISPATCH_ENABLED is exactly "1" (after whitespace
    strip). Everything else — including a missing key — disables it.

    Divergence note (deliberate, fail-safe): this reflects the *sourced* value
    (parse_env strips an unquoted inline comment, mirroring how the shell sources
    config.env). tick.sh applies an ADDITIONAL, STRICTER raw-line kill switch
    (`grep '^DISPATCH_ENABLED=' | cut | tr -d '[:space:]'` must equal "1"), so e.g.
    `DISPATCH_ENABLED=1 # note` reads enabled HERE but disabled in tick.sh. A
    validator "enabled" is therefore NECESSARY-BUT-NOT-SUFFICIENT for tick.sh to
    fire — never the dangerous direction (this never reports disabled-when-tick-
    would-fire). Keep the value comment-free for the two to agree exactly."""
    return raw.get("DISPATCH_ENABLED", "").strip() == "1"


def dry_run(raw: dict[str, str]) -> bool:
    """Dry unless DRY_RUN is exactly "0". Fails toward observation."""
    return raw.get("DRY_RUN", "1").strip() != "0"


def resume_enabled(raw: dict[str, str]) -> bool:
    return raw.get("RESUME_ENABLED", "0").strip() == "1"


def partition_seed_ok(state_dir: str, template: str, tag: str) -> bool:
    """A partitioned STATE_DIR (its basename ends with `-<tag>`) must be seeded
    only from a template whose path contains `<tag>`. Non-partitioned dirs are
    unconstrained. Prevents seeding a partition governor with the wrong LABEL —
    the two-host double-dispatch footgun (BRO-1744). Fails CLOSED on mismatch."""
    if not tag:
        return True
    sd = state_dir.rstrip("/")
    if sd.endswith(f"-{tag}"):
        return tag in template
    return True


def validate(raw: dict[str, str]) -> dict:
    """Validate + normalize a parsed config. Returns a dict:
        {enabled, dry_run, resume_enabled, knobs: {...}, warnings: [...]}
    `enabled` is the fail-closed kill switch; `knobs` are the coerced numerics.
    Warnings record every coercion so an operator sees a silently-fixed typo."""
    warnings: list[str] = []
    knobs: dict[str, int] = {}
    for key, (default, minimum) in NUMERIC_KNOBS.items():
        rawval = raw.get(key)
        coerced = num_or(rawval, default, minimum)
        if rawval is not None and str(rawval).strip() != str(coerced):
            warnings.append(f"{key}={rawval!r} coerced to {coerced}")
        knobs[key] = coerced

    label = raw.get("LABEL", "").strip()
    if not label:
        warnings.append("LABEL unset — dispatch gate is empty (nothing eligible)")

    if knobs["ACTIVE_START"] >= knobs["ACTIVE_END"]:
        warnings.append(
            f"ACTIVE_START ({knobs['ACTIVE_START']}) >= ACTIVE_END "
            f"({knobs['ACTIVE_END']}) — the loop is always in quiet hours")

    return {
        "enabled": kill_switch_enabled(raw),
        "dry_run": dry_run(raw),
        "resume_enabled": resume_enabled(raw),
        "label": label,
        "knobs": knobs,
        "warnings": warnings,
    }


def _main(argv: list[str]) -> int:
    if not argv:
        print("usage: validate_config.py <config.env> [--tag T --state-dir D --template P]",
              file=sys.stderr)
        return 2
    try:
        text = open(argv[0], encoding="utf-8").read()
    except OSError as e:
        # A missing config is not an error to this tool — it is the fail-closed
        # DISABLED state. Report it as such (enabled:false) so callers key off it.
        print(json.dumps({"enabled": False, "error": str(e)}))
        return 0
    flags = _flags(argv[1:])
    result = validate(parse_env(text))
    if flags.get("tag"):
        result["partition_seed_ok"] = partition_seed_ok(
            flags.get("state-dir", ""), flags.get("template", ""), flags["tag"])
    print(json.dumps(result, indent=2))
    return 0


def _flags(rest: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    i = 0
    while i < len(rest) - 1:
        if rest[i].startswith("--"):
            out[rest[i][2:]] = rest[i + 1]
            i += 2
        else:
            i += 1
    return out


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))

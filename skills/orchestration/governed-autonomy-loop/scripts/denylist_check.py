#!/usr/bin/env python3
"""denylist_check — verify the tracker write surface is fully denied where it
must be.

Two safety invariants of the loop are *mechanical*, not prose:
  - DRY_RUN must block every tracker WRITE tool (so "dry never writes" is a
    harness guarantee via --disallowedTools, not a prompt promise).
  - Arcs are tracker-FREE always (the governor is the sole tracker authority);
    every arc is spawned with --disallowedTools covering the tracker write
    surface, so an arc cannot write the tracker even if the MCP is in scope.

The failure mode this guards (called out verbatim in the reference's Kanon-seam
checklist): *a write tool added under the same MCP name is un-blocked until
listed in BOTH places that carry the denylist.* When the tracker gains a new
write tool — or at a Kanon cutover that swaps the MCP behind the same name — a
denylist that isn't re-derived from the tool surface silently fails open.

This check makes that a test: given the tracker's authoritative write surface and
the two denylists, assert each denylist is a superset of the surface, and report
exactly which tools are uncovered.

Pure stdlib. Zero network. Deterministic.
"""
from __future__ import annotations

import json
import sys


def uncovered(write_surface, denylist) -> list[str]:
    """Tools in the write surface that the denylist fails to block (sorted)."""
    return sorted(set(write_surface) - set(denylist))


def check(spec: dict) -> tuple[bool, dict]:
    """Validate a denylist spec. Returns (ok, report). `spec` carries:
        write_surface        — the authoritative set of tracker write tool names
        governor_dry_denylist — the DRY_RUN --disallowedTools set
        arc_denylist          — the every-arc --disallowedTools set
    ok is True iff BOTH denylists cover the full write surface."""
    surface = spec.get("write_surface", [])
    gov = spec.get("governor_dry_denylist", [])
    arc = spec.get("arc_denylist", [])
    report = {
        "write_surface_size": len(set(surface)),
        "governor_uncovered": uncovered(surface, gov),
        "arc_uncovered": uncovered(surface, arc),
    }
    ok = not report["governor_uncovered"] and not report["arc_uncovered"]
    return ok, report


def _main(argv: list[str]) -> int:
    if not argv:
        print("usage: denylist_check.py <denylist.json>", file=sys.stderr)
        return 2
    try:
        spec = json.load(open(argv[0], encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"unreadable spec: {e}", file=sys.stderr)
        return 2
    ok, report = check(spec)
    print(json.dumps(report, indent=2))
    if not ok:
        print("✗ FAIL — tracker write tools left un-denied (fail-open); "
              "add them to BOTH denylists.", file=sys.stderr)
        return 1
    print(f"✓ PASS — all {report['write_surface_size']} write tool(s) denied in "
          "both the governor-dry and arc denylists.")
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))

#!/usr/bin/env python3
"""Lint every framework YAML against frameworks/_schema.yaml.

Used by `make framework-lint`. Replaces the M1 skip-with-message stub now
that frameworks/ has 27 YAMLs (14 Phase-1 + 13 D-scope). Exits non-zero
on any validation failure.
"""

from __future__ import annotations

import sys

from core.frameworks import FRAMEWORKS_ROOT, load_all


def main() -> int:
    if not FRAMEWORKS_ROOT.exists():
        print("[skip] frameworks/ not present", file=sys.stderr)
        return 0
    try:
        registry = load_all()
    except Exception as e:  # any validation error
        print(f"[FAIL] framework validation: {e}", file=sys.stderr)
        return 1

    # Cross-check: every relationship target must be a known slug or a
    # documented deliverable suffix.
    known_slugs = set(registry.keys())
    known_deliverable_suffixes = {
        "maturity-report-deliverable",
        "capability-heatmap-deliverable",
        "use-case-dossier-deliverable",
        "impact-effort-matrix-deliverable",
        "roi-model-deliverable",
        "innovation-roadmap-deliverable",
        "pilot-plan-deliverable",
    }
    valid_targets = known_slugs | known_deliverable_suffixes
    errors: list[str] = []
    for fw in registry.values():
        for rel_kind, targets in fw.relationships.items():
            for t in targets:
                if t not in valid_targets:
                    errors.append(
                        f"  {fw.id}.relationships.{rel_kind} -> {t!r} "
                        f"(not a known framework slug or deliverable suffix)"
                    )

    print(f"[ok] {len(registry)} frameworks validated")
    print(f"     {sum(1 for f in registry.values() if not f.is_d_scope)} Phase-1")
    print(f"     {sum(1 for f in registry.values() if f.is_d_scope)} D-scope stubs")

    if errors:
        print("[FAIL] dangling relationship targets:", file=sys.stderr)
        for e in errors:
            print(e, file=sys.stderr)
        return 1
    print("[ok] all relationships resolve")
    return 0


if __name__ == "__main__":
    sys.exit(main())

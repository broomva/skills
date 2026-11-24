#!/usr/bin/env -S python3 -I
"""rules_fixtures.py — state fixtures for rule-registry replays (BRO-3800).

Some enforcers decide from state, not from the event alone: the fleet dispatch
gate reads a census, the p9 Stop hook reads a wait mark and a queue. A proof for
them is a replay against a constructed state, and the state is built here so
that each proof and its control differ in one feature. Called from `setup:` in
the rule registry (rules.yaml), with the replay's environment (HOME or BROOMVA_P9_HOME
pointed into the scratch directory), so nothing outside the scratch is touched.

  rules_fixtures.py fleet-census META_DIR MAC_CAP
      a fresh census with one live run on the Mac and host.mac.max_live=MAC_CAP
  rules_fixtures.py p9-wait P9_SCRIPTS_DIR [--empty]
      a declared wait for this session, with one queued item (none with --empty)
  rules_fixtures.py write-file PATH TEXT
      PATH (under a scratch directory) holding TEXT, with `\n` read as a newline
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path


def fleet_census(meta: Path, cap: int) -> None:
    meta.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    up = {"state": "up", "driver": "claudeAgent", "account": "agent@example.com", "quota_used": 0.0,
          "failure_streak": 0}
    snapshot = {
        "observed_at": now, "published_at": now, "reachable_hosts": ["mac"],
        "connections": {"mac": {"claudeAgent": up}},
        "host_caps": {"mac": cap}, "host_load": {"mac": {"live": 1}},
        "placements": [dict(up, host="mac", instance="claudeAgent", host_live=1, host_cap=cap,
                            host_free=max(cap - 1, 0))],
    }
    (meta / "fleet-snapshot.json").write_text(json.dumps(snapshot))
    (meta / "setpoints.json").write_text(json.dumps({"setpoints": {
        "host.mac.max_live": {"value": cap}, "gate.dispatch.mode": {"value": "enforce"},
        "census.fresh_s": {"value": 1200}}}))


def p9_wait(scripts: Path, empty: bool) -> None:
    sys.path.append(str(scripts))  # appended: the stdlib keeps precedence under -I
    import p9  # noqa: PLC0415 — the installed p9, located by the caller

    p9.mark_wait("mcp__t3-code__watch_pull_request")
    if not empty:
        p9.queue_push("docs: re-read README.md against the change", "docs")


def in_scratch(path: Path) -> bool:
    """An absolute path whose resolved parent lies under a rules-check scratch directory."""
    return path.is_absolute() and any(part.startswith("rules-check-") for part in path.resolve().parent.parts)


def main(argv: list[str]) -> int:
    if len(argv) == 3 and argv[0] == "fleet-census":
        fleet_census(Path(argv[1]), int(argv[2]))
        return 0
    if len(argv) == 3 and argv[0] == "write-file":
        path = Path(argv[1])
        if not in_scratch(path):
            print(f"write-file: {path} is not under a rules-check scratch directory", file=sys.stderr)
            return 2
        # The same judgement rules_check makes first (P20 #1299 rounds 13-14): data, never code, a
        # tool's configuration or a filled governance file.
        sys.path.append(str(Path(__file__).resolve().parent))  # appended: the stdlib keeps precedence
        from rules_case_data import data_name_error  # noqa: PLC0415
        resolved = path.resolve()  # the resolved directories in_scratch judged (P20 #1299 r16-17 C)
        # The outermost rules-check-* directory is the scratch; one a case names below it hides nothing.
        scratch_part = min(i for i, part in enumerate(resolved.parent.parts) if part.startswith("rules-check-"))
        why = data_name_error(str(Path(*resolved.parts[scratch_part + 1:])))
        if why:
            print(f"write-file: {why}", file=sys.stderr)
            return 2
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(argv[2].replace("\\n", "\n"))
        return 0
    if argv[:1] == ["p9-wait"] and len(argv) in (2, 3) and argv[2:] in ([], ["--empty"]):
        if in_scratch(Path(argv[1]) / "p9.py"):
            print("p9-wait: the p9 scripts directory is inside a scratch; name the installed p9", file=sys.stderr)
            return 2
        p9_wait(Path(argv[1]), empty=argv[2:] == ["--empty"])
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

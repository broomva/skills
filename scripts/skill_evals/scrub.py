#!/usr/bin/env python3
"""scrub — redact host-identifying content from recorded fixtures (BRO-2030).

The env jail isolates the filesystem and the environment. It does NOT isolate the
process table, the network, or anything else the host exposes to a process running as
you — and a live eval runs a real agent with `bypassPermissions`, which is free to
`ps`, `ls /`, read `~/.npm`, and put whatever it finds into a transcript. Those
transcripts are then committed, and `broomva/skills` is PUBLIC.

This was not hypothetical. The first full sweep produced a `dogfood` transcript
carrying a complete process listing of the recording machine — every running command,
home paths, which applications were open — and the pre-commit gitleaks hook is what
caught it, on an npx cache hash inside that dump.

So recording and publishing are two different acts, and this is the step between them.

    python3 scripts/skill_evals/scrub.py tests/skill_evals/fixtures/live --check
    python3 scripts/skill_evals/scrub.py tests/skill_evals/fixtures/live --apply

WHAT IT DOES NOT DO. It does not make a transcript safe to publish by inspection —
it redacts the patterns we know about. `--check` is therefore a gate you run before
committing, not a proof of absence. The durable protection is the gitleaks hook, and
the honest posture is that a live fixture is host output until someone has looked.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

#: The recording machine's home directory, replaced with a stable placeholder so the
#: fixtures stay diffable across machines instead of churning on every re-record.
HOME_PLACEHOLDER = "/Users/USER"

#: Patterns redacted on `--apply`. Each carries WHY, because a redaction nobody can
#: justify later gets removed by the next person who finds it inconvenient.
REDACTIONS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        # The recording machine's real home. Appears in tool results (ps, ls, find)
        # and identifies the operator.
        "home directory",
        re.compile(r"/Users/(?!USER\b)[A-Za-z0-9._-]+"),
        HOME_PLACEHOLDER,
    ),
    (
        # macOS per-boot temp roots: a machine fingerprint, and pure noise in a diff.
        "macOS temp root",
        re.compile(r"/var/folders/[A-Za-z0-9_]+/[A-Za-z0-9_]+"),
        "/var/folders/XX/XXXX",
    ),
    (
        # npx content-addressed cache dirs. Not secret, but they are what tripped the
        # secret scanner, and nothing grades on them.
        "npx cache hash",
        re.compile(r"/_npx/[0-9a-f]{8,}"),
        "/_npx/HASH",
    ),
    (
        # CREDENTIAL-SHAPED VALUES, by the NAME of what they are assigned to rather
        # than by the shape of the value. This is the rule that matters, and it exists
        # because of a specific artefact: the sweep's `dogfood` run listed the host's
        # processes, and another process's command line carried
        # `-session-token <36 chars>` alongside `machine_id` and `session_id`. Those
        # belong to the recording machine, not to the eval.
        #
        # The separator alternation is load-bearing and was missing at first: the real
        # artefact used a SPACE (`-session-token abc…`), not `=`, so the first version
        # of this rule matched nothing in the very transcript it was written for. The
        # secret scanner went quiet for an unrelated reason and I nearly took that as
        # proof. A rule aimed at a known artefact has to be tested against it.
        #
        # Matching on the key is deliberate. Matching on the VALUE means guessing which
        # 36-character strings are secret, which is whack-a-mole on a public repo — and
        # every miss is permanent once pushed.
        "credential-shaped assignment",
        re.compile(
            r"((?:[A-Za-z0-9_\-]*)"
            r"(?:token|secret|password|passwd|api[_\-]?key|credential|machine[_\-]?id|"
            r"session[_\-]?id|auth)"
            r"(?:[A-Za-z0-9_\-]*)[\"']?(?:\s*[:=]\s*|\s+)[\"']?)"
            r"[A-Za-z0-9_\-\.]{16,}",
            re.IGNORECASE,
        ),
        r"\1REDACTED",
    ),
)


def scrub_text(text: str) -> tuple[str, dict[str, int]]:
    """Redact, and report how many substitutions each rule made."""
    counts: dict[str, int] = {}
    for name, pattern, replacement in REDACTIONS:
        text, n = pattern.subn(replacement, text)
        if n:
            counts[name] = counts.get(name, 0) + n
    return text, counts


def scan(root: Path) -> dict[Path, dict[str, int]]:
    """Files that WOULD be changed, and by what. Read-only."""
    findings: dict[Path, dict[str, int]] = {}
    for path in sorted(Path(root).rglob("*")):
        if not path.is_file() or path.suffix not in (".jsonl", ".json"):
            continue
        original = path.read_text(encoding="utf-8", errors="replace")
        scrubbed, counts = scrub_text(original)
        if scrubbed != original:
            findings[path] = counts
    return findings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("root", type=Path)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true",
                       help="report what would be redacted; exit 1 if anything would be")
    group.add_argument("--apply", action="store_true", help="rewrite the files in place")
    args = ap.parse_args(argv)

    if not args.root.exists():
        print(f"no such path: {args.root}", file=sys.stderr)
        return 2

    findings = scan(args.root)
    if not findings:
        print(f"[scrub] clean: nothing to redact under {args.root}")
        return 0

    total = sum(sum(c.values()) for c in findings.values())
    print(f"[scrub] {len(findings)} file(s), {total} redaction(s):")
    for path, counts in list(findings.items())[:20]:
        detail = ", ".join(f"{k} x{v}" for k, v in sorted(counts.items()))
        print(f"  {path.relative_to(args.root)}  ({detail})")
    if len(findings) > 20:
        print(f"  … and {len(findings) - 20} more")

    if args.check:
        print("\n[scrub] --check: these would be redacted. Run --apply before committing.")
        return 1

    for path in findings:
        original = path.read_text(encoding="utf-8", errors="replace")
        scrubbed, _ = scrub_text(original)
        path.write_text(scrubbed, encoding="utf-8")
    print(f"\n[scrub] applied to {len(findings)} file(s).")
    print("[scrub] Re-run the replay: a redaction that changes a VERDICT is a bug, "
          "not a cosmetic edit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

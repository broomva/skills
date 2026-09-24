#!/usr/bin/env python3
"""fixture_audit — a SECOND opinion on a fixture tree, written from the other side.

    python3 scripts/skill_evals/fixture_audit.py tests/skill_evals/fixtures/live
    python3 scripts/skill_evals/fixture_audit.py <dir> --json

WHY THIS IS NOT ``scrub.py --check``. ``--check`` asks *"is there anything my
replacement rules would rewrite?"*. It is authored from the redactor's side: every
rule exists because someone knew how to fix that class. This file is authored from the
other side — *"what shapes would I be unhappy to find on a public URL?"* — and it has
no replacements at all, only findings. The two overlap, and where they diverge is the
point:

* ``scrub.py`` has no rule for an AWS key, a PEM block or a JWT, because none has ever
  appeared in a fixture. This file looks for them anyway.
* This file flags a bare 64-hex string as *review-worthy*, which ``scrub.py`` must
  never redact — ``prompt_sha256`` and ``description_sha256`` are 64-hex and they are
  the artifact binding replay depends on. So it reports counts and lets a human read
  them, rather than pretending it can classify.

BE CLEAR ABOUT WHAT THIS IS NOT. It is a second blocklist, not independent evidence.
Two blocklists written by the same author on the same afternoon share most of their
blind spots. Its value is (a) it is aimed at a different question, so it catches
classes the redactor never had to fix, and (b) its output is meant to be READ by the
person deciding to publish, not just exit-coded by a script. Absence of findings here
is not proof of absence, and the header it prints says so.

Exit codes: 0 nothing to report · 1 findings at BLOCK severity · 2 usage.
``REVIEW`` findings never fail the run on their own; they are counts a human reads.
"""

from __future__ import annotations

import argparse
import collections
import ipaddress
import json
import re
import sys
from pathlib import Path

BLOCK = "BLOCK"
REVIEW = "REVIEW"

#: RFC 2606 / RFC 6761 reserved names, plus the placeholder the scrubber writes. An
#: address at any of these identifies nobody by construction.
_SAFE_EMAIL_DOMAINS = re.compile(
    r"(?i)@(?:REDACTED\.invalid|(?:[A-Za-z0-9.\-]+\.)?example\.(?:com|net|org|edu)"
    r"|[A-Za-z0-9.\-]*\.(?:invalid|test|localhost|example|local))$"
)
_SAFE_EMAIL_ADDRESSES = frozenset({
    "git@github.com", "noreply@github.com", "actions@github.com",
    "noreply@anthropic.com",
})

#: A documented placeholder, not a credential: the literal ellipsis, or an obvious
#: `your_…` stand-in. Both occur in fetched documentation and both were hand-verified
#: in the 2026-07-29 sweep — `sk-ant-oat01-...` is thirteen characters ending in `...`
#: and `ghp_your_github_token` is what it says.
_PLACEHOLDER_SECRET = re.compile(
    r"(?i)(?:\.\.\.|<[a-z_ ]+>|your[_\-]|example|dummy|placeholder|xxx+|redacted)"
)


#: `\n@pytest.fixture`, `\n@app.route`, `\t@AGENTS.md` — a JSON escape abutting an
#: `@`, in a transcript that recorded a file read. Email-shaped, and not an address.
#: The auditor needs this carve-out for the same reason the scrubber does; without it
#: the report leads with seven findings that are all noise, and a report a reader
#: learns to skim is worth nothing.
_ESCAPE_CHARS = frozenset("nrtbfv0")


def _email_is_identifying(value: str, *, text: str = "", start: int = -1) -> bool:
    if value.lower() in _SAFE_EMAIL_ADDRESSES:
        return False
    if _SAFE_EMAIL_DOMAINS.search(value):
        return False
    local, _, domain = value.rpartition("@")
    # A version string, not an address: `acpx@0.12.0.patch`.
    if any(label.isdigit() for label in domain.split(".")):
        return False
    if len(local) == 1 and local in _ESCAPE_CHARS and start > 0 and text[start - 1] == "\\":
        return False
    return True


def _ip_is_public(value: str) -> bool:
    try:
        return ipaddress.ip_address(value).is_global
    except ValueError:
        return False  # `1.817.02.647` is a version number the regex mistook for an IP


#: A dotted quad is not a distinguishable shape, and pretending otherwise made the
#: first three runs of this auditor lead with three findings that were all fragments of
#: an SVG `d="…"` attribute: `3.7.3.9` inside `2.7-3 3.7.3.9.2`, then `5.7.3.4` inside
#: `7.1-3.2 5.7.3.4h.7`, which survives every token-boundary trick because it IS a
#: token. Version strings have the same problem.
#:
#: So the BLOCKING probe requires an address-suggesting CONTEXT, and the tradeoff is
#: named rather than buried: a bare quad sitting alone in prose is NOT blocked. That is
#: what the `dotted-quad` REVIEW probe below is for — it counts every one of them, so
#: the precise gate cannot hide the imprecise total from whoever reads the report.
_IP_CONTEXT = re.compile(
    r"(?i)(?:ip|addr|host|server|remote|listen|bind|ping|curl|ssh|scp|dns|proxy"
    r"|gateway|inet|inet6|dst|src|://|@)[^\n]{0,24}$"
)


def _ip_is_leaked(value: str, *, text: str = "", start: int = -1) -> bool:
    if not _ip_is_public(value):
        return False
    if start < 0:
        return True
    if _IP_CONTEXT.search(text[max(0, start - 44):start]):
        return True
    tail = text[start + len(value):start + len(value) + 7]
    return bool(re.match(r":\d{2,5}(?!\d)", tail))


def _secret_is_real(value: str) -> bool:
    return not _PLACEHOLDER_SECRET.search(value)


#: (id, severity, pattern, predicate, what a reader should do about it).
#: A predicate of None means every match counts.
PROBES: tuple[tuple[str, str, re.Pattern[str], object, str], ...] = (
    ("email-address", BLOCK,
     re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9](?:[A-Za-z0-9.\-]*[A-Za-z0-9])?\.[A-Za-z]{2,24}"),
     _email_is_identifying,
     "a real address. The class that got through: an agent read a config JSON."),
    ("account-identity-key", BLOCK,
     re.compile(r"(?i)\\?[\"'](?:account|organi[sz]ation|oauth|tenant|workspace|seat|billing"
                r"|subscription|customer)[A-Za-z0-9_\-]*\\?[\"']\s*:\s*\\?[\"']"
                r"(?!REDACTED[\\\"'])[^\"\\]"),
     None,
     "an account-identity field with a non-empty string value."),
    ("user-identity-key", BLOCK,
     re.compile(r"(?i)\\?[\"'](?:userid|user_id|userdisplayname|displayname|display_name"
                r"|emailaddress|fullname|full_name|phone[A-Za-z0-9_]*)\\?[\"']\s*:\s*\\?[\"']"
                r"(?!REDACTED[\\\"'])[^\"\\]"),
     None,
     "a user-identity field with a non-empty string value."),
    ("home-directory", BLOCK,
     re.compile(r"/(?:Users|home)/(?!USER\b|runner\b|user\b)[A-Za-z0-9._\-]+"),
     None,
     "the recording machine's home directory, which names the operator."),
    ("anthropic-key", BLOCK, re.compile(r"sk-ant-[A-Za-z0-9._\-]{6,}"), _secret_is_real,
     "an Anthropic API/OAuth key shape."),
    ("github-token", BLOCK, re.compile(r"gh[pousr]_[A-Za-z0-9]{10,}"), _secret_is_real,
     "a GitHub token shape."),
    ("aws-access-key", BLOCK, re.compile(r"(?:AKIA|ASIA)[0-9A-Z]{16}"), None,
     "an AWS access key id."),
    ("slack-token", BLOCK, re.compile(r"xox[abprs]-[0-9A-Za-z\-]{10,}"), _secret_is_real,
     "a Slack token shape."),
    ("private-key-block", BLOCK, re.compile(r"BEGIN (?:[A-Z ]+ )?PRIVATE KEY"), None,
     "a PEM private key block."),
    ("jwt", BLOCK, re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\."), None,
     "a JWT, which decodes to whatever claims it carries."),
    ("bearer-header", BLOCK, re.compile(r"(?i)(?:authorization|bearer)\s*[:=]?\s*"
                                        r"(?:bearer\s+)?[A-Za-z0-9._\-]{24,}"),
     _secret_is_real, "an Authorization header with a long value."),
    # The boundaries reject a longer dotted-number run. Both "public IPs" in the
    # first sweep were fragments of an SVG `d="…"` coordinate string — `3.7.3.9`
    # inside `2.7-3 3.7.3.9.2 3.7` — and `\b` alone cannot see that.
    ("public-ip", BLOCK,
     re.compile(r"(?<![\d.\-])(?:\d{1,3}\.){3}\d{1,3}(?![\d.\-])"), _ip_is_leaked,
     "a routable IP in address-shaped context (a URL, a curl, an ssh, a log line)."),
    ("crm-path", BLOCK, re.compile(r"(?i)(?:^|[\s\"'/\\])crm/[a-z0-9._\-]"), None,
     "a reference to the private crm/ tree, which is PII under a hard invariant."),
    # Reported, never failed on. `prompt_sha256` is 64-hex and load-bearing; a UUID is
    # ordinary transcript plumbing. A gate here would fire on 20,370 harmless ids.
    ("dotted-quad", REVIEW,
     re.compile(r"(?<![\d.\-])(?:\d{1,3}\.){3}\d{1,3}(?![\d.\-])"), _ip_is_public,
     "routable-looking quads with NO address context. Almost always SVG path data or a "
     "version string — but the count is here so the precise gate cannot hide it."),
    ("bare-uuid", REVIEW, re.compile(r"\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b"), None,
     "UUIDs. Mostly event ids; check none is an ACCOUNT or ORG uuid."),
    ("bare-64hex", REVIEW, re.compile(r"\b[0-9a-f]{64}\b"), None,
     "64-hex digests. Mostly prompt/description/skill hashes, which must NOT be redacted."),
)


def audit_text(text: str) -> dict[str, list[str]]:
    """Probe id -> the distinct matched values."""
    found: dict[str, list[str]] = {}
    for probe_id, _sev, pattern, predicate, _note in PROBES:
        seen: list[str] = []
        for m in pattern.finditer(text):
            value = m.group(0)
            if predicate is not None:
                try:
                    ok = predicate(value, text=text, start=m.start())
                except TypeError:
                    ok = predicate(value)
                if not ok:
                    continue
            if value not in seen:
                seen.append(value)
        if seen:
            found[probe_id] = seen
    return found


def audit_tree(root: Path) -> dict[str, dict[str, collections.Counter]]:
    """probe id -> {file -> Counter(value)}. Reads .jsonl / .json only."""
    out: dict[str, dict[str, collections.Counter]] = collections.defaultdict(dict)
    for path in sorted(Path(root).rglob("*")):
        if not path.is_file() or path.suffix not in (".jsonl", ".json"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for probe_id, values in audit_text(text).items():
            rel = str(path.relative_to(root))
            counter = collections.Counter()
            for v in values:
                counter[v] = text.count(v)
            out[probe_id][rel] = counter
    return out


def _severity(probe_id: str) -> str:
    return next(sev for pid, sev, *_ in PROBES if pid == probe_id)


def _note(probe_id: str) -> str:
    return next(note for pid, _s, _p, _pr, note in PROBES if pid == probe_id)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("root", type=Path)
    ap.add_argument("--json", action="store_true", help="machine-readable findings")
    ap.add_argument("--quiet", action="store_true", help="only print BLOCK findings")
    args = ap.parse_args(argv)

    if not args.root.exists():
        print(f"no such path: {args.root}", file=sys.stderr)
        return 2

    findings = audit_tree(args.root)
    n_files = sum(1 for p in args.root.rglob("*")
                  if p.is_file() and p.suffix in (".jsonl", ".json"))
    blocked = {k: v for k, v in findings.items() if _severity(k) == BLOCK}

    if args.json:
        print(json.dumps({
            "root": str(args.root),
            "files_scanned": n_files,
            "findings": {k: {f: dict(c) for f, c in v.items()} for k, v in findings.items()},
            "block": sorted(blocked),
        }, indent=2, sort_keys=True))
        return 1 if blocked else 0

    print(f"[audit] {n_files} file(s) under {args.root}")
    print("[audit] This is a BLOCKLIST. No findings means no rule fired — it is NOT")
    print("[audit] proof the tree is safe to publish. Read the REVIEW counts.")
    for probe_id, _sev, _pat, _pred, _n in PROBES:
        if probe_id not in findings:
            continue
        sev = _severity(probe_id)
        if args.quiet and sev != BLOCK:
            continue
        per_file = findings[probe_id]
        total = sum(sum(c.values()) for c in per_file.values())
        distinct = len({v for c in per_file.values() for v in c})
        print(f"\n  [{sev}] {probe_id}: {total} occurrence(s), {distinct} distinct, "
              f"{len(per_file)} file(s)")
        print(f"         {_note(probe_id)}")
        if sev == BLOCK:
            for f, c in sorted(per_file.items())[:20]:
                for v, n in c.most_common(5):
                    print(f"         {f}  x{n}  {v[:90]!r}")

    if blocked:
        print(f"\n[audit] FAIL — {len(blocked)} blocking class(es): {', '.join(sorted(blocked))}")
        print("[audit] Do NOT publish. Run scrub.py --apply, then re-audit.")
        return 1
    print("\n[audit] no blocking findings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

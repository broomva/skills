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

WHAT IT DOES NOT DO — AND THE POLARITY THAT MATTERS. This is a BLOCKLIST, so it
fails **OPEN**: any field nobody anticipated passes through untouched and lands in
whatever the fixtures are published to. That is not a hypothetical either. The first
version of this file had rules for the home directory, macOS temp roots, npx cache
hashes and credential-shaped assignments — and no rule whatsoever for IDENTITY. A
trial had read a Claude Code config JSON, so 3 of 703 fixtures carried, verbatim:

    "emailAddress":     "<the operator's real work address>"
    "organizationName": "<that address>'s Organization"
    "organizationUuid": "<a stable org identifier>"
    "userID":           "<a stable 64-hex user identifier>"

Every rule below was written after something got through. Assume the next one will
be too, and read `--check` as "the rules we have found no violation of", never as
"clean".

SO WHAT ACTUALLY CONTAINS THE EXPOSURE. Three things, in descending order of how
much they are worth:

1. **The fixtures are not in git** (BRO-2030 / this branch). Git history is forever
   and a public repo's objects are reachable by SHA even from a deleted branch. The
   payload lives in a release asset built by ``fixture_pack.py``, so a mistake is
   *revocable* — you can replace or delete an asset.
2. **A human looks before publishing.** ``fixture_pack.py pack`` runs this scrubber
   AND the independently-written auditor in ``fixture_audit.py``, and prints what it
   found; the operator reads that output and then decides to upload. The asset on a
   PUBLIC repo is PUBLICLY DOWNLOADABLE — relocation buys weight and permanence, it
   buys **no** secrecy.
3. **This scrubber**, which is the cheap automatic layer and the one that fails open.

The pre-commit gitleaks hook is a fourth layer and covers only credential SHAPES; it
would not have flagged an email address, and did not.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Union

#: A redaction's replacement: a `re.sub` template, or a function of the match.
Replacement = Union[str, Callable[["re.Match[str]"], str]]

#: The recording machine's home directory, replaced with a stable placeholder so the
#: fixtures stay diffable across machines instead of churning on every re-record.
HOME_PLACEHOLDER = "/Users/USER"

#: What a redacted email becomes. `.invalid` is reserved by RFC 2606 and can never
#: resolve, and the placeholder must not re-match the rule that produced it or
#: `--apply` stops being idempotent and every run churns the fixtures.
EMAIL_PLACEHOLDER = "REDACTED@REDACTED.invalid"

#: A JSON quote as it appears in a fixture. Recorded transcripts are NDJSON, and a
#: tool result carrying a JSON document has that document's quotes ESCAPED — the
#: config leak reads `\"emailAddress\": \"…\"` on the wire, not `"emailAddress": "…"`.
#: A rule written against the unescaped shape matches nothing in the file it was
#: written for, which is the mistake the credential rule's separator alternation
#: already cost once.
_Q = r'(?:\\{1,2}"|["\'])'

#: Identity-bearing key families. KEY-anchored, like the credential rule and for the
#: same reason: the VALUES here are UUIDs, 64-hex digests and ISO timestamps, and the
#: fixtures are *full* of those legitimately — `prompt_sha256`, `description_sha256`
#: and `skill_md_sha256` are 64-hex, they are the artifact binding replay depends on,
#: and 20,370 distinct event UUIDs are ordinary transcript plumbing. A value-shape
#: rule over either would either destroy the binding or redact 20k harmless ids.
#:
#: `org` gets its own alternatives because a trailing wildcard on three letters also
#: matches `original`.
_IDENTITY_NOUN = (
    r"(?:"
    r"account|organi[sz]ation|oauth|subscriber|subscription|customer|billing|"
    # `profile` is deliberately ABSENT. It reads like an identity noun and is not one
    # in practice: the only config field carrying it is `profileFetchedAt`, a
    # timestamp, while `--profile` is one of the most common non-identity CLI flags
    # there is. Including it redacted `--profile preview` and `--profile production`
    # out of 18 recorded deploy commands — graded tool INPUTS — to protect nothing.
    r"tenant|workspace|seat|owner|user|login|username|user_name|"
    r"email|phone|displayname|display_name|fullname|full_name|"
    r"org[_\-]?(?:id|uuid|guid|name|slug)|org(?![A-Za-z0-9_\-])"
    r")"
)

#: A key CONTAINING one of those nouns. The wildcards are what make it a rule about a
#: family rather than a list of the four field names one leak happened to contain:
#: `organizationRateLimitTier` and `userRateLimitTier` are covered without being named,
#: and so is the next sibling Anthropic adds.
#:
#: The leading boundary lookbehind is a PERFORMANCE requirement, not a semantic one.
#: One fixture embeds a 2.2 MB base64 PDF, and an unanchored `[A-Za-z0-9_\-]*` retries
#: at every position in it — 23 s for that rule on that one file, ~90 s for the whole
#: scrubber. The lookbehind rejects a mid-token position in one step (under 2 s), and
#: the `{0,40}` bounds keep any future pathological input bounded too.
_KEY_BOUNDARY = r"(?<![A-Za-z0-9_\-])"
_IDENTITY_KEY = rf"{_KEY_BOUNDARY}[A-Za-z0-9_\-]{{0,40}}{_IDENTITY_NOUN}[A-Za-z0-9_\-]{{0,40}}"

#: RFC 2606 / RFC 6761 reserved names. An address there is documentation by
#: definition and cannot identify anyone.
_RESERVED_EMAIL_DOMAINS = frozenset({
    "example.com", "example.net", "example.org", "example.edu",
})
_RESERVED_EMAIL_TLDS = (".invalid", ".test", ".localhost", ".example", ".local")

#: Service addresses that identify a *service*, not a person. `git@github.com` shows
#: up in every `git remote -v`, and redacting it would corrupt readable output for no
#: gain.
_SERVICE_EMAIL_ADDRESSES = frozenset({
    "git@github.com", "noreply@github.com", "actions@github.com",
    "noreply@anthropic.com",
})

#: A fixture is NDJSON, so a transcript's own newlines are the two characters `\` `n`.
#: An email rule that matches values therefore collides with them, in two directions,
#: and BOTH have to be handled or the rule corrupts the file it is protecting:
#:
#:   `\n@pytest.fixture`  — an escape abutting a decorator, matched because `n` is a
#:                          perfectly good local part. Not an address. Leave it.
#:   `\ndevteam@corp.com` — a REAL address after an escaped newline, matched as local
#:                          part `ndevteam`. Redacting the whole match eats the `n` and
#:                          leaves `\REDACTED…`, which is not a legal JSON escape — the
#:                          line stops parsing and replay scores ERROR on a fixture the
#:                          scrubber "cleaned". Keep the escape, redact the address.
_ESCAPE_CHARS = frozenset("nrtbfv0")


def _redact_email(m: re.Match[str]) -> str:
    """Email is the one place a VALUE-shape rule beats a key-shape rule.

    Guessing which 36-character strings are secret is whack-a-mole; an address is
    unambiguously shaped and unambiguously identifying, and it arrives under key
    names nobody can enumerate ahead of time — `emailAddress`, `author`,
    `Correspondence:` in a fetched paper, a bare `git log` line. So this one matches
    the value.
    """
    addr = m.group(0)
    local, _, domain = addr.rpartition("@")
    low_addr, low_domain = addr.lower(), domain.lower()
    if low_addr in _SERVICE_EMAIL_ADDRESSES:
        return addr
    if low_domain in _RESERVED_EMAIL_DOMAINS or low_domain.endswith(_RESERVED_EMAIL_TLDS):
        return addr
    # `acpx@0.12.0.patch` and `embedded-postgres@18.1.0-beta.16.patch` are pnpm patch
    # filenames, and they are email-shaped. A purely numeric label is the tell: it is
    # ordinary in a version string and essentially absent from real mail domains. This
    # cost four substitutions of real recorded content before it was added.
    if any(label.isdigit() for label in low_domain.split(".")):
        return addr

    after_backslash = m.start() > 0 and m.string[m.start() - 1] == "\\"
    if after_backslash and local[:1] in _ESCAPE_CHARS:
        if len(local) == 1:
            return addr
        return local[0] + EMAIL_PLACEHOLDER
    return EMAIL_PLACEHOLDER

#: Patterns redacted on `--apply`. Each carries WHY, because a redaction nobody can
#: justify later gets removed by the next person who finds it inconvenient.
#:
#: A replacement is either a template string or a callable, so a rule that needs to
#: consult the surrounding bytes (see :func:`_redact_email`) can, instead of being
#: forced into a regex that cannot express its exception.
REDACTIONS: tuple[tuple[str, re.Pattern[str], Replacement], ...] = (
    (
        # The recording machine's real home. Appears in tool results (ps, ls, find)
        # and identifies the operator.
        "home directory",
        re.compile(r"/Users/(?!USER\b)[A-Za-z0-9._-]+"),
        HOME_PLACEHOLDER,
    ),
    (
        # macOS per-boot temp roots: a machine fingerprint, and pure noise in a diff.
        # The negative lookahead is not cosmetic: without it the replacement matches
        # the pattern that produced it, so `--apply` re-substitutes an identical
        # string and `--check` reports dozens of "redactions" that change nothing.
        # The home rule's `(?!USER\b)` closes the same hole; this one was missed, and
        # the phantom counts are what surfaced it (67 in one file, 0 real).
        "macOS temp root",
        re.compile(r"/var/folders/(?!XX/XXXX\b)[A-Za-z0-9_]+/[A-Za-z0-9_]+"),
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
    (
        # THE ACCOUNT OBJECT, elided whole. This is the rule about the SHAPE rather
        # than about field names, and it is the one that covers what nobody has
        # thought of yet: the leak was a Claude Code config JSON whose `oauthAccount`
        # object carried nineteen fields, four of them identifying. Naming those four
        # leaves the other fifteen — and every field added next release — uncovered.
        #
        # Ordered FIRST of the identity rules so the object is gone before the
        # per-field rules have to be right about its contents.
        #
        # Depth is bounded at one nested object (`ccOnboardingFlags: {}` is real), so
        # a deeper shape does not match and falls through to the per-field rules. That
        # is a fail-open branch, stated rather than hidden.
        "account object",
        re.compile(
            rf"((?:{_Q})?{_KEY_BOUNDARY}[A-Za-z0-9_\-]{{0,40}}"
            rf"(?:oauth|credential|account)[A-Za-z0-9_\-]{{0,40}}"
            rf"(?:{_Q})?\s*:\s*)"
            r"\{(?!REDACTED_account_object\})(?:[^{}]|\{[^{}]*\})*\}",
            re.IGNORECASE,
        ),
        r"\1{REDACTED_account_object}",
    ),
    (
        # IDENTITY-BEARING JSON FIELDS. Quoted STRING values only, which is not a
        # simplification but the thing that keeps the rule quiet: `userModified: false`
        # (116 occurrences), `minUserTurnsBeforeFeedback: 3`, `seatTier: null` and
        # `orgModelDefaultCache: null` all carry an identity noun in the key and
        # nothing identifying in the value, and a rule that rewrote booleans and nulls
        # would corrupt 116 fixtures to redact 0 facts.
        #
        # The separator is `:` or `=` — never bare whitespace, unlike the credential
        # rule. `token` does not occur in English prose next to a 36-char blob;
        # `user`, `email` and `owner` occur in prose constantly, and a whitespace
        # alternation here would redact sentences.
        "identity-bearing field",
        re.compile(
            rf"((?:{_Q})?{_IDENTITY_KEY}(?:{_Q})?\s*[:=]\s*{_Q})"
            r'(?!REDACTED[\\"\'])'
            r'([^"\\]{1,240})',
            re.IGNORECASE,
        ),
        r"\1REDACTED",
    ),
    (
        # The same class as a CLI FLAG, for a transcript that recorded a `ps` line or a
        # documented invocation rather than a config file. The mandatory leading `-` is
        # what keeps this out of prose and out of code: `user`, `email` and `owner` are
        # ordinary English words, so a rule that accepted a bare key here would redact
        # sentences. `--organization-id VALUE` cannot be a sentence.
        "identity-bearing flag",
        re.compile(
            rf"({_KEY_BOUNDARY}--?[A-Za-z0-9_\-]{{0,40}}{_IDENTITY_NOUN}"
            rf"[A-Za-z0-9_\-]{{0,40}}(?:\s*=\s*|\s+))"
            r"(?!REDACTED\b)"
            r"([A-Za-z0-9@._+\-]{2,240})",
            re.IGNORECASE,
        ),
        r"\1REDACTED",
    ),
    (
        # And as an ENV VAR — `ANTHROPIC_ORGANIZATION_ID=…` in a recorded `env` dump.
        #
        # The uppercase lookahead is doing real work and its absence was a real bug.
        # `[A-Z0-9_]` under `re.IGNORECASE` ALSO MATCHES LOWERCASE, so a rule whose
        # comment said "SCREAMING_SNAKE keys only" happily matched `user = ` in a
        # recorded Python file and rewrote `user = get_current_user()` to
        # `user = REDACTED()`. A scoped `(?-i:)` assertion is the fix: the key and its
        # `=` must be genuinely uppercase, checked case-sensitively, while the noun
        # itself still matches case-insensitively so `ORGANIZATION` is found.
        "identity-bearing env var",
        re.compile(
            rf"({_KEY_BOUNDARY}(?=(?-i:[A-Z0-9_]{{1,60}}=))"
            rf"[A-Z0-9_]{{0,40}}{_IDENTITY_NOUN}[A-Z0-9_]{{0,40}}=)"
            r"(?!REDACTED\b)"
            r"([A-Za-z0-9@._+\-]{2,240})",
            re.IGNORECASE,
        ),
        r"\1REDACTED",
    ),
    (
        # EMAIL ADDRESSES, by value shape. See _redact_email for why the polarity
        # flips here, and why `git@github.com` and the RFC 2606 reserved domains stay.
        "email address",
        re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9](?:[A-Za-z0-9.\-]*[A-Za-z0-9])?\.[A-Za-z]{2,24}"),
        _redact_email,
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

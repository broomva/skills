#!/usr/bin/env python3
"""format_lint — flag unsupported platform claims and unsourced precision in drafts.

Severity follows the ledger's GRADE, not the author's confidence:

    refuted            ERROR  contradicted by a primary source that was loaded
    contested          WARN   the literature genuinely disagrees
    unverified         WARN   origin could not be located — NOT proof of falsity
    folklore           WARN   circulates as fact with no located basis
    hypothesis_as_fact WARN   plausible mechanism asserted as established

The refuted/unverified split is the point. "I could not find a source" is a statement
about a search, not about the world, and a linter that conflates the two manufactures
exactly the false confidence it exists to prevent.

Usage:
    format_lint.py <file>...        lint files ( - for stdin )
    format_lint.py <f> --json       machine-readable
    format_lint.py <f> --strict     warnings also fail the exit code

Exit: 0 clean/warnings, 1 on ERROR (or any finding under --strict), 2 on bad input.
"""
from __future__ import annotations

import argparse
import errno
import json
import re
import sys
from pathlib import Path

LEDGER = Path(__file__).resolve().parent.parent / "references" / "claims-ledger.json"

# errno values that describe the PATH THE OPERATOR SUPPLIED rather than the machine.
# Anything outside this set is operational and propagates with its real traceback.
INPUT_ERRNOS = frozenset(
    getattr(errno, name)
    for name in ("ENOENT", "EACCES", "EPERM", "EISDIR", "ENOTDIR", "ENAMETOOLONG", "ELOOP")
    if hasattr(errno, name)
)


class LedgerError(Exception):
    """A ledger is malformed. Catchable — `load_ledger` must not kill an embedding host.

    But it is deliberately NOT caught by `corpus_sweep.scan`'s crash handler, which
    re-raises it. A ledger that cannot be loaded is not "this file crashed"; treating it
    that way is what let a broken comparison ledger report every finding as new coverage.
    """


GRADE_SEVERITY = {
    "refuted": "ERROR",
    "contested": "WARN",
    "unverified": "WARN",
    "folklore": "WARN",
    "hypothesis_as_fact": "WARN",
}

ALLOW_RX = re.compile(r"format-lint:\s*allow[= ]([A-Za-z0-9_, -]+?)\s*(?:-->|$)")
CONTROL_RX = re.compile(r"^\s*<!--\s*format-lint:\s*(disable|enable)\s*-->\s*$")
MARKER_BLANK_RX = re.compile(r"<!--\s*format-lint:.*?-->")
# Markdown lines that begin a new logical unit and must not fuse with the previous one.
STRUCTURAL_RX = re.compile(r"^\s*(?:#{1,6}\s|[-*+]\s|\d+[.)]\s|\||>|-{3,}\s*$|\*{3,}\s*$)")
# Headings, table rows, blockquotes and rules are self-contained: following prose is a
# separate thought. List items are NOT — an indented continuation belongs to its bullet.
STANDALONE_RX = re.compile(r"^\s*(?:#{1,6}\s|\||>|-{3,}\s*$|\*{3,}\s*$)")

# A rule must not fire when the sentence denies, corrects, or attributes the claim —
# otherwise the linter punishes the corrections it exists to promote.
SENT_SPLIT_RX = re.compile(r"(?<=[.!?;])\s+")

# A fence is a run of 3+ of ONE delimiter, then an info string. Indentation is NOT bounded
# to CommonMark's 3 spaces: a fence nested in a list is legitimately indented further, and
# for a gate that ERRORs, wrongly linting quoted code is worse than exempting one extra
# block — an opener that swallows the rest of the file is already caught as unclosed-fence.
FENCE_RX = re.compile(r"^[ 	]*(?P<fence>`{3,}|~{3,})(?P<info>.*)$")


def _negated_at(line: str, start: int) -> bool:
    """True when the SENTENCE containing `start` denies/corrects/attributes the claim.

    Line-level scoping was too coarse: an unrelated "This is not complicated." earlier on
    the same line suppressed a live assertion after it.
    """
    pos = 0
    for sent in SENT_SPLIT_RX.split(line):
        seg = line.find(sent, pos)
        if seg == -1:
            seg = pos
        if seg <= start < seg + len(sent):
            return bool(NEGATION_RX.search(sent))
        pos = seg + len(sent)
    return bool(NEGATION_RX.search(line))


NEGATION_RX = re.compile(
    r"(?i)\b(?:not|never|no longer|isn't|is ?n't|aren't|doesn't|does not|don't|do not|"
    r"myth|false|untrue|debunk\w*|misquot\w*|misattribut\w*|unfounded|no evidence|"
    r"claims? that|allegedly|supposedly|so-called|refut\w*|contrary to)\b"
)


def _compile_or_fail(pattern: str, what: str, fail) -> None:
    """Any failure to compile means an unusable ledger — catch the CLASS, not a list.

    `re.compile` raises more than `re.error`: OverflowError on an absurd repetition count,
    RecursionError on deep nesting, and the set is not fixed across Python versions. Naming
    the two that were reported would leave the next one to escape as a traceback and exit 1
    — the code that means "findings were present".

    `Exception`, not `BaseException`, is deliberate: KeyboardInterrupt, SystemExit and
    GeneratorExit are BaseExceptions and propagate on their own. MemoryError does NOT —
    it subclasses Exception — so it is re-raised explicitly above, because resource
    exhaustion is an operational failure and not a malformed ledger.

    WHAT THIS CANNOT SEE: a pattern that compiles and then explodes at MATCH time —
    `(a+)+$` is valid, loads cleanly, and hangs on the first adversarial input. Validating
    that is a halting problem in miniature, and a heuristic for it would be a weaker gate
    than the one it guards. A ledger is trusted configuration, authored by whoever runs the
    tool; this is stated in SKILL.md rather than papered over.
    """
    try:
        re.compile(pattern)
    except MemoryError:
        # Resource exhaustion is an OPERATIONAL failure, not bad input. Reporting it as an
        # invalid ledger sends the reader to fix a pattern that is fine, and exits 2 ("bad
        # input") for a condition that is nothing of the sort.
        raise
    except Exception as exc:                       # noqa: BLE001 — see docstring
        fail(f"{what}: {type(exc).__name__}: {exc}")


def load_ledger(path: Path = LEDGER) -> dict:
    # THE ERROR SPACE, ENUMERATED ONCE. Loading a ledger can fail in three unrelated ways
    # and they must not be conflated, because the exit code is the operator's only signal:
    #
    #   ABOUT THE PATH OR CONTENT YOU SUPPLIED -> LedgerError -> exit 2 ("bad input")
    #       missing, unreadable-by-permission, a directory, not UTF-8, not JSON, not an
    #       object, or schema-invalid. The operator fixes the ledger.
    #
    #   ABOUT THE MACHINE -> propagate -> the real traceback
    #       MemoryError, and any OSError whose errno is not one of the input-class codes
    #       below (EIO on a failing disk, ENOSPC, ENOMEM...). The operator fixes the host,
    #       and calling that "bad input" would send them to edit a ledger that is fine.
    #
    #   ABOUT THE OPERATOR -> propagate untouched
    #       KeyboardInterrupt, SystemExit, GeneratorExit — BaseExceptions, never caught.
    #
    # Each of these was learned from a separate escape: JSONDecodeError, then MemoryError,
    # then UnicodeDecodeError, then EIO. Enumerating beats patching one edge per round.
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        raise LedgerError(f"format_lint: ledger not found at {path}") from None
    except OSError as exc:
        if exc.errno not in INPUT_ERRNOS:
            raise                                  # operational: not a claim about input
        raise LedgerError(
            f"format_lint: ledger at {path} could not be read: {exc}"
        ) from None

    # DECODE and PARSE are classified BY PHASE, not by exception type.
    #
    # Listing types did not work. Five rounds found five more that a decoder or parser can
    # raise — JSONDecodeError, UnicodeDecodeError, RecursionError on deep nesting, and
    # ValueError on an integer past CPython 3.11's 4300-digit conversion limit — and the
    # set is neither documented nor stable across versions, so the sixth was always coming.
    #
    # The invariant that IS stable: if decoding or parsing this text fails at all, the text
    # is not a usable ledger. That is a statement about the content, so it is bad input.
    # MemoryError is the sole exception, re-raised because it is about the machine; the
    # BaseExceptions (KeyboardInterrupt, SystemExit, GeneratorExit) are never caught.
    # Same shape as `_compile_or_fail` — catch the class, name the type in the message.
    try:
        # utf-8-sig, not utf-8: a leading BOM is what Windows editors write, and the file is
        # otherwise perfectly good JSON that `json.loads` would reject.
        text = raw.decode("utf-8-sig")
    except MemoryError:
        raise
    except Exception as exc:                       # noqa: BLE001 — see above
        raise LedgerError(
            f"format_lint: ledger at {path} is not valid UTF-8: {type(exc).__name__}: {exc}"
        ) from None

    try:
        data = json.loads(text)
    except MemoryError:
        raise
    except Exception as exc:                       # noqa: BLE001 — see above
        raise LedgerError(
            f"format_lint: ledger at {path} is not valid JSON: {type(exc).__name__}: {exc}"
        ) from None

    if not isinstance(data, dict):
        raise LedgerError(
            f"format_lint: ledger at {path} must be a JSON object, got {type(data).__name__}"
        )

    # SCHEMA VALIDATION, enumerated rather than discovered one crash at a time. Every
    # malformed shape must surface as LedgerError at LOAD, because anything that escapes
    # here becomes a traceback and exit 1 — the code that means "findings were present".
    def _fail(what: str) -> None:
        raise LedgerError(f"format_lint: ledger at {path}: {what}")

    try:
        _validate_schema(data, _fail)
    except LedgerError:
        raise
    except MemoryError:
        raise
    except Exception as exc:                       # noqa: BLE001
        # A backstop, not a substitute for the explicit guards above. Every check in
        # `_validate_schema` is written to reject hostile input politely; this catches the
        # one that was missed. Four rounds each found a different unguarded operation, so
        # the guarantee "this tool never tracebacks on a bad ledger" needed to stop
        # depending on my having thought of every field.
        raise LedgerError(
            f"format_lint: ledger at {path} is malformed: {type(exc).__name__}: {exc}"
        ) from None

    return data


LEDGER_KEYS = frozenset(
    {"_meta", "refuted", "folklore", "hypothesis_as_fact", "precision_without_source"}
)
RULE_KEYS = frozenset({"id", "pattern", "message", "instead", "grade", "citation_resolves"})
PRECISION_KEYS = frozenset({"pattern", "marker_regex", "message", "instead", "window_lines"})


def _validate_schema(data: dict, _fail) -> None:
    # UNKNOWN KEYS ARE REJECTED, because the failure mode of accepting them is silent.
    # `precision_without_sources` — one letter — loaded cleanly and switched off the entire
    # precision rule class, and the run then reported a document as clean. A typo that
    # changes what is checked, without changing what is said, is the worst outcome this
    # tool has; unknown keys are far more often that than deliberate extension.
    unknown = sorted(set(data) - LEDGER_KEYS)
    if unknown:
        _fail(
            f"unknown top-level key(s) {unknown} — expected only {sorted(LEDGER_KEYS)}. "
            "A misspelled container silently disables its whole rule class"
        )

    for cat in ("refuted", "folklore", "hypothesis_as_fact"):
        rules = data.get(cat, [])
        if not isinstance(rules, list):
            _fail(f"'{cat}' must be a list, got {type(rules).__name__}")
        for n, r in enumerate(rules):
            if not isinstance(r, dict):
                _fail(f"'{cat}'[{n}] must be an object, got {type(r).__name__}")
            for field in ("id", "pattern", "message"):
                if not isinstance(r.get(field), str) or not r[field].strip():
                    _fail(f"'{cat}'[{n}] needs a non-empty string '{field}'")
            stray = sorted(set(r) - RULE_KEYS)
            if stray:
                _fail(
                    f"'{cat}'[{n}] has unknown key(s) {stray} — expected only "
                    f"{sorted(RULE_KEYS)}. A misspelled `citation_resolves` or `grade` "
                    "changes what the rule does without changing what it says"
                )
            grade = r.get("grade")
            # isinstance BEFORE membership: `in` on an unhashable value (a JSON array or
            # object) raises TypeError, and a schema check that crashes on hostile input is
            # the thing this whole function exists to prevent.
            if not isinstance(grade, str) or grade not in GRADE_SEVERITY:
                _fail(
                    f"rule {r['id']} has unknown grade {grade!r} — a typo must "
                    "not silently downgrade severity"
                )
            if "citation_resolves" in r and not isinstance(r["citation_resolves"], bool):
                _fail(
                    f"rule {r['id']}: citation_resolves must be a JSON boolean — a "
                    "non-boolean is truthy and would silently suppress findings"
                )
            # The documented invariant, made structural. SKILL.md promises a citation never
            # silences a `refuted` claim, because a misquotation with a link attached is
            # still a misquotation — but nothing stopped a ledger from opting one in, which
            # is a promise the code did not keep.
            if grade == "refuted" and r.get("citation_resolves"):
                _fail(
                    f"rule {r['id']}: a `refuted` rule must not set citation_resolves — a "
                    "citation cannot un-refute a claim contradicted by a loaded source"
                )
            _compile_or_fail(r["pattern"], f"rule {r['id']} has an invalid pattern", _fail)
            if re.compile(r["pattern"]).search(""):
                _fail(
                    f"rule {r['id']}: pattern matches the empty string, so it fires on "
                    "every block regardless of content"
                )

    # ABSENT and PRESENT-BUT-NULL are different things, and `.get()` conflates them.
    # `{"precision_without_source": null}` loaded cleanly and silently disabled an entire
    # rule class — the quietest possible failure for a gate, and the one it least affords.
    if "precision_without_source" in data:
        pws = data["precision_without_source"]
        if not isinstance(pws, dict):
            _fail(f"'precision_without_source' must be an object, got {type(pws).__name__}")
        stray = sorted(set(pws) - PRECISION_KEYS)
        if stray:
            # Third level, same failure shape: a typo that REMOVES a required key is caught
            # by the required-field check, but `window_liness` just falls back to the
            # default window and changes the rule's reach without saying so.
            _fail(
                f"'precision_without_source' has unknown key(s) {stray} — expected only "
                f"{sorted(PRECISION_KEYS)}"
            )
        for field in ("pattern", "marker_regex", "message"):
            if not isinstance(pws.get(field), str) or not pws[field].strip():
                _fail(f"precision_without_source needs a non-empty string '{field}'")
        for field in ("pattern", "marker_regex"):
            _compile_or_fail(
                pws[field], f"precision_without_source.{field} is invalid", _fail
            )
        # A marker_regex matching the empty string is satisfied by every block, which
        # silently switches the whole precision rule off. A gate that stops checking
        # without saying so is the failure this skill exists to prevent.
        if re.compile(pws["marker_regex"]).search(""):
            _fail(
                "precision_without_source.marker_regex matches the empty string, so every "
                "block counts as cited and the rule can never fire"
            )
        if re.compile(pws["pattern"]).search(""):
            _fail("precision_without_source.pattern matches the empty string")
        window = pws.get("window_lines", 3)
        # bool is an int subclass, and a window of `True` is a silent 1.
        if "window_lines" in pws and (not isinstance(window, int) or isinstance(window, bool)):
            _fail("precision_without_source.window_lines must be an integer")
        if not 0 <= window <= 100:
            _fail(
                f"precision_without_source.window_lines must be between 0 and 100, got {window}"
                " — a window wide enough to span the document makes any citation anywhere"
                " suppress every precision finding"
            )


def _fence_and_frontmatter(lines: list[str]) -> tuple[set[int], list[dict]]:
    """Exempt fenced blocks and *well-formed* YAML frontmatter; report malformed ones.

    Frontmatter requires a closing `---` AND at least one `key:` line — otherwise a
    Markdown horizontal rule at the top of a file would exempt the whole document.
    An unclosed fence is reported rather than silently swallowing the remainder.
    """
    exempt: set[int] = set()
    problems: list[dict] = []

    # Frontmatter is resolved FIRST and the fence scan starts after it. Ordering matters:
    # a bare ``` inside a YAML value used to open a fence that no `---` could close, so the
    # whole document became exempt and every live claim in it was silently missed.
    body_start = 0
    # Column-zero only. YAML document markers live at column 0; an INDENTED `---` is
    # ordinary content inside a block scalar, and `.strip()` mistook it for the closing
    # delimiter — ending the frontmatter early and linting the rest of the YAML as prose.
    if lines and lines[0].rstrip() == "---":
        close = next((j for j in range(1, len(lines)) if lines[j].rstrip() == "---"), None)
        if close is not None and any(
            re.match(r"^[A-Za-z_][\w-]*\s*:", lines[j]) for j in range(1, close)
        ):
            exempt |= set(range(0, close + 1))
            body_start = close + 1

    open_at: int | None = None
    open_char = ""
    open_len = 0
    for i in range(body_start, len(lines)):
        line = lines[i]
        m = FENCE_RX.match(line)
        if open_at is None:
            # A backtick opener's info string may not contain a backtick (CommonMark), so
            # a prose line like ``` `a` vs `b` ``` is text, not the start of a code block.
            if m and not (m.group("fence")[0] == "`" and "`" in m.group("info")):
                open_at = i
                open_char = m.group("fence")[0]
                open_len = len(m.group("fence"))
                exempt.add(i)
            continue
        exempt.add(i)
        # Closing needs the SAME character, a run at least as long, and nothing after it.
        # Tracking only "starts with ``` or ~~~" let a ``` line inside a ```` block close
        # it early — the remainder of the block was then linted as prose, and a ~~~ could
        # close a ``` fence.
        if (
            m
            and m.group("fence")[0] == open_char
            and len(m.group("fence")) >= open_len
            and not m.group("info").strip()
        ):
            open_at = None
    if open_at is not None:
        problems.append(
            {
                "line": open_at + 1,
                "severity": "ERROR",
                "category": "lint_control",
                "id": "unclosed-fence",
                "matched": open_char * open_len,
                "message": "An unclosed code fence exempts every line to end of file.",
                "instead": f"Close the fence with {open_char * open_len} on its own line.",
            }
        )

    return exempt, problems



def _control_regions(
    lines: list[str], fenced: set[int] | None = None
) -> tuple[set[int], list[dict], list[tuple[int, int]]]:
    """`<!-- format-lint: disable -->` … `enable`, as an exact standalone comment.

    Returns (suppressed line indices, structural problems, region spans).

    Guards: an unclosed region is an ERROR and a nested disable is an ERROR — both are
    malformed, and both silently extend suppression.

    There is deliberately NO "this region covers most of the document" heuristic. One
    existed and was defeated six times in six review rounds, each by a different way of
    padding the denominator: fenced code, frontmatter, lint's own markers, bare `---`
    rules, `-` bullets, `|---|---|` separators, `>`, `#`, and finally ordinary HTML
    comments. A ratio over "prose" invites an argument about what counts as prose, and
    every answer to that argument was wrong at a new edge. What the reader actually needs
    is not a verdict about proportion but the fact itself, which is reported instead: see
    `suppressed-findings`. A fact cannot be padded.
    """
    off: set[int] = set()
    problems: list[dict] = []
    open_at: int | None = None
    spans: list[tuple[int, int]] = []

    fenced = fenced or set()
    for i, line in enumerate(lines):
        m = None if i in fenced else CONTROL_RX.match(line)
        if not m:
            if open_at is not None:
                off.add(i)
            continue
        off.add(i)
        if m.group(1) == "disable":
            if open_at is not None:
                problems.append(
                    {
                        "line": i + 1, "severity": "ERROR", "category": "lint_control",
                        "id": "nested-disable", "matched": "format-lint: disable",
                        "message": "A disable region is already open; nesting is collapsed by a single enable.",
                        "instead": "Close the first region before opening another.",
                    }
                )
            else:
                open_at = i
        else:
            if open_at is not None:
                spans.append((open_at, i))
            open_at = None

    if open_at is not None:
        problems.append(
            {
                "line": open_at + 1, "severity": "ERROR", "category": "lint_control",
                "id": "unclosed-disable", "matched": "format-lint: disable",
                "message": "A disable region was never closed, so every rule is off to end of file.",
                "instead": "Close it with `<!-- format-lint: enable -->` right after the quoted material.",
            }
        )

    return off, problems, spans


def _allowed_ids(lines: list[str], idx: int) -> set[str]:
    """Rule ids suppressed on THIS line only.

    Current-line-only by design: a marker that also covered the next line let one
    comment excuse two separate assertions.
    """
    m = ALLOW_RX.search(lines[idx]) if 0 <= idx < len(lines) else None
    return {s.strip() for s in m.group(1).split(",") if s.strip()} if m else set()


def _blocks(lines: list[str], skip: set[int]) -> list[tuple[str, list[int]]]:
    """Join hard-wrapped lines into paragraph blocks, keeping a char->line map.

    Real markdown wraps at ~90 columns, so a claim routinely straddles a newline. Matching
    per raw line silently misses those — which is how a real-world article containing the
    exact fabrication this linter was built to catch came back clean.
    """
    out: list[tuple[str, list[int]]] = []
    buf: list[str] = []
    owner: list[int] = []

    def flush() -> None:
        if buf:
            joined = " ".join(buf)
            assert len(joined) == len(owner), "char->line map desynchronised"
            out.append((joined, owner[:]))

    for i, line in enumerate(lines):
        if i in skip or not line.strip() or STRUCTURAL_RX.match(line):
            # A heading, list item, table row, blockquote or rule starts a NEW block.
            # Fusing them would let "- polished aesthetic" + "- minimalism is dead" read as
            # one claim, and would let a negation in one bullet excuse the next.
            flush()
            buf, owner = [], []
            if i in skip or not line.strip():
                continue
        # Blank out format-lint's own control/allow comments, offset-preserving. They are
        # metadata, not prose — and a rule id such as `sends-3-5x-likes` literally contains
        # the pattern it names, so an unblanked marker matches itself.
        seg = MARKER_BLANK_RX.sub(lambda m: " " * len(m.group(0)), line).strip()
        if not seg:
            flush()
            buf, owner = [], []
            continue
        if buf:
            owner.append(i)  # the joining space belongs to the line it pulls in
        buf.append(seg)
        owner.extend([i] * len(seg))
        if STANDALONE_RX.match(line):
            flush()
            buf, owner = [], []
    flush()
    return out


def _line_of(owner: list[int], offset: int) -> int:
    return owner[min(offset, len(owner) - 1)] if owner else 0


def lint_text(text: str, ledger: dict, _honour_regions: bool = True) -> list[dict]:
    """Lint `text`. `_honour_regions=False` is internal: it lints as if every disable
    region were absent, which is how the suppression report learns what a region hid.

    It is a FLAG rather than a text substitution on purpose. Rewriting the marker comments
    to neutralise them changes the document the second pass sees — the replacement text is
    no longer recognised as lint metadata, so it joins the surrounding paragraph and can
    change what matches and where.
    """
    lines = text.splitlines()
    exempt, problems = _fence_and_frontmatter(lines)
    ctrl_off, ctrl_problems, spans = _control_regions(lines, exempt)
    skip = exempt | (ctrl_off if _honour_regions else set())
    findings: list[dict] = list(problems) + list(ctrl_problems) if _honour_regions else []

    # What did each disable region actually hide? Re-lint with the regions inactive and
    # diff. This replaces a coverage-ratio heuristic that six review rounds defeated with
    # six different kinds of padding: the reader is told what was suppressed rather than
    # given a verdict about how much of the file it was.
    if _honour_regions and spans:
        uncensored = lint_text(text, ledger, _honour_regions=False)
        # Bucket by line ONCE. Filtering the whole list per region is quadratic, and a
        # document with thousands of regions is exactly the shape a batch sweep produces
        # (measured: 4x the time for 2x the regions before this).
        #
        # No lint_control filter is needed: the inner pass returns claim findings only
        # (see the `if _honour_regions else []` above), so filtering them would be dead
        # code — and a mutant that removed it could not be killed, which is how it was found.
        by_line: dict[int, list[dict]] = {}
        for f in uncensored:
            by_line.setdefault(f["line"], []).append(f)
        for lo, hi in spans:
            hidden = [f for ln in range(lo + 2, hi + 1) for f in by_line.get(ln, ())]
            if hidden:
                ids_ = ", ".join(sorted({f["id"] for f in hidden}))
                hides_error = any(f["severity"] == "ERROR" for f in hidden)
                findings.append(
                    {
                        "line": lo + 1,
                        # Severity is INHERITED from the worst thing the region hides.
                        # Suppressing a WARN is ordinary editorial practice; suppressing an
                        # ERROR must not turn a failing document into a passing one.
                        # Removing the old coverage heuristic dropped this by accident: a
                        # file whose only content was a disabled `refuted` claim went from
                        # exit 1 to exit 0.
                        "severity": "ERROR" if hides_error else "WARN",
                        "category": "lint_control",
                        "id": "suppressed-findings",
                        "matched": "format-lint: disable",
                        "message": (
                            f"This region hides {len(hidden)} finding(s) on lines "
                            f"{lo + 2}-{hi}: {ids_}."
                            + (" One of them is an ERROR." if hides_error else "")
                        ),
                        "instead": (
                            "Legitimate when you are quoting a claim in order to correct it. "
                            "Scope it to the quotation, and prefer an inline "
                            "`allow=<rule-id>` marker so the suppression names what it hides."
                        ),
                    }
                )

    blocks = _blocks(lines, skip)

    # Some rules complain "this circulates with no located source". For THOSE, a sentence
    # supplying a resolvable source is the correction the rule asks for, so it must not
    # fire — "According to Instagram, its algorithm demotes non-original accounts: <link>"
    # is true, cited, and was flagged as folklore until this existed.
    #
    # THIS IS A DELIBERATE, DOCUMENTED BYPASS, opted into PER RULE (`citation_resolves`)
    # and scoped to the claim's own PARAGRAPH.
    pws_cfg = ledger.get("precision_without_source") or {}
    cite_rx = re.compile(pws_cfg["marker_regex"], re.I) if pws_cfg.get("marker_regex") else None

    def _cited_in(btext: str) -> bool:
        """Scoped to the claim's OWN paragraph, deliberately narrower than the +/-3-line
        window the precision rule uses.

        A line window let a URL in a DIFFERENT paragraph — even one ABOVE the claim —
        silence it, which turns "cite your source" into "put a link somewhere nearby".
        Block scope still spans a hard wrap, which is the only thing it needed to span.
        """
        return bool(cite_rx.search(btext)) if cite_rx else False

    for category in ("refuted", "folklore", "hypothesis_as_fact"):
        for rule in ledger.get(category, []):
            grade = rule.get("grade", category)
            severity = GRADE_SEVERITY.get(grade, "WARN")
            rx = re.compile(rule["pattern"])
            for btext, owner in blocks:
                for m in rx.finditer(btext):
                    if _negated_at(btext, m.start()):
                        continue
                    lo = _line_of(owner, m.start())
                    hi = _line_of(owner, m.end() - 1)
                    spanned = range(lo, hi + 1)
                    if any(rule["id"] in _allowed_ids(lines, k) for k in spanned):
                        continue
                    # Opt-in, PER RULE — see `citation_resolves` in the ledger. Grade was
                    # too coarse: `three-second-hook`'s complaint is that every located
                    # source is a content farm, so a URL satisfies the bypass while
                    # confirming the complaint. Absent key = no bypass.
                    if rule.get("citation_resolves") and _cited_in(btext):
                        continue
                    findings.append(
                        {
                            "line": lo + 1, "severity": severity, "category": category,
                            "grade": grade, "id": rule["id"],
                            "matched": " ".join(m.group(0).split())[:80],
                            "message": rule["message"], "instead": rule.get("instead", ""),
                        }
                    )

    pws = ledger.get("precision_without_source")
    if pws:
        rx = re.compile(pws["pattern"])
        window = int(pws.get("window_lines", 3))
        # A marker must look like a RESOLVABLE locator. A bare "https://" or the
        # substring "PMC" is not a citation.
        marker_rx = re.compile(pws["marker_regex"], re.I)
        for btext, owner in blocks:
            for m in rx.finditer(btext):
                if _negated_at(btext, m.start()):
                    continue
                lo = _line_of(owner, m.start())
                hi = _line_of(owner, m.end() - 1)
                if any("unsourced-precision" in _allowed_ids(lines, k) for k in range(lo, hi + 1)):
                    continue
                blob = "\n".join(lines[max(0, lo - window) : min(len(lines), hi + window + 1)])
                if marker_rx.search(blob):
                    continue
                findings.append(
                    {
                        "line": lo + 1, "severity": "WARN",
                        "category": "precision_without_source", "grade": "unverified",
                        "id": "unsourced-precision",
                        "matched": " ".join(m.group(0).split())[:80],
                        "message": pws["message"],
                        "instead": "Cite a resolvable URL or DOI containing that figure, or make the claim qualitative.",
                    }
                )

    findings.sort(key=lambda f: (f["line"], f["id"]))
    return findings


def render(label: str, findings: list[dict]) -> str:
    if not findings:
        return f"[format-lint] {label}: clean"
    out = [f"[format-lint] {label}: {len(findings)} finding(s)"]
    for f in findings:
        grade = f.get("grade", f["category"])
        out.append(f"  {f['severity']:<5} L{f['line']}  ({f['id']} · {grade})  «{f['matched']}»")
        out.append(f"        {f['message']}")
        if f["instead"]:
            out.append(f"        → {f['instead']}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="format_lint")
    ap.add_argument("files", nargs="+")
    ap.add_argument("--json", action="store_true", dest="as_json")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--ledger", type=Path, default=LEDGER)
    args = ap.parse_args(argv)

    try:
        ledger = load_ledger(args.ledger)
    except LedgerError as exc:
        print(exc, file=sys.stderr)
        return 2
    results: dict[str, list[dict]] = {}
    for spec in args.files:
        if spec == "-":
            results["<stdin>"] = lint_text(sys.stdin.read(), ledger)
            continue
        p = Path(spec)
        if not p.exists():
            print(f"format_lint: no such file: {spec}", file=sys.stderr)
            return 2
        results[str(p)] = lint_text(p.read_text(encoding="utf-8", errors="replace"), ledger)

    if args.as_json:
        print(json.dumps(results, indent=2))
    else:
        for label, findings in results.items():
            print(render(label, findings))

    flat = [f for fs in results.values() for f in fs]
    if args.strict and flat:
        return 1
    return 1 if any(f["severity"] == "ERROR" for f in flat) else 0


if __name__ == "__main__":
    raise SystemExit(main())

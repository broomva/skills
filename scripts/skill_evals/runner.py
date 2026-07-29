#!/usr/bin/env python3
"""skill-evals — run a skill's prompt set through a real agent CLI and grade it.

BRO-2005. The instrument the skill-QA arc depends on: does a skill's *description*
actually cause the model to fire it on the prompts it should fire on, and stay
quiet on the near-misses it should not?

    python3 scripts/skill_evals/runner.py --skill checkit --trials 3
    python3 scripts/skill_evals/runner.py --skill checkit --replay fixtures/checkit

Four properties are non-negotiable, each closing a named failure mode:

**Isolated runs.** Every trial gets a fresh temp cwd containing only the skill
under test, run with ``--setting-sources project`` so the user's 149 installed
skills, hooks and MCP servers are excluded. Not hygiene — a dirty tree lets the
agent recover skill content *without triggering*, scoring a trigger failure as a
pass. The skill's own ``evals/`` directory is excluded from the copy for the same
reason: it is the answer key.

That isolation is *environmental* as well as filesystem-scoped (BRO-2018). A fresh
cwd does nothing about a skill script that resolves its state from ``$HOME`` — and
they do: p9 writes ``~/.config/broomva/p9``, kg locates the entire workspace at
``Path.home()/"broomva"``. Since a positive trial exists precisely to make the agent
run those scripts, the faithful path was also the destructive one. ``skill_evals.jail``
gives each case a deny-by-default environment with ``HOME`` inside the workspace;
``--verify-jail`` proves it holds before a live suite spends anything.

**Distribution, not verdict.** N trials per case (default 3), reported as a
per-case pass rate plus an aggregate. One trial is an anecdote, and the report
says so: fewer trials than requested is an ERROR, never a silent clamp.

**Outcomes, not paths.** A run that fires the skill on turn 5 and lands the right
answer passes exactly like one that fires on turn 1. The grader asserts *that* the
skill fired and *what* the run produced, never the route.

**Real CLI, with a replay path bound to the artifact under test.** ``LiveRunner``
shells out to the actual binary and is the default; ``--record`` saves transcripts
and ``--replay`` re-grades them so CI stays free. Each fixture records a hash of
the skill's ``SKILL.md`` *and* of its frontmatter description; replay recomputes
both and refuses to grade when either moved. That is what makes a description
regression — the thing this harness exists to detect — turn the gate RED.

What replay does NOT do is authenticate the transcript. Anyone with write access
to the repo can hand-write a fixture and a matching meta sidecar; the hashes prove
the fixture is *current*, not that a model produced it. ``provenance`` records
which path wrote it and synthetic fixtures are refused unless
``--allow-synthetic-fixtures`` is passed explicitly, so the two can never be
confused silently. See README.md § "What replay does and does not guarantee".

``--ablate`` is BRO-2006 and is NOT implemented here. The seam is
``VISIBILITY_REGISTRY``: skill visibility is a parameter of workspace construction,
so the ablation arm is a one-line registration plus a flag, not a refactor.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol, Sequence

_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:  # allow direct execution AND package import
    sys.path.insert(0, str(_HERE.parent))

from skill_evals import ablation as ablation_mod  # noqa: E402
from skill_evals import checks as checks_mod  # noqa: E402
from skill_evals import jail as jail_mod  # noqa: E402
from skill_evals.transcript import Transcript, normalize_skill_name  # noqa: E402

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------

#: Repo layout: <repo>/scripts/skill_evals/runner.py -> <repo>/skills
DEFAULT_SKILLS_ROOT = _HERE.parent.parent / "skills"

DEFAULT_TRIALS = 3
DEFAULT_THRESHOLD = 0.80
DEFAULT_CASE_THRESHOLD = 0.60
DEFAULT_MODEL = "haiku"
DEFAULT_TIMEOUT_S = 300
#: The CLI version this harness's stream parsing was verified against.
EXPECTED_CLI_VERSION = "2.1.220"

PROMPT_SET_VERSION = 1
VALID_ORIGINS = {"golden", "negative", "real-trace"}

#: Bumped when the fixture meta sidecar gains a field replay *requires*. Fixtures
#: written before artifact binding (v1, no skill hash) are unusable by design.
FIXTURE_META_VERSION = 2

#: Who wrote a fixture. ``live-record`` is written only by ``LiveRunner._record``;
#: ``synthetic`` is hand-authored (harness self-tests) and must be opted into.
PROVENANCE_LIVE = "live-record"
PROVENANCE_SYNTHETIC = "synthetic"
VALID_PROVENANCE = {PROVENANCE_LIVE, PROVENANCE_SYNTHETIC}

#: Below this, a per-case result is an anecdote and is labelled as one.
MIN_DISTRIBUTION_TRIALS = 2

# Trial outcomes. Only PASS counts toward a pass rate; the rest are distinguished
# because they have different causes and different fixes.
PASS = "PASS"
FAIL = "FAIL"
RECOVERED = "RECOVERED"  # answered by reading SKILL.md off disk, never triggering
INVISIBLE = "INVISIBLE"  # skill absent from the run's roster -> result is vacuous
ERROR = "ERROR"  # CLI/fixture/harness failure -> no signal at all
#: The skill was present (or fired) in an arm that requires it ABSENT. The ablation
#: baseline is contaminated, which is a different thing from a zero-lift result and
#: must never be read as one — a contaminated baseline scores like the skill added
#: nothing, which is the exact recommendation-to-delete this measurement must not
#: manufacture (BRO-2006).
LEAKED = "LEAKED"
#: A negative case in the skill-absent arm. An uninstalled skill cannot over-trigger,
#: so the case asserts nothing at all — not a pass, not a failure.
NOT_COMPARABLE = "NOT_COMPARABLE"
NON_PASS_ERRORS = {INVISIBLE, ERROR, LEAKED, NOT_COMPARABLE}

EXIT_OK = 0
EXIT_BELOW_THRESHOLD = 1
EXIT_USAGE = 2
EXIT_FIXTURES = 3
#: The ablation baseline produced no usable evidence (BRO-2006). Distinct from a
#: threshold failure: nothing is wrong with the SKILL, the MEASUREMENT is void.
EXIT_ABLATION_UNUSABLE = 4

#: Skills the CLI ships built in. They are present in EVERY run, including the
#: ablation baseline, so a skill of ours that shares one of these names has no
#: definable absent arm — the "uninstalled" run still has a skill by that name. The
#: ablation refuses rather than reporting a lift of roughly zero, which would read
#: as absorption and recommend deleting ours.
BUILTIN_SKILL_NAMES = frozenset({
    "deep-research", "code-review", "simplify", "debug", "verify", "run", "loop",
    "review", "security-review", "init", "schedule", "artifact-design",
    "update-config", "keybindings-help", "fewer-permission-prompts", "dataviz",
})

#: Never copied into a case workspace: the answer key, the skill's own tests, VCS.
SKILL_COPY_EXCLUDE = (
    "evals",
    "tests",
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".DS_Store",
    "node_modules",
)


class PromptSetError(ValueError):
    """The prompt set is malformed or references checks that do not exist."""


class FixtureError(RuntimeError):
    """A replay fixture is missing, empty, unreadable, or bound to a different skill."""


class SkillArtifactError(RuntimeError):
    """The skill under test could not be fingerprinted — no SKILL.md, or no description."""


# ---------------------------------------------------------------------------
# artifact binding: the fixture is bound to the SKILL.md it was recorded against
# ---------------------------------------------------------------------------


def find_skill_md(skill_dir: Path) -> Path | None:
    p = Path(skill_dir) / "SKILL.md"
    return p if p.is_file() else None


try:  # optional: the reference YAML implementation, used whenever it is installed
    import yaml as _yaml
except ImportError:  # pragma: no cover - exercised by the no-PyYAML fallback path
    _yaml = None  # type: ignore[assignment]


def _frontmatter_block(text: str) -> str | None:
    """The raw YAML between the opening and closing ``---``, or ``None``."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        return None
    return "\n".join(lines[1:end])


def _normalize_description(value: str) -> str:
    """Collapse whitespace: a pure re-wrap must not read as a description change.

    The hash has to track *meaning*. Re-flowing a paragraph changes neither the
    words the model sees nor the trigger behaviour under test.
    """
    return " ".join(str(value).split())


#: A ``#`` that opens a comment in a YAML *plain* scalar: at the start, or preceded
#: by whitespace. Inside quotes or a block scalar it is literal, so the fallback
#: applies this only where YAML would.
_YAML_INLINE_COMMENT_RE = re.compile(r"(?:^|\s)#.*$")

_BLOCK_INDICATORS = (">", "|", ">-", "|-", ">+", "|+")


def _parse_frontmatter_description_fallback(text: str) -> str:
    """Hand parser for ``description:``, used only when PyYAML is not importable.

    Kept byte-compatible with PyYAML on every SKILL.md in this repo — see
    ``test_hand_parser_agrees_with_pyyaml_on_every_real_skill_md``. The three
    places it used to diverge, all of which move the description hash and so
    manufacture phantom staleness:

    * **quoted scalars** — ``description: "x"`` yielded ``"x"`` with the quotes;
    * **inline comments** — a plain scalar containing `` #`` (``AI Blue #0066FF``)
      kept the remainder, where YAML truncates it as a comment;
    * **escapes** — ``\\n`` inside a double-quoted scalar stayed literal.

    Block scalars (``>``/``|``) are exempt from the comment rule, because inside
    one a ``#`` is content.
    """
    block = _frontmatter_block(text)
    if block is None:
        return ""
    body = block.splitlines()
    for idx, line in enumerate(body):
        stripped = line.strip()
        if not stripped.lower().startswith("description:"):
            continue
        if line[: len(line) - len(line.lstrip())]:  # indented -> a nested key, not ours
            continue
        rest = stripped[len("description:") :].strip()
        tail = body[idx + 1 :]

        if rest[:1] in ("'", '"'):
            return _normalize_description(_read_quoted_scalar(rest, tail))

        if rest in _BLOCK_INDICATORS or not rest:
            collected: list[str] = []
            for cont in tail:
                if not cont.strip():
                    collected.append("")
                    continue
                if not cont[:1].isspace():  # dedented back to a sibling key
                    break
                collected.append(cont.strip())
            return _normalize_description(" ".join(collected))

        # plain multi-line scalar: every line is comment-eligible, and the first
        # comment ends the scalar (YAML cannot resume it on the next line).
        collected = [_YAML_INLINE_COMMENT_RE.sub("", rest)]
        if not _YAML_INLINE_COMMENT_RE.search(rest):
            for cont in tail:
                if not cont.strip():
                    collected.append("")
                    continue
                if not cont[:1].isspace():
                    break
                piece = cont.strip()
                collected.append(_YAML_INLINE_COMMENT_RE.sub("", piece))
                if _YAML_INLINE_COMMENT_RE.search(piece):
                    break
        return _normalize_description(" ".join(collected))
    return ""


def _read_quoted_scalar(first: str, tail: Sequence[str]) -> str:
    """Read a single- or double-quoted YAML scalar, which may span lines."""
    quote = first[0]
    buf = first[1:]
    closed, value = _close_quote(buf, quote)
    if closed:
        return value
    for line in tail:
        stripped = line.strip()
        if not stripped:
            continue
        buf = f"{buf} {stripped}"
        closed, value = _close_quote(buf, quote)
        if closed:
            return value
    return _unescape(buf, quote)


def _close_quote(buf: str, quote: str) -> tuple[bool, str]:
    """``(closed, value)`` — scan *buf* for the quote that terminates the scalar."""
    out: list[str] = []
    i = 0
    while i < len(buf):
        ch = buf[i]
        if quote == '"' and ch == "\\" and i + 1 < len(buf):
            out.append(buf[i : i + 2])
            i += 2
            continue
        if ch == quote:
            if quote == "'" and buf[i + 1 : i + 2] == "'":  # YAML's escaped ''
                out.append("'")
                i += 2
                continue
            return True, _unescape("".join(out), quote)
        out.append(ch)
        i += 1
    return False, _unescape("".join(out), quote)


def _unescape(value: str, quote: str) -> str:
    if quote != '"':
        return value
    try:
        return json.loads(f'"{value}"')
    except ValueError:
        return value.replace('\\"', '"').replace("\\\\", "\\")


def parse_frontmatter_description(text: str) -> str:
    """The skill's frontmatter ``description``, as the real loader sees it.

    PyYAML is the reference implementation and is used whenever it imports; the
    hand parser below is the fallback for environments without it. They are held
    byte-identical on every SKILL.md in the repo by a differential test, because
    this string's hash is what binds a replay fixture to its artifact: a parser
    that disagrees with the real loader can miss a genuine description change AND
    flag a phantom one (an edit to an inline YAML comment, say).
    """
    if _yaml is not None:
        block = _frontmatter_block(text)
        if block is None:
            return ""
        try:
            data = _yaml.safe_load(block)
        except Exception:  # malformed frontmatter -> let the hand parser try
            return _parse_frontmatter_description_fallback(text)
        if isinstance(data, dict) and isinstance(data.get("description"), str):
            return _normalize_description(data["description"])
        return ""
    return _parse_frontmatter_description_fallback(text)


def strip_frontmatter_description(text: str) -> str:
    """Return *text* with the top-level ``description`` key removed (BRO-2028).

    The body is left byte-identical; only the frontmatter changes. Key detection
    mirrors ``_parse_frontmatter_description_fallback`` exactly — top-level (not
    indented) ``description:`` — and the scalar's continuation lines (blank, or
    indented under the key) go with it.

    Raises ``SkillArtifactError`` when there is no frontmatter, no description to
    remove, or when the result *still* parses a non-empty description.

    That last check is the load-bearing one, and it is why this function verifies
    itself rather than trusting its own line arithmetic. The ``bare`` arm exists
    to answer "does a skill still trigger on its name alone?". A strip that
    silently no-ops makes the bare arm byte-identical to the present arm, both
    arms score the same, and the experiment reports **"the name alone is
    sufficient"** having never removed a description — the exact false conclusion
    it was built to rule out. Per this arc's own lesson, the proof uses the SAME
    predicate the harness grades with (``parse_frontmatter_description``), not a
    second opinion that could agree for the wrong reason.
    """
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise SkillArtifactError(
            "no YAML frontmatter — cannot build a bare arm from this SKILL.md"
        )
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        raise SkillArtifactError("unterminated frontmatter — refusing to guess its extent")

    kept: list[str] = []
    i, dropped = 1, False
    while i < end:
        line = lines[i]
        indent = line[: len(line) - len(line.lstrip())]
        if indent or not line.strip().lower().startswith("description:"):
            kept.append(line)
            i += 1
            continue
        dropped = True
        i += 1
        # The scalar runs until a line dedents back to a sibling key. Blank lines
        # inside that run belong to it (block scalars may contain them).
        while i < end:
            cont = lines[i]
            if cont.strip() and not cont[:1].isspace():
                break
            i += 1

    if not dropped:
        raise SkillArtifactError(
            "no top-level 'description:' in frontmatter — a bare arm would be "
            "identical to the present arm, which measures nothing"
        )

    result = lines[0] + "".join(kept) + "".join(lines[end:])
    residue = parse_frontmatter_description(result)
    if residue.strip():
        raise SkillArtifactError(
            f"description survived stripping ({residue[:60]!r}…) — the bare arm "
            "would silently equal the present arm"
        )
    return result


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def skill_fingerprint(skill_dir: Path) -> dict[str, str]:
    """Hash the artifact under test: the whole SKILL.md and its description alone.

    Two hashes, because they answer different questions when a fixture goes stale.
    ``description_sha256`` moving means the thing the eval measures changed — the
    regression this harness exists to catch. ``skill_md_sha256`` moving means the
    recorded run no longer corresponds to the skill on disk at all, which
    invalidates the outcome checks even when the description is untouched.
    """
    path = find_skill_md(skill_dir)
    if path is None:
        raise SkillArtifactError(
            f"no SKILL.md under {skill_dir} — the eval cannot be bound to an artifact. "
            "Pass --skill-dir at the directory that contains SKILL.md."
        )
    text = path.read_text(encoding="utf-8")
    description = parse_frontmatter_description(text)
    if not description:
        raise SkillArtifactError(
            f"{path} has no frontmatter 'description:' — the description IS what this "
            "harness measures; a skill without one cannot be evaluated."
        )
    return {
        "skill_md_path": str(path),
        "skill_md_sha256": _sha256(text),
        "description_sha256": _sha256(description),
    }


# ---------------------------------------------------------------------------
# prompt set
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Case:
    id: str
    prompt: str
    should_trigger: bool
    expected_checks: list[str] = field(default_factory=list)
    origin: str = "golden"
    rationale: str = ""
    #: URLs/ids that resolve to the SAME artifact the prompt points at, for the one
    #: shape artifact scoping cannot see: an artifact behind an indirection that
    #: shares no distinctive token with the pasted link (see
    #: ``checks._case_artifact_tokens``). Additive only — it can never make a
    #: wrong-artifact fetch pass.
    artifact_aliases: list[str] = field(default_factory=list)

    @property
    def prompt_sha256(self) -> str:
        return hashlib.sha256(self.prompt.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PromptSet:
    skill: str
    version: int
    cases: list[Case]
    notes: str = ""
    path: Path | None = None

    @property
    def positives(self) -> list[Case]:
        return [c for c in self.cases if c.should_trigger]

    @property
    def negatives(self) -> list[Case]:
        return [c for c in self.cases if not c.should_trigger]


def validate_prompt_set(data: Any, registry: dict[str, Any] | None = None) -> tuple[list[str], list[str]]:
    """Return ``(errors, warnings)`` for a raw prompt-set document.

    Errors block the run. Warnings are printed but do not: they flag prompt sets
    that will still execute yet measure something weaker than intended (a prompt
    naming the skill literally measures name-matching, not description-matching).
    """
    registry = checks_mod.CHECK_REGISTRY if registry is None else registry
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(data, dict):
        return ([f"prompt set must be a JSON object, got {type(data).__name__}"], warnings)

    skill = data.get("skill")
    if not isinstance(skill, str) or not skill.strip():
        errors.append("'skill' must be a non-empty string")
        skill = ""

    version = data.get("version")
    if version != PROMPT_SET_VERSION:
        errors.append(f"'version' must be {PROMPT_SET_VERSION}, got {version!r}")

    raw_cases = data.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        errors.append("'cases' must be a non-empty list")
        return (errors, warnings)

    seen: set[str] = set()
    for idx, raw in enumerate(raw_cases):
        where = f"cases[{idx}]"
        if not isinstance(raw, dict):
            errors.append(f"{where}: must be an object")
            continue
        cid = raw.get("id")
        if not isinstance(cid, str) or not cid.strip():
            errors.append(f"{where}: 'id' must be a non-empty string")
        elif cid in seen:
            errors.append(f"{where}: duplicate case id {cid!r}")
        else:
            seen.add(cid)
            where = f"case {cid!r}"

        prompt = raw.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            errors.append(f"{where}: 'prompt' must be a non-empty string")
            prompt = ""

        if not isinstance(raw.get("should_trigger"), bool):
            errors.append(f"{where}: 'should_trigger' must be a boolean")

        expected = raw.get("expected_checks", [])
        if not isinstance(expected, list) or not all(isinstance(c, str) for c in expected):
            errors.append(f"{where}: 'expected_checks' must be a list of strings")
        elif not expected:
            # THE hole the eval-set review proved: emptying a case's expected_checks
            # deleted everything the case asserted and the set still validated clean
            # ("prompt set OK", exit 0). On a negative that is the difference between
            # "the skill stayed quiet" and "the skill stayed quiet AND the run still
            # answered the user"; on a positive it reduces the case to "it fired".
            # An ERROR, not a warning: a warning is the shape of hole this was.
            errors.append(
                f"{where}: 'expected_checks' is empty — the case then asserts nothing "
                "beyond trigger/no-trigger, which is the one edit that guts a case "
                "while leaving the prompt set valid"
            )
        else:
            for missing in [c for c in expected if c not in registry]:
                errors.append(f"{where}: unknown check id {missing!r} (not in CHECK_REGISTRY)")

        aliases = raw.get("artifact_aliases", [])
        if not isinstance(aliases, list) or not all(isinstance(a, str) for a in aliases):
            errors.append(f"{where}: 'artifact_aliases' must be a list of strings")
        else:
            # An alias that contributes no distinctive token is noise wearing the
            # shape of evidence: it looks like the case scoped harder and does
            # nothing. THAT an alias resolves to the same artifact is reviewable, not
            # machine-checkable — the verification log is where it gets checked.
            for alias in aliases:
                if not alias.strip():
                    errors.append(f"{where}: 'artifact_aliases' contains an empty string")
                elif not checks_mod._artifact_tokens(alias):
                    errors.append(
                        f"{where}: artifact alias {alias!r} yields no distinctive token, "
                        "so it scopes nothing"
                    )

        # BRO-2006: in the ablation baseline the trigger-dependent checks are
        # skipped, so a positive case made ONLY of them has nothing runnable left —
        # it can never pass the baseline, which biases the lift upward and makes a
        # load-bearing verdict cheaper to obtain. Zero cases across the seven
        # committed sets are like this today; this keeps it that way.
        if (
            isinstance(expected, list)
            and expected
            and raw.get("should_trigger") is True
            and all(c in checks_mod.TRIGGER_DEPENDENT_CHECKS for c in expected)
        ):
            warnings.append(
                f"{where}: every expected_check is trigger-dependent, so this case "
                "asserts nothing in the ablation baseline and would bias the lift upward"
            )

        origin = raw.get("origin", "golden")
        if origin not in VALID_ORIGINS:
            warnings.append(f"{where}: unrecognised origin {origin!r} (expected one of {sorted(VALID_ORIGINS)})")

        if skill and prompt and skill.lower() in prompt.lower():
            warnings.append(
                f"{where}: prompt contains the literal skill name {skill!r} — "
                "this measures name-matching, not description-matching"
            )

    # A suite with no positives is the cheapest way to green this gate: a skill
    # whose description is so broken it can never fire scores a perfect negative
    # sweep. That is an ERROR, not a warning — the asymmetry with the negative-case
    # warning below is deliberate. A positives-only suite still measures something
    # (it just cannot see over-triggering); a negatives-only suite measures nothing
    # about whether the skill works at all.
    if not any(isinstance(c, dict) and c.get("should_trigger") is True for c in raw_cases):
        errors.append(
            "prompt set has no positive cases — a suite that never demonstrates the skill "
            "firing cannot fail when its description breaks"
        )

    if not any(isinstance(c, dict) and c.get("should_trigger") is False for c in raw_cases):
        warnings.append(
            "prompt set has no negative cases — a positives-only suite cannot see over-triggering"
        )

    return (errors, warnings)


def parse_prompt_set(data: Any, path: Path | None = None) -> PromptSet:
    """Validate then build a :class:`PromptSet`. Raises :class:`PromptSetError`."""
    errors, _warnings = validate_prompt_set(data)
    if errors:
        raise PromptSetError("; ".join(errors))
    cases = [
        Case(
            id=c["id"],
            prompt=c["prompt"],
            should_trigger=bool(c["should_trigger"]),
            expected_checks=list(c.get("expected_checks", [])),
            origin=str(c.get("origin", "golden")),
            rationale=str(c.get("rationale", "")),
            artifact_aliases=list(c.get("artifact_aliases", [])),
        )
        for c in data["cases"]
    ]
    return PromptSet(
        skill=data["skill"],
        version=int(data["version"]),
        cases=cases,
        notes=str(data.get("notes", "")),
        path=path,
    )


def load_prompt_set(path: Path) -> PromptSet:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PromptSetError(f"prompt set not found: {path}") from exc
    except ValueError as exc:
        raise PromptSetError(f"prompt set is not valid JSON ({path}): {exc}") from exc
    return parse_prompt_set(data, path=Path(path))


def find_skill_dir(skills_root: Path, skill: str) -> Path:
    """Locate ``<skills_root>/<bucket>/<skill>/`` across the bucket layout."""
    root = Path(skills_root)
    direct = root / skill
    if (direct / "SKILL.md").is_file():
        return direct
    matches = sorted(p.parent for p in root.glob(f"*/{skill}/SKILL.md"))
    if not matches:
        raise PromptSetError(f"no skill named {skill!r} under {root}")
    if len(matches) > 1:
        raise PromptSetError(f"skill {skill!r} is ambiguous: {[str(m) for m in matches]}")
    return matches[0]


def default_prompts_path(skill_dir: Path) -> Path:
    return Path(skill_dir) / "evals" / "prompts.json"


# ---------------------------------------------------------------------------
# workspace isolation + skill visibility (the --ablate seam)
# ---------------------------------------------------------------------------


def _materialize_present(workspace: Path, skill_dir: Path, skill_name: str) -> None:
    """Install the skill under test as a project-scope skill inside the case cwd."""
    dest = Path(workspace) / ".claude" / "skills" / skill_name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        skill_dir,
        dest,
        ignore=shutil.ignore_patterns(*SKILL_COPY_EXCLUDE),
        dirs_exist_ok=True,
    )


@dataclass(frozen=True)
class Visibility:
    """How the skill under test is made (in)visible to a case run.

    ``expects_visible`` drives the anti-vacuity roster precheck: when the strategy
    claims the skill should be installed but the run's ``init`` event does not list
    it, the trial is scored INVISIBLE rather than counted — a negative case that
    "passed" because the skill was never loaded is not evidence of anything.
    """

    id: str
    expects_visible: bool
    materialize: Callable[[Path, Path, str], None]


#: SEAM (BRO-2006 ``--ablate``): register
#: ``Visibility("absent", False, lambda *_: None)`` here and expose it as a flag.
#: The runner already threads visibility through workspace construction and
#: grading, so the ablation arm needs no structural change.
def _materialize_absent(workspace: Path, skill_dir: Path, skill_name: str) -> None:
    """Install nothing. The ablation baseline (BRO-2006).

    Note what this does NOT remove: the base model's built-in skills are present in
    every run regardless, so a lift measured here is the skill's MARGINAL value over
    a model that still has those — not its value over a bare model.
    """


def _materialize_bare(workspace: Path, skill_dir: Path, skill_name: str) -> None:
    """Install the skill, then strip the description from the INSTALLED copy (BRO-2028).

    Reproduces the rationed-roster condition BRO-2014 measured in the wild: ~75%
    of skills reach the model as a bare name because the listing is capped. The
    skill IS in the roster; its description is not.

    Two properties make this arm faithful rather than merely different:

    * **The body stays byte-identical on disk.** Rationing truncates the *listing*,
      not the file. Deleting the body would collapse RECOVERED — "answered by
      reading SKILL.md without ever triggering" — into FAIL, and that distinction
      is the whole reason this experiment can attribute a result to a mechanism.
    * **The SOURCE skill is never touched.** ``skill_fingerprint`` reads
      ``skill_dir``, so replay binding still holds and this arm does not trip the
      "description moved" staleness guard.

    ``expects_visible=True`` in the registry entry is deliberate: a bare skill is
    still ON the roster, so the anti-vacuity precheck keeps applying. If the CLI
    turns out to drop description-less skills from the roster entirely, every
    trial scores INVISIBLE rather than FAIL — which is a finding about the loader,
    not a zero-lift result, and must not be read as one.
    """
    _materialize_present(workspace, skill_dir, skill_name)
    dest = Path(workspace) / ".claude" / "skills" / skill_name
    path = find_skill_md(dest)
    if path is None:  # pragma: no cover - _materialize_present just wrote it
        raise SkillArtifactError(f"no SKILL.md at {dest} after materializing the bare arm")
    path.write_text(
        strip_frontmatter_description(path.read_text(encoding="utf-8")), encoding="utf-8"
    )


VISIBILITY_REGISTRY: dict[str, Visibility] = {
    "present": Visibility("present", True, _materialize_present),
    "absent": Visibility("absent", False, _materialize_absent),
    "bare": Visibility("bare", True, _materialize_bare),
}

#: Arms usable as an ablation baseline. ``absent`` measures the skill's marginal
#: value over a model without it; ``bare`` measures the *description's* marginal
#: value over the name alone. They answer different questions and the verdict text
#: must not imply otherwise.
ABLATION_BASELINES = ("absent", "bare")


def _baseline_cases(prompt_set: "PromptSet", baseline: str) -> list["Case"]:
    """Which cases the baseline arm re-runs, and why the two baselines differ.

    ``absent`` runs POSITIVES ONLY: an uninstalled skill cannot over-trigger, so a
    negative case there asserts nothing and re-running it is pure spend (BRO-2006).

    ``bare`` runs EVERYTHING. That optimisation does not transfer, and assuming it
    did would silently gut the experiment: a bare skill IS installed, so it can
    absolutely over-trigger on its name alone — ``blog-post`` firing on "summarise
    this CSV" is exactly the failure a name-only roster invites. Dropping the
    negatives would leave the arc unable to distinguish "the name is a sufficient
    trigger" from "the name is an indiscriminate one", which are opposite verdicts
    on the same measurement (BRO-2028).
    """
    return list(prompt_set.cases if baseline == "bare" else prompt_set.positives)


def build_workspace(root: Path, skill_dir: Path, skill_name: str, visibility: Visibility) -> Path:
    """Create a fresh, non-git case cwd and apply the visibility strategy."""
    ws = Path(root)
    ws.mkdir(parents=True, exist_ok=True)
    visibility.materialize(ws, Path(skill_dir), skill_name)
    return ws


# ---------------------------------------------------------------------------
# Runner protocol + implementations
# ---------------------------------------------------------------------------


class Runner(Protocol):
    """The single seam between grading and the outside world."""

    mode: str

    def run(self, prompt: str, workspace: Path, *, case_id: str, trial: int) -> Transcript: ...

    def trials_for(self, case_id: str, requested: int) -> int: ...


@dataclass
class LiveRunner:
    """Shells out to the real agent CLI. The default, and the only honest path.

    Invocation verified live against CLI 2.1.220. ``stdin`` must be ``/dev/null``
    or every run eats a 3s stall; ``--output-format stream-json`` requires
    ``--verbose`` and is mandatory (plain ``json`` carries no tool data at all).
    """

    cli: str
    model: str = DEFAULT_MODEL
    timeout_s: int = DEFAULT_TIMEOUT_S
    record_dir: Path | None = None
    disallow_recovery_tools: bool = False
    extra_args: Sequence[str] = ()
    #: BRO-2018. When true (the default), the child gets a deny-by-default
    #: environment with ``HOME`` inside the case workspace, so a skill script that
    #: resolves its state from ``$HOME`` — p9's config dir, kg's whole workspace —
    #: writes into the temp dir instead of the user's real one. Turning it OFF is
    #: what the escape mutation-proof does; there is no other reason to.
    env_jail: bool = True
    #: Written into every fixture so replay can detect a stale recording.
    skill: str = ""
    cli_version: str = ""
    fingerprint: dict[str, str] = field(default_factory=dict)
    mode: str = field(default="live", init=False)

    def build_argv(self, prompt: str) -> list[str]:
        argv = [
            self.cli,
            "-p",
            prompt,
            "--output-format",
            "stream-json",
            "--verbose",
            "--model",
            self.model,
            "--setting-sources",
            "project",
            "--permission-mode",
            "bypassPermissions",
            "--no-session-persistence",
        ]
        if self.disallow_recovery_tools:
            argv += ["--disallowedTools", "Read Grep Glob Bash"]
        argv += list(self.extra_args)
        return argv

    def trials_for(self, case_id: str, requested: int) -> int:
        return requested

    def run(self, prompt: str, workspace: Path, *, case_id: str, trial: int) -> Transcript:
        argv = self.build_argv(prompt)
        # The jail is built HERE, at the one place in the harness that spawns a
        # process, rather than in build_workspace: replay grades recorded bytes and
        # can leak nothing, so it should not be paying for symlinks it never uses.
        env = jail_mod.build_case_env(workspace) if self.env_jail else None
        if self.env_jail:
            jail_mod.prepare_jail(workspace)
        started = time.monotonic()
        try:
            proc = subprocess.run(
                argv,
                cwd=str(workspace),
                env=env,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
            )
            stdout, stderr, code = proc.stdout, proc.stderr, proc.returncode
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout if isinstance(exc.stdout, str) else ""
            stderr = f"TIMEOUT after {self.timeout_s}s"
            code = 124
        wall_ms = int((time.monotonic() - started) * 1000)
        transcript = Transcript.from_ndjson(
            stdout, exit_code=code, stderr=stderr, source=" ".join(argv[:1]), wall_ms=wall_ms
        )
        if self.record_dir is not None:
            self._record(case_id, trial, prompt, stdout, transcript)
        return transcript

    def _record(self, case_id: str, trial: int, prompt: str, stdout: str, t: Transcript) -> None:
        """Write the transcript plus the provenance replay needs to detect staleness.

        The skill hashes are the load-bearing fields: without them a replay is
        decoupled from the artifact under test and a description regression is
        invisible to the gate.
        """
        if not (self.fingerprint.get("skill_md_sha256") and
                self.fingerprint.get("description_sha256")):
            raise SkillArtifactError(
                "refusing to record an UNBOUND fixture: LiveRunner has no skill "
                "fingerprint, so the transcript could never be checked against the "
                "SKILL.md it was recorded from. Pass fingerprint=skill_fingerprint(dir)."
            )
        case_dir = Path(self.record_dir) / "cases" / case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        (case_dir / f"trial-{trial:02d}.jsonl").write_text(stdout, encoding="utf-8")
        meta = {
            "meta_version": FIXTURE_META_VERSION,
            "provenance": PROVENANCE_LIVE,
            "skill": self.skill,
            "case_id": case_id,
            "trial": trial,
            "exit_code": t.exit_code,
            "stderr": t.stderr[-4000:],
            "wall_ms": t.wall_ms,
            "model": self.model,
            "cli_version": self.cli_version,
            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "skill_md_sha256": self.fingerprint.get("skill_md_sha256", ""),
            "description_sha256": self.fingerprint.get("description_sha256", ""),
            "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        (case_dir / f"trial-{trial:02d}.meta.json").write_text(
            json.dumps(meta, indent=2), encoding="utf-8"
        )


@dataclass
class ReplayRunner:
    """Re-grades transcripts recorded by ``LiveRunner --record``. CI's path.

    Refuses to fabricate signal. A fixture is graded only when it is:

    * **present and parseable** — missing, empty and garbage fixtures raise
      :class:`FixtureError`, which the grader turns into an ERROR trial and the
      reporter turns into a non-zero exit regardless of the pass rate;
    * **bound to this artifact** — the meta sidecar's ``skill_md_sha256`` and
      ``description_sha256`` must equal the current SKILL.md's. A fixture recorded
      before a description edit is stale, and grading it green would hide exactly
      the regression the harness exists to detect;
    * **bound to this prompt** — ``prompt_sha256`` must match;
    * **declared** — a fixture with no meta sidecar, or one written by a
      non-``live-record`` path, is refused unless synthetic fixtures are opted in.

    The binding proves the fixture is *current*. It does not prove a model
    produced it: anyone who can write the fixture can write the sidecar. Detection
    of staleness is the guarantee; authentication is not (README § guarantees).
    """

    root: Path
    #: The current artifact's hashes, from :func:`skill_fingerprint`. REQUIRED —
    #: there is deliberately no default, so a replay runner that is not bound to an
    #: artifact cannot be constructed at all, from the CLI or from a test.
    fingerprint: dict[str, str]
    strict_prompt_hash: bool = False
    allow_synthetic: bool = False
    expected_skill: str = ""
    expected_model: str = ""
    expected_cli_version: str = ""
    mode: str = field(default="replay", init=False)
    #: Fixtures recorded against a DIFFERENT PROMPT than the set now carries — a
    #: subset of :attr:`integrity_failures` with its own remedy ("the prompt set
    #: moved, re-record"), so :func:`main` reports it as its own line and puts the
    #: list in the JSON report. It was write-only until BRO-2005 round 3.
    stale_fixtures: list[str] = field(default_factory=list, init=False)
    provenance_notes: list[str] = field(default_factory=list, init=False)
    #: Every FixtureError this runner raised. A fixture-integrity failure is NOT a
    #: scoring error: `--allow-errors` may forgive a CLI hiccup, but it must never
    #: forgive "the fixture does not describe the skill on disk". Callers hoist
    #: this into the fixtures-unusable gate, which outranks every threshold.
    integrity_failures: list[str] = field(default_factory=list, init=False)

    def case_dir(self, case_id: str) -> Path:
        return Path(self.root) / "cases" / case_id

    def available(self, case_id: str) -> int:
        d = self.case_dir(case_id)
        if not d.is_dir():
            return 0
        return len(sorted(d.glob("trial-*.jsonl")))

    def trials_for(self, case_id: str, requested: int) -> int:
        """Always the requested count — a shortfall is an ERROR, never a clamp.

        Clamping to whatever happened to be on disk is how ``--trials 3`` against
        one-trial-per-case fixtures reported a green "distribution" of anecdotes.
        Missing trials now surface as FixtureError -> ERROR trials, and
        :func:`main`'s fixture guard catches the shortfall before any of it runs.
        """
        return requested

    def _check_binding(self, meta: dict[str, Any], case_id: str, trial: int, path: Path) -> None:
        where = f"{case_id} trial {trial}"
        provenance = str(meta.get("provenance", ""))
        if provenance not in VALID_PROVENANCE:
            raise FixtureError(
                f"{where}: fixture meta declares provenance {provenance!r}; expected one of "
                f"{sorted(VALID_PROVENANCE)} ({path.name})"
            )
        if provenance == PROVENANCE_SYNTHETIC and not self.allow_synthetic:
            raise FixtureError(
                f"{where}: fixture is SYNTHETIC (hand-authored, no model produced it). "
                "Pass --allow-synthetic-fixtures to grade harness self-tests; never pass it "
                "when the number is meant to describe a real skill."
            )
        recorded_skill = str(meta.get("skill", ""))
        if self.expected_skill and recorded_skill and (
            normalize_skill_name(recorded_skill) != normalize_skill_name(self.expected_skill)
        ):
            raise FixtureError(
                f"{where}: fixture was recorded for skill {recorded_skill!r}, not "
                f"{self.expected_skill!r} — a fixture directory holding another skill's "
                "transcripts grades neither one."
            )
        if int(meta.get("meta_version", 0) or 0) < FIXTURE_META_VERSION:
            raise FixtureError(
                f"{where}: fixture meta is version {meta.get('meta_version')!r}, needs "
                f">= {FIXTURE_META_VERSION} (pre-dates artifact binding). Re-record it."
            )
        for key, label in (
            ("description_sha256", "the skill's DESCRIPTION"),
            ("skill_md_sha256", "the skill's SKILL.md"),
        ):
            recorded = str(meta.get(key, ""))
            current = self.fingerprint.get(key, "")
            if not recorded:
                raise FixtureError(
                    f"{where}: fixture meta carries no {key} — it is not bound to any "
                    "artifact, so a description regression would be invisible. Re-record it."
                )
            if recorded != current:
                raise FixtureError(
                    f"{where}: STALE FIXTURE — {label} changed since this transcript was "
                    f"recorded ({key} {recorded[:12]} != {current[:12]}). The recorded run "
                    "does not describe the skill on disk; re-record before trusting it."
                )

    def _note_drift(self, meta: dict[str, Any], case_id: str, trial: int) -> None:
        """Model / CLI drift: detected and reported, fatal only under --strict-fixtures."""
        for key, expected, label in (
            ("model", self.expected_model, "model"),
            ("cli_version", self.expected_cli_version, "CLI version"),
        ):
            recorded = str(meta.get(key, ""))
            if expected and recorded and recorded != expected:
                msg = (
                    f"{case_id} trial {trial}: recorded on {label} {recorded!r}, "
                    f"current expectation is {expected!r}"
                )
                self.provenance_notes.append(msg)
                if self.strict_prompt_hash:
                    raise FixtureError(msg)

    def run(self, prompt: str, workspace: Path, *, case_id: str, trial: int) -> Transcript:
        """Load one recorded trial, refusing anything the binding cannot vouch for.

        Every raise is recorded in :attr:`integrity_failures` before it propagates,
        so no scoring flag downstream can quietly absorb it.
        """
        try:
            return self._run(prompt, case_id=case_id, trial=trial)
        except FixtureError as exc:
            self.integrity_failures.append(str(exc))
            raise

    def _run(self, prompt: str, *, case_id: str, trial: int) -> Transcript:
        path = self.case_dir(case_id) / f"trial-{trial:02d}.jsonl"
        if not path.is_file():
            raise FixtureError(f"missing replay fixture: {path}")
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            raise FixtureError(f"empty replay fixture: {path}")

        meta_path = path.with_suffix(".meta.json")
        if not meta_path.is_file():
            raise FixtureError(
                f"{case_id} trial {trial}: no meta sidecar at {meta_path.name} — an "
                "unbound fixture cannot be told apart from a stale or fabricated one. "
                "Re-record with --record."
            )
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise FixtureError(f"{case_id} trial {trial}: unreadable meta sidecar: {exc}") from exc
        if not isinstance(meta, dict):
            raise FixtureError(f"{case_id} trial {trial}: meta sidecar is not a JSON object")

        self._check_binding(meta, case_id, trial, path)
        self._note_drift(meta, case_id, trial)

        recorded_hash = str(meta.get("prompt_sha256", ""))
        current_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        if not recorded_hash:
            raise FixtureError(
                f"{case_id} trial {trial}: fixture meta carries no prompt_sha256"
            )
        if recorded_hash != current_hash:
            msg = (
                f"{case_id} trial {trial}: STALE FIXTURE — recorded against a different "
                "prompt than the prompt set now carries"
            )
            self.stale_fixtures.append(msg)
            raise FixtureError(msg)

        transcript = Transcript.from_ndjson(
            text,
            exit_code=int(meta.get("exit_code", 0) or 0),
            stderr=str(meta.get("stderr", "")),
            source=str(path),
            wall_ms=meta.get("wall_ms"),
        )
        if not transcript.events:
            raise FixtureError(f"replay fixture has no parseable events: {path}")
        return transcript


# ---------------------------------------------------------------------------
# grading
# ---------------------------------------------------------------------------


@dataclass
class TrialResult:
    case_id: str
    trial: int
    outcome: str
    detail: str = ""
    triggered: bool = False
    checks: list[dict[str, Any]] = field(default_factory=list)
    cost_usd: float | None = None
    duration_ms: int | None = None
    num_turns: int | None = None
    source: str = ""

    @property
    def passed(self) -> bool:
        return self.outcome == PASS

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "trial": self.trial,
            "outcome": self.outcome,
            "detail": self.detail,
            "triggered": self.triggered,
            "checks": self.checks,
            "cost_usd": self.cost_usd,
            "duration_ms": self.duration_ms,
            "num_turns": self.num_turns,
            "source": self.source,
        }


def grade_trial(
    case: Case,
    transcript: Transcript,
    skill: str,
    *,
    trial: int = 1,
    expect_visible: bool = True,
    workspace: str | None = None,
) -> TrialResult:
    """Score one transcript. Outcomes, not paths — the turn the skill fired on is
    irrelevant; whether it fired at all, and what the run produced, are not."""

    def out(outcome: str, detail: str, *, checks: list[dict[str, Any]] | None = None,
            triggered: bool = False) -> TrialResult:
        return TrialResult(
            case_id=case.id,
            trial=trial,
            outcome=outcome,
            detail=detail,
            triggered=triggered,
            checks=checks or [],
            cost_usd=transcript.cost_usd,
            duration_ms=transcript.duration_ms,
            num_turns=transcript.num_turns,
            source=transcript.source,
        )

    if not transcript.events:
        return out(ERROR, f"empty transcript (exit {transcript.exit_code}) {transcript.stderr[:200]}".strip())

    roster = transcript.skill_roster()
    if roster is None:
        return out(
            ERROR,
            "init event carries no 'skills' array — CLI stream shape changed; "
            "detection cannot be trusted",
        )

    if transcript.is_error:
        return out(ERROR, f"cli reported failure: {transcript.error_reason[:200]}")

    # Anti-vacuity, in BOTH directions (BRO-2006). ``expect_visible`` used to be a
    # skip switch: when False, nothing was asserted about visibility at all, so a
    # skill that leaked into the ablation baseline scored as an ordinary result and
    # the lift came out at zero — indistinguishable from "the model absorbed it",
    # which is a recommendation to delete a load-bearing skill.
    #
    # The asymmetry is deliberate. INVISIBLE stays roster-only (conservative for the
    # present arm); LEAKED is roster OR triggered (conservative for the absent arm).
    # Both err toward refusing to score rather than toward scoring wrongly.
    available = normalize_skill_name(skill) in {normalize_skill_name(s) for s in roster}
    if expect_visible and not available:
        return out(
            INVISIBLE,
            f"{skill!r} absent from the run's {len(roster)}-skill roster — "
            "visibility bug, not a description result",
        )
    if not expect_visible and (available or transcript.triggered(skill)):
        return out(
            LEAKED,
            f"{skill!r} was in the roster (or fired) in an arm that requires it "
            "ABSENT — the baseline is contaminated, not a zero-lift result",
        )

    triggered = transcript.triggered(skill)
    ctx = checks_mod.CheckContext(
        case={
            "id": case.id,
            "prompt": case.prompt,
            "should_trigger": case.should_trigger,
            "artifact_aliases": list(case.artifact_aliases),
        },
        skill=skill,
        transcript=transcript,
        workspace=workspace,
    )
    runnable, skipped = checks_mod.partition_for_arm(
        case.expected_checks, skill_present=expect_visible
    )
    check_results = checks_mod.run_checks(runnable, ctx)
    check_dicts = [c.to_dict() for c in check_results]
    check_dicts += [checks_mod.skipped_result(c) for c in skipped]
    failed = [c.check_id for c in check_results if not c.passed]

    # -- the ablation baseline (BRO-2006) ------------------------------------
    # The skill is not installed, so "did it fire" is not a question this arm can
    # ask. Grade the OUTCOME only, and say so in the detail rather than letting a
    # reader assume the two arms were scored the same way.
    if not expect_visible:
        if not case.should_trigger:
            return out(
                NOT_COMPARABLE,
                "negative case in the skill-absent arm: an uninstalled skill cannot "
                "over-trigger, so this case asserts nothing",
                checks=check_dicts,
            )
        if failed:
            return out(
                FAIL,
                f"baseline (skill absent): outcome-only grading, checks failed: "
                f"{', '.join(failed)}",
                checks=check_dicts,
            )
        return out(
            PASS, "baseline (skill absent): outcome-only grading, all runnable checks passed",
            checks=check_dicts,
        )

    if case.should_trigger:
        if not triggered:
            if transcript.read_skill_content(skill, workspace):
                return out(
                    RECOVERED,
                    "answered by reading SKILL.md off disk without invoking the skill",
                    checks=check_dicts,
                )
            return out(FAIL, "skill did not trigger", checks=check_dicts)
        if failed:
            return out(
                FAIL, f"triggered but checks failed: {', '.join(failed)}",
                checks=check_dicts, triggered=True,
            )
        return out(PASS, "triggered; all expected checks passed", checks=check_dicts, triggered=True)

    # negative case: the skill must stay quiet
    if triggered:
        return out(FAIL, "over-triggered on a near-miss prompt", checks=check_dicts, triggered=True)
    if failed:
        return out(FAIL, f"did not trigger (correct) but checks failed: {', '.join(failed)}",
                   checks=check_dicts)
    return out(PASS, "correctly did not trigger", checks=check_dicts)


# ---------------------------------------------------------------------------
# aggregation
# ---------------------------------------------------------------------------


@dataclass
class CaseResult:
    case_id: str
    should_trigger: bool
    origin: str
    trials: list[TrialResult] = field(default_factory=list)

    @property
    def trial_count(self) -> int:
        return len(self.trials)

    @property
    def pass_count(self) -> int:
        return sum(1 for t in self.trials if t.passed)

    @property
    def pass_rate(self) -> float:
        # Zero trials is never a pass: a case that never ran has no evidence.
        return (self.pass_count / self.trial_count) if self.trial_count else 0.0

    @property
    def outcome_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for t in self.trials:
            counts[t.outcome] = counts.get(t.outcome, 0) + 1
        return counts

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "should_trigger": self.should_trigger,
            "origin": self.origin,
            "trials": self.trial_count,
            "passes": self.pass_count,
            "pass_rate": round(self.pass_rate, 4),
            "outcomes": self.outcome_counts,
            "results": [t.to_dict() for t in self.trials],
        }


def _rate(num: int, den: int) -> float:
    return (num / den) if den else 0.0


def _graded(trials: Sequence["TrialResult"]) -> int:
    """Trials that actually produced signal — everything that is not a non-outcome.

    ROOT PREDICATE for "did this run measure anything?". Deliberately expressed as
    "not in :data:`NON_PASS_ERRORS`" rather than as a list of specific failure
    causes: a growing catalogue of error classes (FixtureError today, OSError
    tomorrow) is how ``--allow-errors --threshold 0.0`` kept finding a sibling
    source of ERROR that no gate covered.
    """
    return sum(1 for t in trials if t.outcome not in NON_PASS_ERRORS)


def aggregate(case_results: Sequence[CaseResult], case_threshold: float = DEFAULT_CASE_THRESHOLD) -> dict[str, Any]:
    """Roll per-trial outcomes into the distribution the harness reports."""
    trials = [t for c in case_results for t in c.trials]
    passes = sum(1 for t in trials if t.passed)

    pos = [c for c in case_results if c.should_trigger]
    neg = [c for c in case_results if not c.should_trigger]
    pos_trials = [t for c in pos for t in c.trials]
    neg_trials = [t for c in neg for t in c.trials]

    outcome_counts: dict[str, int] = {}
    for t in trials:
        outcome_counts[t.outcome] = outcome_counts.get(t.outcome, 0) + 1

    cases_at_threshold = [c for c in case_results if c.pass_rate >= case_threshold]
    costs = [t.cost_usd for t in trials if t.cost_usd is not None]
    durations = [t.duration_ms for t in trials if t.duration_ms is not None]

    return {
        "cases": len(case_results),
        "trials": len(trials),
        "passes": passes,
        "trial_pass_rate": round(_rate(passes, len(trials)), 4),
        # THE evidence counter. A trial whose outcome is ERROR or INVISIBLE was
        # never graded — the CLI never launched, the fixture never vouched for
        # itself, the skill was never loaded — so it carries no signal about the
        # skill at all. `trials` counts attempts; `graded_trials` counts evidence,
        # and only the second one can support a pass. See `decide_exit_code`.
        "graded_trials": _graded(trials),
        "min_trials_per_case": min((c.trial_count for c in case_results), default=0),
        "case_threshold": case_threshold,
        "cases_at_threshold": len(cases_at_threshold),
        "case_pass_rate": round(_rate(len(cases_at_threshold), len(case_results)), 4),
        "positive": {
            "cases": len(pos),
            "trials": len(pos_trials),
            "graded_trials": _graded(pos_trials),
            "passes": sum(1 for t in pos_trials if t.passed),
            "pass_rate": round(_rate(sum(1 for t in pos_trials if t.passed), len(pos_trials)), 4),
        },
        "negative": {
            "cases": len(neg),
            "trials": len(neg_trials),
            "graded_trials": _graded(neg_trials),
            "passes": sum(1 for t in neg_trials if t.passed),
            "pass_rate": round(_rate(sum(1 for t in neg_trials if t.passed), len(neg_trials)), 4),
        },
        "outcomes": outcome_counts,
        "errors": sum(outcome_counts.get(k, 0) for k in NON_PASS_ERRORS),
        # Split out because --allow-errors may forgive an ERROR (a CLI/fixture
        # failure) but must never forgive an INVISIBLE (the skill was not loaded,
        # so every result in that trial is vacuous).
        "invisible": outcome_counts.get(INVISIBLE, 0),
        "total_cost_usd": round(sum(costs), 6) if costs else None,
        "mean_cost_usd": round(sum(costs) / len(costs), 6) if costs else None,
        "mean_duration_ms": int(sum(durations) / len(durations)) if durations else None,
    }


def decide_exit_code(
    agg: dict[str, Any],
    threshold: float,
    *,
    fixtures_unusable: bool = False,
    allow_errors: bool = False,
    positive_threshold: float | None = None,
) -> int:
    """Gate logic, ordered so that the cheapest way to fake green is closed first.

    Two invariants sit ABOVE every flag, and both are single predicates rather
    than lists of forgivable causes — the list form is what kept leaving a sibling
    hole open one error class at a time:

    1. **A run that graded zero real trials cannot pass.** ``graded_trials`` counts
       trials that produced signal (anything not ERROR/INVISIBLE). Zero of them
       means the harness measured nothing, whatever the cause: an empty replay
       set, fixtures bound to another description, or — the case the flag-specific
       version missed — a LIVE run whose CLI could not be launched at all, where
       every trial is ``ERROR — could not launch runner: [Errno 13] …``. No
       combination of ``--allow-errors`` and ``--threshold 0.0`` reaches exit 0
       from there.
    2. **A positive arm that never once passed cannot pass.** ``--threshold`` may
       lower the *rate* the positive arm must clear, but not below the floor of
       one demonstrated firing: a suite where the skill fired 0/33 times is a total
       trigger failure, which is precisely the regression this harness exists to
       catch, and ``--threshold 0.0`` must not be able to green it.

    ``fixtures_unusable`` outranks everything too. It covers missing, short, and
    integrity-failed fixture sets — a stale fixture is not a scoring error to be
    forgiven, it is an absence of evidence.

    INVISIBLE trials likewise outrank ``--allow-errors``: a run where the skill was
    never loaded is vacuous by construction and no flag may forgive it.

    Above those floors, the **positive** pass rate is gated separately from the
    aggregate. An aggregate is dominated by whichever arm has more trials, so a
    skill that fires rarely still sweeps a negative-heavy suite.
    """
    if fixtures_unusable:
        return EXIT_FIXTURES
    # (1) no evidence at all — subsumes the old `not agg["trials"]` check, and
    # covers every source of a non-outcome rather than the ones named so far.
    if not agg.get("graded_trials", agg.get("trials", 0)):
        return EXIT_FIXTURES
    if agg.get("invisible", 0):
        return EXIT_BELOW_THRESHOLD
    if agg.get("errors", 0) and not allow_errors:
        return EXIT_BELOW_THRESHOLD

    positive = agg.get("positive") or {}
    if not positive.get("trials"):
        return EXIT_BELOW_THRESHOLD
    # (2) the floor --threshold cannot lower: the skill has to have fired and
    # passed at least once, on evidence that was actually graded.
    if not positive.get("passes") or not positive.get("graded_trials", positive.get("trials", 0)):
        return EXIT_BELOW_THRESHOLD
    bar = threshold if positive_threshold is None else positive_threshold
    if positive.get("pass_rate", 0.0) < bar:
        return EXIT_BELOW_THRESHOLD

    return EXIT_OK if agg.get("trial_pass_rate", 0.0) >= threshold else EXIT_BELOW_THRESHOLD


# ---------------------------------------------------------------------------
# execution
# ---------------------------------------------------------------------------


@dataclass
class RunConfig:
    skill: str
    skill_dir: Path
    trials: int = DEFAULT_TRIALS
    visibility: Visibility = field(default_factory=lambda: VISIBILITY_REGISTRY["present"])
    jobs: int = 1
    keep_workspaces: bool = False


def run_case(runner: Runner, case: Case, cfg: RunConfig) -> CaseResult:
    """Run every trial of one case, each in its own fresh workspace."""
    result = CaseResult(case_id=case.id, should_trigger=case.should_trigger, origin=case.origin)
    n = runner.trials_for(case.id, cfg.trials)

    if n <= 0:
        result.trials.append(
            TrialResult(
                case_id=case.id,
                trial=1,
                outcome=ERROR,
                detail="no transcript available for this case (missing fixture)",
            )
        )
        return result

    for trial in range(1, n + 1):
        tmp = Path(tempfile.mkdtemp(prefix=f"skilleval-{case.id}-{trial}-"))
        try:
            ws = build_workspace(tmp, cfg.skill_dir, cfg.skill, cfg.visibility)
            transcript = runner.run(case.prompt, ws, case_id=case.id, trial=trial)
        except FixtureError as exc:
            result.trials.append(
                TrialResult(case_id=case.id, trial=trial, outcome=ERROR, detail=str(exc))
            )
            continue
        except OSError as exc:
            result.trials.append(
                TrialResult(
                    case_id=case.id, trial=trial, outcome=ERROR,
                    detail=f"could not launch runner: {exc}",
                )
            )
            continue
        else:
            result.trials.append(
                grade_trial(
                    case, transcript, cfg.skill, trial=trial,
                    expect_visible=cfg.visibility.expects_visible, workspace=str(ws),
                )
            )
        finally:
            if not cfg.keep_workspaces:
                shutil.rmtree(tmp, ignore_errors=True)
    return result


def run_suite(runner: Runner, prompt_set: PromptSet, cfg: RunConfig) -> list[CaseResult]:
    if cfg.jobs <= 1:
        return [run_case(runner, c, cfg) for c in prompt_set.cases]
    with ThreadPoolExecutor(max_workers=cfg.jobs) as pool:
        return list(pool.map(lambda c: run_case(runner, c, cfg), prompt_set.cases))


# ---------------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------------


def _bar(rate: float, width: int = 10) -> str:
    filled = int(round(rate * width))
    return "█" * filled + "·" * (width - filled)


def format_report(
    case_results: Sequence[CaseResult],
    agg: dict[str, Any],
    *,
    mode: str,
    skill: str,
    threshold: float,
    exit_code: int,
) -> str:
    lines: list[str] = []
    lines.append("")
    lines.append(f"{'CASE':<22}{'ORIGIN':<12}{'EXPECT':<8}{'N':>3}  {'PASS':>4}  {'RATE':>5}  DISTRIBUTION")
    lines.append("-" * 92)
    for c in case_results:
        dist = " ".join(f"{k}x{v}" for k, v in sorted(c.outcome_counts.items()))
        lines.append(
            f"{c.case_id[:21]:<22}{c.origin[:11]:<12}"
            f"{'fire' if c.should_trigger else 'quiet':<8}"
            f"{c.trial_count:>3}  {c.pass_count:>4}  {c.pass_rate:>5.2f}  "
            f"{_bar(c.pass_rate)} {dist}"
        )
        for t in c.trials:
            if not t.passed:
                lines.append(f"{'':<22}  trial {t.trial}: {t.outcome} — {t.detail[:120]}")
    lines.append("-" * 92)
    lines.append("AGGREGATE")
    shape = (
        "distribution"
        if agg.get("min_trials_per_case", 0) >= MIN_DISTRIBUTION_TRIALS
        else f"ANECDOTE (n={agg.get('min_trials_per_case', 0)} on at least one case)"
    )
    lines.append(
        f"  trials      {agg['passes']}/{agg['trials']} passed        "
        f"trial pass-rate {agg['trial_pass_rate']:.3f}   [{shape}]"
    )
    lines.append(
        f"  cases       {agg['cases_at_threshold']}/{agg['cases']} at >= "
        f"{agg['case_threshold']:.2f}   case pass-rate  {agg['case_pass_rate']:.3f}"
    )
    lines.append(
        f"  positives   {agg['positive']['passes']}/{agg['positive']['trials']} "
        f"({agg['positive']['pass_rate']:.3f})   "
        f"negatives {agg['negative']['passes']}/{agg['negative']['trials']} "
        f"({agg['negative']['pass_rate']:.3f})"
    )
    # The positive arm is gated on its own. Say so when it is what failed, or the
    # reader is left comparing the aggregate against the threshold and finding it fine.
    if not agg["positive"]["trials"]:
        lines.append(
            "              ^ NO POSITIVE TRIALS — this run never demonstrated the skill "
            "firing, so it cannot pass"
        )
    elif not agg["positive"]["passes"]:
        lines.append(
            "              ^ ZERO POSITIVE PASSES — total trigger failure; no --threshold "
            "lowers this floor"
        )
    elif agg["positive"]["pass_rate"] < threshold:
        lines.append(
            f"              ^ positive arm is below the {threshold:.2f} bar; the aggregate "
            "does not rescue it"
        )
    if agg.get("errors"):
        lines.append(f"  errors      {agg['errors']} trial(s) produced no signal (ERROR/INVISIBLE)")
    # The evidence counter, printed whenever it is not the whole run — and shouted
    # when it is zero, which is the only state no flag combination can green.
    graded = agg.get("graded_trials", agg["trials"])
    if not graded:
        lines.append(
            f"  graded      0/{agg['trials']} trials produced ANY signal — this run measured "
            "nothing, so it cannot pass under any flag"
        )
    elif graded < agg["trials"]:
        lines.append(f"  graded      {graded}/{agg['trials']} trials produced signal")
    if agg.get("total_cost_usd") is not None:
        # In replay these numbers are read out of the fixture, not incurred now.
        # Saying so is the only honest option: the harness cannot verify a cost it
        # did not pay, so it must never let one read as fresh spend.
        provenance = " (as recorded in fixtures — not re-incurred)" if mode == "replay" else ""
        lines.append(
            f"  cost        ${agg['total_cost_usd']:.4f} total, "
            f"${agg['mean_cost_usd']:.4f}/trial   "
            f"mean {(agg['mean_duration_ms'] or 0) / 1000:.1f}s/trial{provenance}"
        )
    verdict = "PASS" if exit_code == EXIT_OK else "FAIL"
    lines.append(
        f"  threshold   {threshold:.2f} -> {verdict} (exit {exit_code})   "
        f"[mode={mode.upper()} skill={skill}]"
    )
    # Name the actual cause. Reading "threshold -> FAIL" on an exit that the
    # threshold did not produce sends the reader to fix the wrong thing — the
    # numbers above are the PRESENT arm and are unaffected.
    if exit_code == EXIT_ABLATION_UNUSABLE:
        lines.append(
            "              ^ exit 4 is the ABLATION BASELINE, not this arm: the "
            "measurement is void, the numbers above stand"
        )
    lines.append("")
    return "\n".join(lines)


def build_report(
    prompt_set: PromptSet,
    case_results: Sequence[CaseResult],
    agg: dict[str, Any],
    *,
    mode: str,
    threshold: float,
    exit_code: int,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "skill": prompt_set.skill,
        "prompt_set": str(prompt_set.path) if prompt_set.path else None,
        "mode": mode,
        "threshold": threshold,
        "exit_code": exit_code,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "meta": meta or {},
        "aggregate": agg,
        "cases": [c.to_dict() for c in case_results],
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def detect_cli(explicit: str | None) -> str | None:
    if explicit:
        return explicit
    found = shutil.which("claude")
    if found:
        return found
    fallback = Path.home() / ".local" / "bin" / "claude"
    return str(fallback) if fallback.is_file() else None


def cli_version(cli: str) -> str:
    try:
        proc = subprocess.run([cli, "--version"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return ""
    return (proc.stdout or "").strip().split(" ")[0]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="skill-evals",
        description="Run a skill's prompt set through a real agent CLI and grade trigger + outcome.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "modes:\n"
            "  live (default)  shells out to the real CLI; add --record DIR to save transcripts\n"
            "  --replay DIR    re-grade recorded transcripts; free, and used by CI\n\n"
            "Replay is bound to the artifact: every fixture carries the SKILL.md and\n"
            "description hashes it was recorded against, and a mismatch is fatal, so an\n"
            "edited description turns the gate RED instead of replaying stale green.\n"
            "Missing, empty and short fixture sets exit non-zero regardless of the numbers.\n"
            "It does NOT authenticate transcripts — see README § guarantees.\n"
        ),
    )
    p.add_argument("--skill", help="skill name; resolves <skills-root>/<bucket>/<skill>/")
    p.add_argument("--prompts", type=Path, help="explicit path to prompts.json")
    p.add_argument("--skills-root", type=Path, default=DEFAULT_SKILLS_ROOT)
    p.add_argument("--skill-dir", type=Path, help="explicit skill directory (overrides lookup)")
    p.add_argument("--trials", type=int, default=DEFAULT_TRIALS, help="trials per case (default 3)")
    p.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                   help="aggregate trial pass-rate required to exit 0 (default 0.80)")
    p.add_argument("--case-threshold", type=float, default=DEFAULT_CASE_THRESHOLD,
                   help="per-case pass rate counted as a passing case (default 0.60)")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--cli", help="path to the agent CLI (default: which claude)")
    p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S, help="per-trial seconds")
    p.add_argument("--replay", type=Path, metavar="DIR", help="grade recorded transcripts instead of calling the CLI")
    p.add_argument("--record", type=Path, metavar="DIR", help="save live transcripts for later replay")
    p.add_argument("--strict-fixtures", action="store_true",
                   help="also treat model / CLI-version drift in a fixture as fatal "
                        "(prompt-hash and skill-hash mismatches are ALWAYS fatal)")
    p.add_argument("--allow-synthetic-fixtures", action="store_true",
                   help="grade hand-authored fixtures (harness self-test only — a synthetic "
                        "fixture says nothing about a real skill's trigger behaviour)")
    # NOTE: the positive-arm bar is deliberately NOT a flag. Its *rate* is pinned
    # to --threshold, and beneath that it has a floor no flag can lower: at least
    # one positive trial must have been graded AND passed, so `--threshold 0.0`
    # cannot green a suite in which the skill never fired once (decide_exit_code
    # invariant 2). `positive_threshold` exists as a decide_exit_code parameter
    # for tests only, and is likewise bounded below by that floor.
    p.add_argument("--report", type=Path, help="write the full JSON report here")
    p.add_argument("--json", action="store_true", help="print the JSON report to stdout")
    p.add_argument("--case", action="append", dest="cases", metavar="ID", help="run only this case id (repeatable)")
    p.add_argument("--jobs", type=int, default=1,
                   help="parallel cases (default 1; high fan-out contends on the shared config dir)")
    p.add_argument("--visibility", default="present", choices=sorted(VISIBILITY_REGISTRY),
                   help="how the skill is exposed to each case workspace")
    p.add_argument("--disallow-recovery-tools", action="store_true",
                   help="live only: block Read/Grep/Glob/Bash so the agent cannot read SKILL.md off disk")
    p.add_argument("--keep-workspaces", action="store_true", help="do not delete case temp dirs")
    p.add_argument("--no-env-jail", action="store_true",
                   help="live only, DANGEROUS: let case runs inherit the real environment. "
                        "A skill script resolving state from $HOME (p9's config dir, kg's "
                        "workspace) then reads and writes the REAL one. Exists so the escape "
                        "mutation-proof has something to prove against.")
    p.add_argument("--verify-jail", action="store_true",
                   help="run the jail proof and exit; reports where a case run's $HOME, "
                        "XDG paths and skill state dirs actually resolve")
    p.add_argument("--fail-on-real-state-change", action="store_true",
                   help="promote the real-state watch from a warning to a failure. Off by "
                        "default because the watched stores are shared: a p9 watcher in "
                        "another terminal is indistinguishable from a leak by mtime alone.")
    p.add_argument("--allow-errors", action="store_true",
                   help="diagnostics only: do not fail the run on ERROR trials (CLI/fixture "
                        "failures). INVISIBLE trials still fail — a run where the skill was "
                        "never loaded is vacuous and no flag forgives it.")
    p.add_argument("--expect-cli-version", default=EXPECTED_CLI_VERSION)
    p.add_argument("--no-version-check", action="store_true")
    p.add_argument("--ablate", action="store_true",
                   help="BRO-2006: also run the prompt set with the skill UNINSTALLED and "
                        "report the lift. Doubles the trial count and therefore the spend.")
    p.add_argument("--ablate-baseline", default="absent", choices=ABLATION_BASELINES,
                   help="BRO-2028: which arm --ablate compares against. 'absent' (default) "
                        "uninstalls the skill and measures ITS marginal value. 'bare' installs "
                        "it with the description stripped and measures the DESCRIPTION's "
                        "marginal value over the name alone — the rationed-roster condition "
                        "~75%% of skills are actually delivered in.")
    p.add_argument("--ablation-min-trials", type=int, default=ablation_mod.ABLATION_MIN_TRIALS,
                   help="below this many graded positive trials per arm the verdict is "
                        "'underpowered' rather than a number a reader would act on")
    p.add_argument("--ablation-margin", type=float, default=ablation_mod.ABLATION_MARGIN,
                   help="a lift interval entirely below this marks a retirement candidate")
    p.add_argument("--fail-on-retire-candidate", action="store_true",
                   help="exit non-zero when the ablation verdict is retire-candidate "
                        "(opt-in; --ablate is report-only by default)")
    p.add_argument("--dry-run", action="store_true",
                   help="print the plan and the trial count, then exit without spending")
    p.add_argument("--validate-only", action="store_true", help="validate the prompt set and exit")
    p.add_argument("--list-checks", action="store_true", help="print CHECK_REGISTRY ids and exit")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.list_checks:
        for check_id, fn in sorted(checks_mod.CHECK_REGISTRY.items()):
            doc = (fn.__doc__ or "").strip().splitlines()
            print(f"{check_id:<40}{doc[0] if doc else ''}")
        return EXIT_OK

    if args.verify_jail:
        tmp = Path(tempfile.mkdtemp(prefix="skilleval-verify-jail-"))
        try:
            jail_mod.prepare_jail(tmp)
            verdict = jail_mod.verify_jail(tmp)
            for key, value in sorted(verdict.resolved.items()):
                print(f"  {key:<16}{value}")
            if verdict.holds:
                print("\njail HOLDS: every probed path resolved inside the case workspace")
                return EXIT_OK
            for leak in verdict.escapes:
                print(f"[skill-evals] ESCAPE   {leak}", file=sys.stderr)
            return EXIT_BELOW_THRESHOLD
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    if not args.skill and not args.prompts:
        print("error: one of --skill or --prompts is required", file=sys.stderr)
        return EXIT_USAGE

    # -- resolve skill + prompt set -----------------------------------------
    try:
        if args.skill_dir:
            skill_dir = Path(args.skill_dir)
        elif args.skill:
            skill_dir = find_skill_dir(args.skills_root, args.skill)
        else:
            skill_dir = Path(args.prompts).resolve().parent.parent
        prompts_path = Path(args.prompts) if args.prompts else default_prompts_path(skill_dir)
        raw = json.loads(prompts_path.read_text(encoding="utf-8"))
    except (PromptSetError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    errors, warnings = validate_prompt_set(raw)
    for w in warnings:
        print(f"[skill-evals] WARNING  {w}", file=sys.stderr)
    if errors:
        for e in errors:
            print(f"[skill-evals] ERROR    {e}", file=sys.stderr)
        return EXIT_USAGE
    prompt_set = parse_prompt_set(raw, path=prompts_path)

    # A prompt set graded against a different skill than it declares measures
    # nothing about either one. Silently preferring --skill let a mismatch through.
    if args.skill and prompt_set.skill != args.skill:
        print(
            f"[skill-evals] ERROR    prompt set declares skill {prompt_set.skill!r} "
            f"but --skill is {args.skill!r}. Grading a prompt set against a different "
            "skill than it was written for is meaningless; fix one of the two.",
            file=sys.stderr,
        )
        return EXIT_USAGE
    skill = args.skill or prompt_set.skill

    # -- bind the run to the artifact under test -----------------------------
    try:
        fingerprint = skill_fingerprint(skill_dir)
    except (SkillArtifactError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    if args.cases:
        wanted = set(args.cases)
        missing = wanted - {c.id for c in prompt_set.cases}
        if missing:
            print(f"error: no such case id(s): {sorted(missing)}", file=sys.stderr)
            return EXIT_USAGE
        prompt_set = PromptSet(
            skill=prompt_set.skill,
            version=prompt_set.version,
            cases=[c for c in prompt_set.cases if c.id in wanted],
            notes=prompt_set.notes,
            path=prompt_set.path,
        )

    # -- build the runner ----------------------------------------------------
    meta: dict[str, Any] = {
        "skill_dir": str(skill_dir),
        "trials_requested": args.trials,
        "skill_md_sha256": fingerprint["skill_md_sha256"],
        "description_sha256": fingerprint["description_sha256"],
    }
    runner: Runner
    if args.replay:
        if args.record:
            print("error: --record is meaningless with --replay", file=sys.stderr)
            return EXIT_USAGE
        runner = ReplayRunner(
            root=Path(args.replay),
            fingerprint=fingerprint,
            strict_prompt_hash=args.strict_fixtures,
            allow_synthetic=args.allow_synthetic_fixtures,
            expected_skill=skill,
            expected_model=args.model,
            expected_cli_version=args.expect_cli_version,
        )
        mode_line = f"mode=REPLAY  fixtures={args.replay}"
        if args.allow_synthetic_fixtures:
            mode_line += "  SYNTHETIC-FIXTURES-ALLOWED (grades the harness, not a real skill)"
    else:
        cli = detect_cli(args.cli)
        if not cli:
            print("error: agent CLI not found; pass --cli /path/to/claude", file=sys.stderr)
            return EXIT_USAGE
        version = "" if args.no_version_check else cli_version(cli)
        meta["cli"] = cli
        meta["cli_version"] = version
        if version and version != args.expect_cli_version:
            print(
                f"[skill-evals] WARNING  CLI version {version} != expected "
                f"{args.expect_cli_version}; stream-json shape is only verified for the latter",
                file=sys.stderr,
            )
        runner = LiveRunner(
            cli=cli,
            model=args.model,
            timeout_s=args.timeout,
            record_dir=Path(args.record) if args.record else None,
            disallow_recovery_tools=args.disallow_recovery_tools,
            skill=skill,
            cli_version=version,
            fingerprint=fingerprint,
            env_jail=not args.no_env_jail,
        )
        mode_line = f"mode=LIVE  cli={cli} ({version or 'unknown'})  model={args.model}"
        if args.record:
            mode_line += f"  record={args.record}"
        mode_line += "  env-jail=" + ("ON" if not args.no_env_jail else "OFF")

    # The mode banner prints on EVERY invocation. A harness whose replay path is
    # indistinguishable from its live path is how mocks become the only path.
    print(
        f"[skill-evals] {mode_line}\n"
        f"[skill-evals] skill={skill}  cases={len(prompt_set.cases)}  "
        f"trials/case={args.trials}  visibility={args.visibility}  "
        f"prompts={prompts_path}\n"
        f"[skill-evals] artifact={fingerprint['skill_md_path']}  "
        f"skill_md={fingerprint['skill_md_sha256'][:12]}  "
        f"description={fingerprint['description_sha256'][:12]}",
        file=sys.stderr,
    )
    if args.trials < MIN_DISTRIBUTION_TRIALS:
        print(
            f"[skill-evals] WARNING  --trials {args.trials} is an anecdote, not a "
            f"distribution ({MIN_DISTRIBUTION_TRIALS}+ required to read as one); the "
            "report is labelled accordingly",
            file=sys.stderr,
        )

    if args.validate_only:
        print(f"[skill-evals] prompt set OK: {len(prompt_set.cases)} cases "
              f"({len(prompt_set.positives)} positive / {len(prompt_set.negatives)} negative)")
        return EXIT_OK

    # --ablate runs the POSITIVE cases a second time with the skill uninstalled;
    # negatives are not re-run, because an uninstalled skill cannot over-trigger and
    # spending on a case that asserts nothing is just spending.
    ablate_trials = (
        len(_baseline_cases(prompt_set, args.ablate_baseline)) * args.trials
        if args.ablate else 0
    )
    planned = len(prompt_set.cases) * args.trials + ablate_trials
    if args.ablate:
        if args.visibility != "present":
            print("error: --ablate owns both arms; do not also pass --visibility",
                  file=sys.stderr)
            return EXIT_USAGE
        # Both refusals are for the same missing piece: fixtures are stored per CASE,
        # not per ARM, so the two arms of an ablation cannot coexist in one directory.
        if args.record:
            print(
                "error: --ablate with --record would write the ABSENT arm's transcripts "
                "over the PRESENT arm's, destroying the live evidence you just paid for "
                "— every positive case would replay as INVISIBLE. Record the arms "
                "separately (--visibility present / absent into different --record dirs) "
                "until fixtures are arm-namespaced.",
                file=sys.stderr,
            )
            return EXIT_USAGE
        if args.replay:
            print(
                "error: --ablate with --replay cannot produce a measurement: both arms "
                "would replay the SAME fixtures, so the baseline is 100% LEAKED by "
                "construction. Ablation needs live runs.",
                file=sys.stderr,
            )
            return EXIT_USAGE
        measures = (
            "the SKILL's marginal value over a model without it"
            if args.ablate_baseline == "absent"
            else "the DESCRIPTION's marginal value over the name alone (BRO-2028)"
        )
        print(
            f"[skill-evals] ABLATION: {len(prompt_set.cases)}x{args.trials} present + "
            f"{len(_baseline_cases(prompt_set, args.ablate_baseline))}x{args.trials} "
            f"{args.ablate_baseline} = {planned} "
            f"trials ({'replay' if args.replay else 'LIVE — this costs money'})\n"
            f"[skill-evals] baseline={args.ablate_baseline} — measuring {measures}",
            file=sys.stderr,
        )
    if args.dry_run:
        print(f"[skill-evals] DRY RUN: would run {planned} trial(s); nothing was spent")
        return EXIT_OK

    # -- replay fixture guard ------------------------------------------------
    # Checks availability against the REQUESTED trial count, not against zero.
    # Testing `== 0` let a one-trial-per-case fixture set satisfy `--trials 3`,
    # silently clamp, and still print a "distribution".
    fixtures_unusable = False
    if isinstance(runner, ReplayRunner):
        counts = {c.id: runner.available(c.id) for c in prompt_set.cases}
        empty = [cid for cid, n in counts.items() if n == 0]
        short = [(cid, n) for cid, n in counts.items() if 0 < n < args.trials]
        if len(empty) == len(prompt_set.cases):
            print(
                f"[skill-evals] FIXTURE GUARD: no recorded transcripts under {args.replay} — "
                "refusing to report a pass from an empty replay set. "
                "Record first: --record DIR on a live run.",
                file=sys.stderr,
            )
            return EXIT_FIXTURES
        if empty:
            fixtures_unusable = True
            print(
                f"[skill-evals] FIXTURE GUARD: {len(empty)} case(s) have no fixtures "
                f"({', '.join(empty[:6])}{'...' if len(empty) > 6 else ''}); "
                "these score ERROR and the run cannot exit 0.",
                file=sys.stderr,
            )
        if short:
            fixtures_unusable = True
            detail = ", ".join(f"{cid}={n}" for cid, n in short[:6])
            print(
                f"[skill-evals] FIXTURE GUARD: {len(short)} case(s) have fewer than the "
                f"{args.trials} requested trials ({detail}{'...' if len(short) > 6 else ''}). "
                "A short fixture set is an ERROR, not a silent clamp: re-record, or ask for "
                "the number of trials you actually have.",
                file=sys.stderr,
            )

    # -- run -----------------------------------------------------------------
    cfg = RunConfig(
        skill=skill,
        skill_dir=skill_dir,
        trials=args.trials,
        visibility=VISIBILITY_REGISTRY[args.visibility],
        jobs=max(1, args.jobs),
        keep_workspaces=args.keep_workspaces,
    )

    # BRO-2018. A live suite is about to run skill scripts for real, with
    # bypassPermissions, N times per case. Prove the jail contains their path
    # resolution BEFORE any of that — the proof is a subprocess launch, costs no
    # model call, and the alternative is discovering the leak by reading the
    # user's corrupted p9 store afterwards.
    is_live = not isinstance(runner, ReplayRunner)
    watch: jail_mod.RealStateWatch | None = None
    if is_live and not args.no_env_jail:
        probe_dir = Path(tempfile.mkdtemp(prefix="skilleval-jailcheck-"))
        try:
            jail_mod.prepare_jail(probe_dir)
            verdict = jail_mod.verify_jail(probe_dir)
        finally:
            shutil.rmtree(probe_dir, ignore_errors=True)
        if not verdict.holds:
            print(
                "[skill-evals] JAIL CHECK FAILED — refusing to run live. A case run's "
                "paths resolve outside its workspace, so the suite would read and write "
                "real skill state:",
                file=sys.stderr,
            )
            for leak in verdict.escapes:
                print(f"[skill-evals]   - {leak}", file=sys.stderr)
            return EXIT_USAGE
        print(f"[skill-evals] jail check OK  {jail_mod.describe_jail(Path('<case-ws>'))}",
              file=sys.stderr)
        # The jail moves HOME, and on macOS the CLI's credential lives under HOME.
        # If there is nothing to link back, every trial is about to ERROR with
        # "Not logged in" and read as a total trigger failure. Say so now.
        if jail_mod.auth_material_missing():
            print(
                "[skill-evals] WARNING  no credential material found to link into the "
                "jail. The jail moves HOME, and the CLI's login lives under it, so "
                "trials may all fail with 'Not logged in' — that would be a setup "
                "problem, not a result about the skill.",
                file=sys.stderr,
            )
    elif is_live:
        print(
            "[skill-evals] WARNING  --no-env-jail: case runs inherit the real "
            "environment. A skill that resolves state from $HOME will read and write "
            "the REAL store. Use this only to prove the jail matters.",
            file=sys.stderr,
        )

    if is_live:
        watch = jail_mod.RealStateWatch()
        watch.snapshot()

    case_results = run_suite(runner, prompt_set, cfg)

    real_state_changes: list[str] = watch.changes() if watch is not None else []
    if real_state_changes:
        meta["real_state_changes"] = real_state_changes
        print(
            f"[skill-evals] REAL STATE CHANGED during this run — {len(real_state_changes)} "
            f"path(s) under {', '.join(jail_mod.DEFAULT_WATCHED_PATHS)} moved. Either a case "
            "escaped its jail, or another process on this machine wrote them:",
            file=sys.stderr,
        )
        for line in real_state_changes[:8]:
            print(f"[skill-evals]   - {line}", file=sys.stderr)

    # A suite that ERRORs on "Not logged in" is a jail-setup failure wearing the
    # costume of a total trigger failure. Name it, or the next reader concludes the
    # skill's description is broken.
    if is_live and any(
        "not logged in" in t.detail.lower()
        for c in case_results for t in c.trials if t.outcome == ERROR
    ):
        print(
            "[skill-evals] HINT  trials failed with 'Not logged in'. The jail moves "
            "HOME, and on macOS the CLI's token is in the login keychain UNDER $HOME. "
            "Check that the keychain linked into the jail "
            f"({', '.join(jail_mod.AUTH_PASSTHROUGH.get(sys.platform, ('n/a',)))}) exists. "
            "This is a setup failure, not a result about the skill.",
            file=sys.stderr,
        )

    if isinstance(runner, ReplayRunner):
        for msg in runner.provenance_notes:
            print(f"[skill-evals] WARNING  fixture drift: {msg}", file=sys.stderr)
        if runner.stale_fixtures:
            # Its own line because its remedy is its own: the PROMPT SET moved, so
            # re-record; nothing is wrong with the skill or the fixture format.
            meta["stale_prompt_fixtures"] = list(runner.stale_fixtures)
            print(
                f"[skill-evals] FIXTURE GUARD: {len(runner.stale_fixtures)} fixture(s) were "
                "recorded against a DIFFERENT PROMPT than the prompt set now carries; "
                "re-record those cases:",
                file=sys.stderr,
            )
            for msg in runner.stale_fixtures[:8]:
                print(f"[skill-evals]   - {msg}", file=sys.stderr)
        if runner.integrity_failures:
            # NOT folded into the pass rate: a fixture that cannot vouch for itself
            # is absent evidence, and absent evidence outranks every scoring flag.
            fixtures_unusable = True
            print(
                f"[skill-evals] FIXTURE GUARD: {len(runner.integrity_failures)} fixture "
                "integrity failure(s); the run cannot exit 0 regardless of --threshold "
                "or --allow-errors:",
                file=sys.stderr,
            )
            for msg in runner.integrity_failures[:8]:
                print(f"[skill-evals]   - {msg}", file=sys.stderr)

    agg = aggregate(case_results, case_threshold=args.case_threshold)
    exit_code = decide_exit_code(
        agg,
        args.threshold,
        fixtures_unusable=fixtures_unusable,
        allow_errors=args.allow_errors,
    )
    if real_state_changes and args.fail_on_real_state_change and exit_code == EXIT_OK:
        print(
            "[skill-evals] --fail-on-real-state-change: the numbers passed, but this run "
            "did not leave the machine as it found it.",
            file=sys.stderr,
        )
        exit_code = EXIT_BELOW_THRESHOLD
    report = build_report(
        prompt_set, case_results, agg,
        mode=runner.mode, threshold=args.threshold, exit_code=exit_code, meta=meta,
    )

    # -- the ablation baseline (BRO-2006) ------------------------------------
    if args.ablate:
        baseline_set = PromptSet(
            skill=prompt_set.skill, version=prompt_set.version,
            cases=list(_baseline_cases(prompt_set, args.ablate_baseline)),
            notes=prompt_set.notes, path=prompt_set.path,
        )
        absent_cfg = RunConfig(
            skill=skill, skill_dir=skill_dir, trials=args.trials,
            visibility=VISIBILITY_REGISTRY[args.ablate_baseline], jobs=max(1, args.jobs),
            keep_workspaces=args.keep_workspaces,
        )
        print(
            f"[skill-evals] running the {args.ablate_baseline.upper()} arm "
            f"({'skill uninstalled' if args.ablate_baseline == 'absent' else 'installed, description stripped'})",
            file=sys.stderr,
        )
        absent_results = run_suite(runner, baseline_set, absent_cfg)
        absent_agg = aggregate(absent_results, case_threshold=args.case_threshold)
        absent_report = build_report(
            baseline_set, absent_results, absent_agg,
            mode=runner.mode, threshold=args.threshold, exit_code=0,
            meta={"arm": args.ablate_baseline},
        )
        comparison = ablation_mod.compare(
            report, absent_report,
            non_pass=sorted(NON_PASS_ERRORS),
            builtin_names=BUILTIN_SKILL_NAMES,
            min_trials=args.ablation_min_trials,
            margin=args.ablation_margin,
        )
        report["ablation"] = comparison
        report["ablation_absent_arm"] = absent_report
        if not args.json:
            print(ablation_mod.format_comparison(comparison))

        # An unusable baseline is its own exit code: nothing is wrong with the
        # SKILL, the MEASUREMENT is void, and reporting that as a threshold failure
        # would send a reader to fix the wrong thing.
        if comparison["leaked_baseline_trials"] or not comparison["absent"]["graded_positive_trials"]:
            print("[skill-evals] ABLATION UNUSABLE: the baseline produced no clean evidence",
                  file=sys.stderr)
            exit_code = exit_code or EXIT_ABLATION_UNUSABLE
        elif args.fail_on_retire_candidate and comparison["verdict"] == ablation_mod.VERDICT_RETIRE:
            exit_code = exit_code or EXIT_BELOW_THRESHOLD
        report["exit_code"] = exit_code

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(format_report(
            case_results, agg, mode=runner.mode, skill=skill,
            threshold=args.threshold, exit_code=exit_code,
        ))
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"[skill-evals] report written to {args.report}", file=sys.stderr)

    return exit_code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

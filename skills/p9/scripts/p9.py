#!/usr/bin/env python3
"""
p9.py — Broomva CI watcher + productive-wait primitive (bstack P9).

Replaces sleep-based CI waits with an event-driven control loop:
  - `gh pr checks <pr> --watch` via run_in_background as the notification
    mechanism (not polling).
  - context-scoped wait-queue draining session/memory/graph/docs/Linear
    while CI runs.
  - classifier (fast regex filter) + evaluator (progress score) self-heal
    loop with stability-budget termination.
  - merge authorization delegated to existing control metalayer
    (.control/policy.yaml). P9 emits MERGE_READY; metalayer authorizes.

Stdlib-only at runtime. Test-only deps (pytest, vcrpy) live under
tests/requirements-dev.txt.

Spec: docs/superpowers/specs/2026-05-04-p9-ci-watcher-design.md
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import datetime as _dt
import enum
import errno
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator

# ─────────────────────────────────────────────────────────────────────────────
# Exit codes (composable shell semantics)
# ─────────────────────────────────────────────────────────────────────────────
EXIT_OK = 0
EXIT_DEGRADED = 1                # recoverable: run again, may succeed
EXIT_POLICY_ERROR = 2            # policy.yaml missing/malformed (fail-closed)
EXIT_USAGE = 3                   # bad CLI args
EXIT_EXTERNAL_ERROR = 4          # gh/Linear/network failure
EXIT_CONCURRENCY_CEILING = 5     # max_concurrent_prs reached
EXIT_HEAL_LOCK_TIMEOUT = 6
EXIT_AUTO_MERGE_BLOCKED = 7      # auto_merge policy says require_human / notify
EXIT_INVARIANT_VIOLATION = 99    # cardinal-rule breach: cannot persist state

# ─────────────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────────────
def p9_home() -> Path:
    """State directory; overridable via BROOMVA_P9_HOME for tests."""
    override = os.environ.get("BROOMVA_P9_HOME")
    if override:
        return Path(override)
    xdg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(xdg) / "broomva" / "p9"


def state_jsonl() -> Path:
    return p9_home() / "state.jsonl"


def wait_queue_jsonl() -> Path:
    return p9_home() / "wait-queue.jsonl"


def pending_escalations_jsonl() -> Path:
    return p9_home() / "pending-escalations.jsonl"


def heal_lock_path() -> Path:
    return p9_home() / "heal.lock"


def state_lock_path() -> Path:
    return p9_home() / "state.lock"


def queue_lock_path() -> Path:
    return p9_home() / "queue.lock"


def session_lock_path() -> Path:
    return p9_home() / "session.lock"


def session_default_id_path() -> Path:
    return p9_home() / "session-default.id"


def current_session_id() -> str:
    """Resolve the scope key for this invocation.

    This is the keystone of parallel-session safety: every state event and
    wait-queue item is stamped with it, and the concurrency ceiling counts
    per-session. Two concurrent agents with *different* session ids never
    collide on the ceiling or steal each other's wait-work.

    Precedence:
      1. ``BROOMVA_P9_SESSION`` env — the contract a parallel harness
         (Fanout P5 worktree, ``bstack wave`` plan, autonomous run) sets
         per session. This is the ONLY way to get true isolation between
         concurrent agents on one machine, because separate processes share
         no other stable per-session marker.
      2. A persisted per-state-dir uuid (``session-default.id``), stable
         across invocations. Keeps single-session / no-env usage on ONE
         scope — i.e. backward-compatible global behavior — rather than
         fragmenting every CLI call into its own scope.

    The fallback is created under ``session.lock`` (double-checked) so a
    burst of concurrent first-invocations converges on a single id.
    """
    env = os.environ.get("BROOMVA_P9_SESSION")
    if env and env.strip():
        return env.strip()
    path = session_default_id_path()
    if path.exists():
        txt = path.read_text(encoding="utf-8").strip()
        if txt:
            return txt
    with file_lock(session_lock_path()):
        if path.exists():
            txt = path.read_text(encoding="utf-8").strip()
            if txt:
                return txt
        sid = "default-" + uuid.uuid4().hex[:12]
        path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write (temp + replace) so a reader on the *unlocked* fast
        # path can never observe a partial id — it sees either no file or the
        # complete one. (The under-lock recheck above already guarantees
        # correctness; this removes any doubt for lock-free readers.)
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(sid, encoding="utf-8")
        os.replace(tmp, path)
        return sid


def policy_yaml_path() -> Path:
    """Resolve .control/policy.yaml.

    Honors BROOMVA_P9_POLICY env var (used by tests). Otherwise walks from
    cwd upward looking for `.control/policy.yaml`.
    """
    override = os.environ.get("BROOMVA_P9_POLICY")
    if override:
        return Path(override)
    cur = Path.cwd().resolve()
    for parent in [cur, *cur.parents]:
        p = parent / ".control" / "policy.yaml"
        if p.exists():
            return p
    return cur / ".control" / "policy.yaml"  # fail-closed marker


def rubric_md_path() -> Path:
    """Locate references/scoring-rubric.md alongside this script."""
    return Path(__file__).resolve().parent.parent / "references" / "scoring-rubric.md"


# ─────────────────────────────────────────────────────────────────────────────
# Errors
# ─────────────────────────────────────────────────────────────────────────────
class P9Error(Exception):
    """Base exception with an exit code."""
    code = EXIT_DEGRADED


class PolicyError(P9Error):
    code = EXIT_POLICY_ERROR


class IllegalTransitionError(P9Error):
    code = EXIT_INVARIANT_VIOLATION


class ConcurrencyCeilingError(P9Error):
    code = EXIT_CONCURRENCY_CEILING


# ─────────────────────────────────────────────────────────────────────────────
# State machine
# ─────────────────────────────────────────────────────────────────────────────
class PRState(str, enum.Enum):
    PUSHED = "PUSHED"
    WATCHING = "WATCHING"
    GREEN = "GREEN"
    RED_CLASSIFIED = "RED_CLASSIFIED"
    RED_UNCLASSIFIED = "RED_UNCLASSIFIED"
    HEALING = "HEALING"
    MERGE_READY = "MERGE_READY"
    MERGED = "MERGED"
    ESCALATED = "ESCALATED"
    ABANDONED = "ABANDONED"


# Allowed (from -> to) transitions. All edges in spec §5.1.
_TRANSITIONS: set[tuple[PRState, PRState]] = {
    (PRState.PUSHED, PRState.WATCHING),
    (PRState.WATCHING, PRState.GREEN),
    (PRState.WATCHING, PRState.RED_CLASSIFIED),
    (PRState.WATCHING, PRState.RED_UNCLASSIFIED),
    (PRState.RED_CLASSIFIED, PRState.HEALING),
    (PRState.RED_CLASSIFIED, PRState.ESCALATED),  # evaluator-stalled
    (PRState.HEALING, PRState.WATCHING),          # heal pushed; new watch cycle
    (PRState.HEALING, PRState.ESCALATED),         # heal corruption / scope violation
    (PRState.RED_UNCLASSIFIED, PRState.ESCALATED),
    (PRState.GREEN, PRState.MERGE_READY),
    (PRState.MERGE_READY, PRState.MERGED),
    (PRState.MERGE_READY, PRState.WATCHING),       # rare: human pushed amend post-green
    # Terminal "abandoned" reachable from any non-terminal — needed for
    # `p9 abandon` and `p9 cleanup` to drain orphans regardless of the
    # state they're parked in.
    (PRState.PUSHED, PRState.ABANDONED),
    (PRState.WATCHING, PRState.ABANDONED),
    (PRState.HEALING, PRState.ABANDONED),
    (PRState.RED_CLASSIFIED, PRState.ABANDONED),
    (PRState.RED_UNCLASSIFIED, PRState.ABANDONED),
    (PRState.GREEN, PRState.ABANDONED),
    (PRState.MERGE_READY, PRState.ABANDONED),
}


def assert_legal_transition(curr: PRState, nxt: PRState) -> None:
    if curr == nxt:
        return  # idempotent self-event allowed (e.g., status refresh)
    if (curr, nxt) not in _TRANSITIONS:
        raise IllegalTransitionError(
            f"Illegal PR state transition: {curr.value} -> {nxt.value}"
        )


def is_terminal(state: PRState) -> bool:
    return state in {PRState.MERGED, PRState.ESCALATED, PRState.ABANDONED}


# ─────────────────────────────────────────────────────────────────────────────
# Dataclasses
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class IsolationTierMap:
    research: str = "none"
    docs: str = "none"
    code_independent: str = "worktree"
    code_dependent: str = "stacked_branch"
    governance: str = "blocked"


@dataclass(frozen=True)
class CIWatchPolicy:
    enabled: bool = True
    max_concurrent_prs: int = 1
    isolation_tier_map: IsolationTierMap = field(default_factory=IsolationTierMap)


@dataclass(frozen=True)
class EscalationChannel:
    linear_team: str = "BRO"
    linear_label: str = "ci-heal-escalation"
    notify_hook: str = "skills/p9/scripts/p9-escalate-notify.sh"


@dataclass(frozen=True)
class CIHealPolicy:
    enabled: bool = True
    max_attempts: int = 5
    stability_floor: float = 0.3
    classified_failure_types: tuple[str, ...] = (
        "lint", "format", "test_flaky", "codegen_drift", "import_missing",
    )
    escalation_channel: EscalationChannel = field(default_factory=EscalationChannel)


@dataclass(frozen=True)
class AutoMergeRule:
    """One auto-merge rule. Either branch_pattern or path_touched (not both).

    branch_pattern: fnmatch glob against the PR's head branch (e.g. "docs/*").
    path_touched:   substring match against any file in the PR diff
                    (e.g. "CLAUDE.md" matches the literal path).
    action:         "auto" → run gh pr merge; "require_human" → hard-block,
                    exit 7; "notify" → emit MERGE_NOTIFIED event, exit 7.

    Rules are evaluated in declaration order; first match wins.
    Matches are short-circuited: `require_human` and `notify` are blocking
    states even if a later rule would auto-merge.
    """
    branch_pattern: str | None = None
    path_touched: str | None = None
    action: str = "notify"


@dataclass(frozen=True)
class AutoMergePolicy:
    enabled: bool = False
    require_no_requested_changes: bool = True
    require_branch_up_to_date: bool = True
    merge_method: str = "squash"          # squash | merge | rebase
    delete_branch: bool = True
    rules: tuple[AutoMergeRule, ...] = ()
    default_action: str = "notify"        # fail-safe default


@dataclass(frozen=True)
class PolicyConfig:
    ci_watch: CIWatchPolicy
    ci_heal: CIHealPolicy
    auto_merge: AutoMergePolicy = field(default_factory=AutoMergePolicy)


@dataclass
class PRStateEvent:
    """One row of state.jsonl."""
    ts: str
    pr: int
    repo: str
    from_state: str
    to_state: str
    watcher_id: str
    attempt: int = 0
    evaluator_score: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    # Scope key (current_session_id). Default "" so old rows and positional
    # callers stay valid; "" means "unscoped / legacy global".
    session_id: str = ""

    def to_jsonl(self) -> str:
        return json.dumps(dataclasses.asdict(self), separators=(",", ":"))


@dataclass(frozen=True)
class ClassifierResult:
    failure_type: str
    classified: bool
    confidence: float
    heal_command: str | None
    signature_hash: str
    rationale: str


@dataclass(frozen=True)
class EvaluatorResult:
    progress_score: float
    signature_changed: bool
    failures_decreased: bool
    budget_remaining: float
    classifier_confidence: float
    stalled: bool


_QUEUE_PRIORITY = ("session", "memory", "graph", "docs", "linear")


@dataclass
class WaitQueueItem:
    """One row of wait-queue.jsonl."""
    id: str
    source: str
    item: str
    created_at: str
    pr: int | None = None
    isolation_tier: str = "none"
    # Scope key + originating repo. Defaults keep old rows / positional
    # callers valid; "" session_id means "unscoped / legacy global".
    session_id: str = ""
    repo: str = ""

    def to_jsonl(self) -> str:
        return json.dumps(dataclasses.asdict(self), separators=(",", ":"))


# ─────────────────────────────────────────────────────────────────────────────
# Filesystem helpers — JSONL append, locks, corruption recovery
# ─────────────────────────────────────────────────────────────────────────────
@contextlib.contextmanager
def file_lock(lock_path: Path, timeout_s: float = 30.0) -> Iterator[None]:
    """Cross-process flock with timeout. Creates lock file if absent."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
    deadline = time.monotonic() + timeout_s
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as e:
                if e.errno not in (errno.EAGAIN, errno.EACCES):
                    raise
                if time.monotonic() >= deadline:
                    raise P9Error(
                        f"flock timeout after {timeout_s}s on {lock_path}"
                    ) from e
                time.sleep(0.05)
        yield
    finally:
        with contextlib.suppress(OSError):
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def jsonl_append(path: Path, payload: str, lock: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(lock):
        with path.open("a", encoding="utf-8") as f:
            f.write(payload)
            if not payload.endswith("\n"):
                f.write("\n")


def jsonl_read_all(path: Path) -> tuple[list[dict[str, Any]], int]:
    """Read JSONL, skipping the last line if it's a partial/corrupt write.

    Returns (rows, dropped) where dropped is the number of lines we skipped
    (currently 0 or 1).
    """
    if not path.exists():
        return [], 0
    raw = path.read_text(encoding="utf-8")
    if not raw:
        return [], 0
    lines = raw.splitlines()
    rows: list[dict[str, Any]] = []
    dropped = 0
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            # JSONL append-only design: only the last line can be partial.
            # If the corrupt line is not the last, that's an invariant violation.
            if i == len(lines) - 1:
                dropped = 1
            else:
                raise IllegalTransitionError(
                    f"Mid-file JSON corruption in {path} at line {i + 1}"
                )
    return rows, dropped


# ─────────────────────────────────────────────────────────────────────────────
# Policy loader (strict; fail-closed)
# ─────────────────────────────────────────────────────────────────────────────
def _yaml_loader():
    """Lazy-import PyYAML; fall back to a tiny parser for the keys we need."""
    try:
        import yaml  # type: ignore
        return yaml.safe_load
    except ImportError:
        return _minimal_yaml_load


def _minimal_yaml_load(text: str) -> dict[str, Any]:
    """Tiny YAML subset: top-level mappings, nested mappings, scalars,
    inline lists `[a,b]`, and block-style list-of-dicts `- key: val`.

    Sufficient for `.control/policy.yaml` ci_watch / ci_heal / auto_merge
    blocks. Not a general YAML parser — intentionally narrow so it fails
    noisily on anything unexpected.
    """
    out: dict[str, Any] = {}
    # stack tracks (indent, dict) frames for nested mappings.
    stack: list[tuple[int, dict[str, Any]]] = [(-1, out)]
    # list_stack tracks (indent, list) frames for active block lists.
    list_stack: list[tuple[int, list[Any]]] = []

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        body = line.strip()

        if body.startswith("- "):
            # block list item; pop deeper frames first
            while list_stack and list_stack[-1][0] >= indent:
                list_stack.pop()
            while stack and stack[-1][0] >= indent:
                stack.pop()
            if not list_stack:
                continue  # orphan list item — ignore
            target_list = list_stack[-1][1]
            inner = body[2:].strip()
            if ":" in inner and not (inner.startswith("[") or inner.startswith('"')):
                # block-style list-of-dicts: `- key: val` starts a new dict
                # and any subsequent more-indented `key: val` lines populate it
                key, _, value_str = inner.partition(":")
                value_str = value_str.strip()
                new_dict: dict[str, Any] = {}
                if value_str:
                    new_dict[key.strip()] = _scalar(value_str)
                target_list.append(new_dict)
                # Subsequent same-indent `- ` items pop this frame; nested
                # `key: val` lines at deeper indent populate new_dict.
                stack.append((indent, new_dict))
            else:
                # scalar list item
                target_list.append(_scalar(inner))
            continue

        if ":" not in body:
            continue
        key, _, value_str = body.partition(":")
        value_str = value_str.strip()
        # Pop deeper frames
        while stack and stack[-1][0] >= indent:
            stack.pop()
        while list_stack and list_stack[-1][0] >= indent:
            list_stack.pop()
        parent = stack[-1][1] if stack else out

        if value_str == "":
            # Mapping or list — we don't know yet. Default to mapping;
            # if the next non-blank line is a `- `, the open list_stack
            # frame below catches it.
            new_map: dict[str, Any] = {}
            new_list: list[Any] = []
            parent[key.strip()] = new_map
            stack.append((indent, new_map))
            # Tentatively register a list at deeper indent; whichever
            # the next line uses (mapping vs list) wins via stack pop.
            # We need a sentinel: register the list only if the next
            # `-` arrives at deeper indent. Easiest: pre-register both
            # but only commit to one once content arrives.
            # Concretely: replace mapping with list lazily on first `-`.
            list_stack.append((indent, new_list))
            # If the next content is a `- ` deeper than `indent`, we'll
            # convert: replace parent[key] with new_list and pop the dict.
            stack[-1] = (indent, new_map)
            # Stash a reference so a `- ` line can swap mapping → list
            new_map.setdefault("__p9_yaml_pending_list_holder__",
                               (parent, key.strip(), new_list))
        elif value_str.startswith("[") and value_str.endswith("]"):
            inner = value_str[1:-1].strip()
            parent[key.strip()] = (
                [_scalar(p.strip()) for p in inner.split(",") if p.strip()]
                if inner else []
            )
        else:
            parent[key.strip()] = _scalar(value_str)

    # Second pass: any dict that still holds the pending-list sentinel
    # AND has no other keys is actually an empty dict; any dict whose
    # corresponding list got populated had its mapping replaced.
    _resolve_pending_lists(out)
    return out


def _resolve_pending_lists(node: Any) -> None:
    """Walk the parsed tree; convert mapping→list where a `-` block was
    used. Sentinel removal must come before semantic validation."""
    if isinstance(node, dict):
        sentinel_key = "__p9_yaml_pending_list_holder__"
        if sentinel_key in node:
            holder = node[sentinel_key]
            del node[sentinel_key]
            parent, key, the_list = holder
            if the_list:
                # `-` lines populated the list; replace mapping with list
                parent[key] = the_list
        for v in list(node.values()):
            _resolve_pending_lists(v)
    elif isinstance(node, list):
        for item in node:
            _resolve_pending_lists(item)


def _scalar(s: str) -> Any:
    s = s.strip().strip('"').strip("'")
    if s.lower() == "true":
        return True
    if s.lower() == "false":
        return False
    if s.lower() in ("null", "none", "~"):
        return None
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


def load_policy(path: Path | str | None = None) -> PolicyConfig:
    """Load .control/policy.yaml. **Fail-closed** on missing/malformed blocks.

    Accepts both `Path` and `str` (str is coerced — historic callers were
    inconsistent). None falls back to `policy_yaml_path()`.
    """
    p = Path(path) if path is not None else policy_yaml_path()
    if not p.exists():
        raise PolicyError(f"policy.yaml not found at {p}")
    try:
        loader = _yaml_loader()
        data = loader(p.read_text(encoding="utf-8"))
    except Exception as e:
        raise PolicyError(f"policy.yaml malformed: {e}") from e
    if not isinstance(data, dict):
        raise PolicyError("policy.yaml must be a mapping at the top level")
    if "ci_watch" not in data:
        raise PolicyError("policy.yaml missing required block: ci_watch")
    if "ci_heal" not in data:
        raise PolicyError("policy.yaml missing required block: ci_heal")
    return _parse_policy(data)


def _parse_policy(data: dict[str, Any]) -> PolicyConfig:
    cw_raw = data.get("ci_watch") or {}
    ch_raw = data.get("ci_heal") or {}
    iso_raw = cw_raw.get("isolation_tier_map") or {}
    esc_raw = ch_raw.get("escalation_channel") or {}
    types_raw = ch_raw.get("classified_failure_types") or ()
    if not isinstance(types_raw, (list, tuple)):
        raise PolicyError("ci_heal.classified_failure_types must be a list")
    return PolicyConfig(
        ci_watch=CIWatchPolicy(
            enabled=bool(cw_raw.get("enabled", True)),
            max_concurrent_prs=int(cw_raw.get("max_concurrent_prs", 1)),
            isolation_tier_map=IsolationTierMap(
                research=str(iso_raw.get("research", "none")),
                docs=str(iso_raw.get("docs", "none")),
                code_independent=str(iso_raw.get("code_independent", "worktree")),
                code_dependent=str(iso_raw.get("code_dependent", "stacked_branch")),
                governance=str(iso_raw.get("governance", "blocked")),
            ),
        ),
        ci_heal=CIHealPolicy(
            enabled=bool(ch_raw.get("enabled", True)),
            max_attempts=int(ch_raw.get("max_attempts", 5)),
            stability_floor=float(ch_raw.get("stability_floor", 0.3)),
            classified_failure_types=tuple(str(t) for t in types_raw),
            escalation_channel=EscalationChannel(
                linear_team=str(esc_raw.get("linear_team", "BRO")),
                linear_label=str(esc_raw.get("linear_label", "ci-heal-escalation")),
                notify_hook=str(
                    esc_raw.get(
                        "notify_hook",
                        "skills/p9/scripts/p9-escalate-notify.sh",
                    )
                ),
            ),
        ),
        auto_merge=_parse_auto_merge(data.get("auto_merge")),
    )


_AUTO_MERGE_ACTIONS = ("auto", "require_human", "notify")


def _parse_auto_merge(raw: Any) -> AutoMergePolicy:
    """Parse the optional auto_merge: block. Absence is *not* an error —
    auto-merge is opt-in; missing block defaults to disabled (fail-safe)."""
    if raw is None:
        return AutoMergePolicy()
    if not isinstance(raw, dict):
        raise PolicyError("auto_merge must be a mapping if present")
    rules_raw = raw.get("rules") or []
    if not isinstance(rules_raw, list):
        raise PolicyError("auto_merge.rules must be a list")
    rules: list[AutoMergeRule] = []
    for i, r in enumerate(rules_raw):
        if not isinstance(r, dict):
            raise PolicyError(f"auto_merge.rules[{i}] must be a mapping")
        action = str(r.get("action", "notify"))
        if action not in _AUTO_MERGE_ACTIONS:
            raise PolicyError(
                f"auto_merge.rules[{i}].action must be one of {_AUTO_MERGE_ACTIONS}, "
                f"got {action!r}"
            )
        bp = r.get("branch_pattern")
        pt = r.get("path_touched")
        if bp and pt:
            raise PolicyError(
                f"auto_merge.rules[{i}] cannot set both branch_pattern and path_touched"
            )
        if not bp and not pt:
            raise PolicyError(
                f"auto_merge.rules[{i}] must set either branch_pattern or path_touched"
            )
        rules.append(AutoMergeRule(
            branch_pattern=str(bp) if bp else None,
            path_touched=str(pt) if pt else None,
            action=action,
        ))
    default = str(raw.get("default_action", "notify"))
    if default not in _AUTO_MERGE_ACTIONS:
        raise PolicyError(
            f"auto_merge.default_action must be one of {_AUTO_MERGE_ACTIONS}, "
            f"got {default!r}"
        )
    method = str(raw.get("merge_method", "squash"))
    if method not in ("squash", "merge", "rebase"):
        raise PolicyError(
            f"auto_merge.merge_method must be squash|merge|rebase, got {method!r}"
        )
    return AutoMergePolicy(
        enabled=bool(raw.get("enabled", False)),
        require_no_requested_changes=bool(raw.get("require_no_requested_changes", True)),
        require_branch_up_to_date=bool(raw.get("require_branch_up_to_date", True)),
        merge_method=method,
        delete_branch=bool(raw.get("delete_branch", True)),
        rules=tuple(rules),
        default_action=default,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Auto-merge matcher
# ─────────────────────────────────────────────────────────────────────────────
import fnmatch  # noqa: E402  (kept near use site for clarity)


def match_auto_merge_action(
    policy: AutoMergePolicy,
    *,
    branch: str,
    paths_touched: Iterable[str],
) -> tuple[str, str]:
    """First-match-wins evaluator. Returns (action, reason).

    Path rules are evaluated FIRST regardless of order — a path-touched
    `require_human` rule (e.g. CLAUDE.md) is a hard block that cannot be
    overridden by a later branch rule. This implements the "governance
    paths always block" invariant from the original brainstorming.
    """
    paths = list(paths_touched)

    # Pass 1: any path rule with require_human is a hard block.
    for rule in policy.rules:
        if rule.path_touched and rule.action == "require_human":
            for p in paths:
                if rule.path_touched in p:
                    return ("require_human",
                            f"path rule blocks: {rule.path_touched!r} in {p}")

    # Pass 2: first match wins (path or branch).
    for rule in policy.rules:
        if rule.path_touched:
            for p in paths:
                if rule.path_touched in p:
                    return (rule.action,
                            f"path rule matched: {rule.path_touched!r} in {p}")
        if rule.branch_pattern and fnmatch.fnmatch(branch, rule.branch_pattern):
            return (rule.action, f"branch rule matched: {rule.branch_pattern!r}")

    return (policy.default_action, "no rule matched; using default_action")


# ─────────────────────────────────────────────────────────────────────────────
# Failure classifier (rubric-driven regex matcher)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class RubricEntry:
    failure_type: str
    patterns: tuple[re.Pattern[str], ...]
    heal_command: str | None      # None => escalate (cannot auto-fix)
    confidence_floor: float = 0.7  # below this, drop to "unclassified"


def _builtin_rubric() -> tuple[RubricEntry, ...]:
    """Default rubric. Mirrors references/scoring-rubric.md.

    Rubric markdown is the authoritative source for humans; this constant is
    the authoritative source for code. Tests assert the two stay in sync.
    """
    return (
        RubricEntry(
            failure_type="lint",
            patterns=(
                re.compile(r"biome\s+(check|lint).*(found|error)", re.IGNORECASE),
                re.compile(r"eslint.*\d+\s+(error|problem)", re.IGNORECASE),
                re.compile(r"clippy.*::error", re.IGNORECASE),
                re.compile(r"::error.*lint", re.IGNORECASE),
            ),
            heal_command="bun run lint:fix",
        ),
        RubricEntry(
            failure_type="format",
            patterns=(
                re.compile(r"prettier.*--check.*would reformat", re.IGNORECASE),
                re.compile(r"rustfmt.*Diff in", re.IGNORECASE),
                re.compile(r"would reformat", re.IGNORECASE),
            ),
            heal_command="bun run format",
        ),
        RubricEntry(
            failure_type="type",
            patterns=(
                re.compile(r"\berror TS\d+\b"),
                re.compile(r"\berror\[E\d+\]"),
                re.compile(r"type error.*at\s+[\w./]+:\d+", re.IGNORECASE),
            ),
            heal_command=None,  # escalate — type errors need human reasoning
        ),
        RubricEntry(
            failure_type="test_flaky",
            patterns=(
                # Detected by signature-history rather than text — see
                # classify_with_history. The pattern below matches generic
                # test failure for fallback recognition only.
                re.compile(r"^\s*FAIL\s+", re.MULTILINE),
            ),
            heal_command="gh run rerun --failed",
            confidence_floor=0.9,  # only confident if history confirms flakiness
        ),
        RubricEntry(
            failure_type="codegen_drift",
            patterns=(
                re.compile(r"(generated|codegen).*(out of (date|sync)|stale)", re.IGNORECASE),
                re.compile(r"schema mismatch", re.IGNORECASE),
                re.compile(r"graphql codegen.*diff", re.IGNORECASE),
            ),
            heal_command="bun run codegen",
        ),
        RubricEntry(
            failure_type="import_missing",
            patterns=(
                re.compile(r"Cannot find module ['\"]([^'\"]+)['\"]", re.IGNORECASE),
                re.compile(r"unresolved import\s+`([^`]+)`", re.IGNORECASE),
                re.compile(r"Module not found", re.IGNORECASE),
            ),
            heal_command=None,  # complex — escalate v1
        ),
    )


def _signature_hash(log: str) -> str:
    """Stable signature for a failure log: first error-ish line, normalized."""
    candidates = [
        ln for ln in log.splitlines()
        if re.search(r"\b(error|FAIL|fatal)\b", ln, re.IGNORECASE)
    ]
    src = candidates[0] if candidates else log[:200]
    norm = re.sub(r"\s+", " ", src).strip()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


def classify(
    log: str,
    rubric: tuple[RubricEntry, ...] | None = None,
) -> ClassifierResult:
    """Pure classifier: regex match against the rubric.

    Returns the best match. If best confidence < that entry's floor, returns
    an `unclassified` result (which the caller must treat as `escalate`).
    """
    rubric = rubric or _builtin_rubric()
    best: tuple[RubricEntry, float] | None = None
    for entry in rubric:
        score = _entry_score(entry, log)
        if score == 0.0:
            continue
        if best is None or score > best[1]:
            best = (entry, score)
    sig = _signature_hash(log)
    if best is None or best[1] < best[0].confidence_floor:
        return ClassifierResult(
            failure_type="unclassified",
            classified=False,
            confidence=best[1] if best else 0.0,
            heal_command=None,
            signature_hash=sig,
            rationale=(
                f"no rubric entry above floor (best={best[0].failure_type}@{best[1]:.2f})"
                if best else "no rubric pattern matched"
            ),
        )
    entry, conf = best
    return ClassifierResult(
        failure_type=entry.failure_type,
        classified=entry.heal_command is not None,
        confidence=conf,
        heal_command=entry.heal_command,
        signature_hash=sig,
        rationale=f"matched {entry.failure_type} at confidence {conf:.2f}",
    )


def _entry_score(entry: RubricEntry, log: str) -> float:
    """How well does this rubric entry match? 0.0–1.0."""
    matched = sum(1 for p in entry.patterns if p.search(log))
    if matched == 0:
        return 0.0
    # Scale by fraction of patterns hit, then cap at 1.0. Multi-pattern hits
    # boost confidence; single-pattern hits sit at ~0.7 — exactly the default
    # confidence_floor, so single-pattern matches *just* qualify.
    base = 0.7 + 0.1 * (matched - 1)
    return min(base, 1.0)


# ─────────────────────────────────────────────────────────────────────────────
# Evaluator (progress-score brain)
# ─────────────────────────────────────────────────────────────────────────────
def evaluate(
    *,
    attempt: int,
    max_attempts: int,
    classifier_confidence: float,
    prev_signature: str | None,
    curr_signature: str,
    prev_failure_count: int | None,
    curr_failure_count: int,
    stability_floor: float,
) -> EvaluatorResult:
    """Compute progress_score per spec §6.3.

    progress_score =
       0.4 × signature_changed?   +
       0.3 × failures_decreased?  +
       0.2 × (1 - attempt/max)    +
       0.1 × classifier_confidence
    """
    sig_changed = prev_signature is not None and curr_signature != prev_signature
    failures_dec = (
        prev_failure_count is not None and curr_failure_count < prev_failure_count
    )
    budget = max(0.0, 1.0 - (attempt / max(1, max_attempts)))
    score = (
        0.4 * (1.0 if sig_changed else 0.0)
        + 0.3 * (1.0 if failures_dec else 0.0)
        + 0.2 * budget
        + 0.1 * classifier_confidence
    )
    return EvaluatorResult(
        progress_score=round(score, 4),
        signature_changed=sig_changed,
        failures_decreased=failures_dec,
        budget_remaining=round(budget, 4),
        classifier_confidence=classifier_confidence,
        stalled=score < stability_floor,
    )


def stalled_for_two_cycles(
    history: Iterable[float], stability_floor: float
) -> bool:
    """True iff the last two evaluator scores are both below floor."""
    last_two = list(history)[-2:]
    return len(last_two) >= 2 and all(s < stability_floor for s in last_two)


# ─────────────────────────────────────────────────────────────────────────────
# Wait queue
# ─────────────────────────────────────────────────────────────────────────────
def _validate_source(source: str) -> str:
    if source not in _QUEUE_PRIORITY:
        raise P9Error(
            f"invalid source '{source}'; must be one of {_QUEUE_PRIORITY}"
        )
    return source


# Sentinel: "resolve to the current session at call time". Distinct from
# None (which means "no scoping / all sessions").
_CURRENT_SESSION = object()


def _resolve_scope(session_id: Any, all_sessions: bool) -> str | None:
    """Map the (session_id, all_sessions) arg pair to a concrete filter:
    a session-id string to filter by, or None for the global view."""
    if all_sessions:
        return None
    if session_id is _CURRENT_SESSION:
        return current_session_id()
    return session_id


def _queue_ttl_seconds() -> float:
    """Wait-queue item TTL. Overridable via BROOMVA_P9_QUEUE_TTL_DAYS
    (default 14 days). 0 disables age-based pruning."""
    raw = os.environ.get("BROOMVA_P9_QUEUE_TTL_DAYS", "14")
    try:
        days = float(raw)
    except ValueError:
        days = 14.0
    return max(0.0, days) * 86400.0


def _iso_age_seconds(ts: str) -> float:
    try:
        when = _dt.datetime.fromisoformat(ts)
    except ValueError:
        return 0.0  # unparseable → treat as fresh (never auto-prune)
    if when.tzinfo is None:
        when = when.replace(tzinfo=_dt.timezone.utc)
    return (_dt.datetime.now(_dt.timezone.utc) - when).total_seconds()


def _item_is_stale(it: WaitQueueItem) -> bool:
    """A queue item is stale (eligible for pruning) when it has aged past
    the TTL, or its owning PR has reached a terminal state — the wait it was
    queued behind is over, so the work is moot."""
    ttl = _queue_ttl_seconds()
    if ttl > 0 and _iso_age_seconds(it.created_at) > ttl:
        return True
    # Terminal-PR pruning requires a KNOWN repo: identity is (repo, pr), so an
    # item with no repo can't be disambiguated from a same-numbered PR in
    # another repo. Such items fall back to TTL-only pruning.
    if it.pr is not None and it.repo:
        st = current_pr_state(it.pr, it.repo)
        if st is not None and is_terminal(st):
            return True
    return False


def _item_visible(it: WaitQueueItem, scope: str | None) -> bool:
    """Visible in a session's view when un-scoped global view (scope None),
    owned by the session, or legacy-unowned ("" — drained by whoever pops)."""
    if scope is None:
        return True
    return it.session_id in ("", scope)


def queue_push(item: str, source: str, *, pr: int | None = None,
               isolation_tier: str = "none", session_id: str | None = None,
               repo: str = "") -> WaitQueueItem:
    src = _validate_source(source)
    entry = WaitQueueItem(
        id=uuid.uuid4().hex[:12],
        source=src,
        item=item,
        created_at=_utcnow(),
        pr=pr,
        isolation_tier=isolation_tier,
        session_id=session_id if session_id is not None else current_session_id(),
        repo=repo or "",
    )
    jsonl_append(wait_queue_jsonl(), entry.to_jsonl(), queue_lock_path())
    return entry


def queue_list(session_id: Any = _CURRENT_SESSION, *,
               all_sessions: bool = False,
               include_stale: bool = False) -> list[WaitQueueItem]:
    """List queue items in priority order. Defaults to the *current
    session's* view (its own items + legacy-unowned items), excluding stale
    items. ``all_sessions=True`` shows every session's items; ``include_stale``
    keeps terminal-PR / aged-out items."""
    scope = _resolve_scope(session_id, all_sessions)
    rows, _ = jsonl_read_all(wait_queue_jsonl())
    items = [WaitQueueItem(**r) for r in rows]
    items = [it for it in items if _item_visible(it, scope)]
    if not include_stale:
        items = [it for it in items if not _item_is_stale(it)]
    items.sort(key=lambda it: (_QUEUE_PRIORITY.index(it.source), it.created_at))
    return items


def queue_pop(session_id: Any = _CURRENT_SESSION, *,
              all_sessions: bool = False) -> WaitQueueItem | None:
    """Atomic, scope-aware pop. Returns the highest-priority *in-scope,
    non-stale* item and removes it. Out-of-scope items (other sessions') are
    preserved on disk; stale items are pruned as a side effect."""
    scope = _resolve_scope(session_id, all_sessions)
    with file_lock(queue_lock_path()):
        rows, _ = jsonl_read_all(wait_queue_jsonl())
        if not rows:
            return None
        eligible: list[WaitQueueItem] = []
        retained: list[WaitQueueItem] = []   # out-of-scope, keep on disk
        for r in rows:
            it = WaitQueueItem(**r)
            if _item_is_stale(it):
                continue  # prune from disk regardless of scope
            if _item_visible(it, scope):
                eligible.append(it)
            else:
                retained.append(it)
        if not eligible:
            # Persist the prune of stale items even when nothing pops.
            wait_queue_jsonl().write_text(
                "".join(it.to_jsonl() + "\n" for it in retained), encoding="utf-8",
            )
            return None
        eligible.sort(key=lambda it: (_QUEUE_PRIORITY.index(it.source), it.created_at))
        head, *rest = eligible
        wait_queue_jsonl().write_text(
            "".join(it.to_jsonl() + "\n" for it in (retained + rest)),
            encoding="utf-8",
        )
        return head


def queue_clear(session_id: Any = _CURRENT_SESSION, *,
                all_sessions: bool = False) -> int:
    """Clear queue items. Defaults to the current session's *own* items
    (exact-owner match — legacy-unowned items are preserved unless
    ``all_sessions=True``). Returns the number removed."""
    scope = _resolve_scope(session_id, all_sessions)
    with file_lock(queue_lock_path()):
        if not wait_queue_jsonl().exists():
            return 0
        rows, _ = jsonl_read_all(wait_queue_jsonl())
        items = [WaitQueueItem(**r) for r in rows]
        if scope is None:
            wait_queue_jsonl().write_text("", encoding="utf-8")
            return len(items)
        keep = [it for it in items if it.session_id != scope]
        removed = len(items) - len(keep)
        wait_queue_jsonl().write_text(
            "".join(it.to_jsonl() + "\n" for it in keep), encoding="utf-8",
        )
        return removed


# ─────────────────────────────────────────────────────────────────────────────
# State store
# ─────────────────────────────────────────────────────────────────────────────
def _utcnow() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def append_state_event(event: PRStateEvent) -> None:
    assert_legal_transition(PRState(event.from_state), PRState(event.to_state))
    jsonl_append(state_jsonl(), event.to_jsonl(), state_lock_path())


def current_pr_state(pr: int, repo: str | None = None) -> PRState | None:
    """Latest state for a PR. When ``repo`` is given, identity is the
    composite ``(repo, pr)`` — so the same PR number in two repos never
    resolves to each other's state. ``repo=None`` keeps the legacy
    match-by-number behavior for callers that don't know the repo."""
    rows, _ = jsonl_read_all(state_jsonl())
    last: PRState | None = None
    for r in rows:
        if r.get("pr") != pr:
            continue
        if repo is not None and r.get("repo", "") != repo:
            continue
        last = PRState(r["to_state"])
    return last


def latest_row(pr: int, repo: str | None = None) -> dict[str, Any] | None:
    """The most recent raw event row for a PR (composite ``(repo, pr)`` when
    repo is given). Used for watcher de-dup — we need the pid + state, not
    just the state."""
    rows, _ = jsonl_read_all(state_jsonl())
    last: dict[str, Any] | None = None
    for r in rows:
        if r.get("pr") != pr:
            continue
        if repo is not None and r.get("repo", "") != repo:
            continue
        last = r
    return last


def open_prs(session_id: str | None = None) -> list[dict[str, Any]]:
    """All PRs that haven't reached a terminal state.

    Keyed by ``(repo, pr)`` so the same PR number in two repos never
    collides (the bare-number keying clobbered cross-repo state).

    When ``session_id`` is given, only rows owned by that session are
    returned — this is what makes the concurrency ceiling *per-session*
    instead of one global merge-train. ``session_id=None`` returns the
    global view (``status`` / ``cleanup`` / ``reap`` / legacy callers).
    Legacy rows (no ``session_id``) belong to no session, so they never
    count against a real session's ceiling — they are drained by ``reap``.
    """
    rows, _ = jsonl_read_all(state_jsonl())
    seen: dict[tuple[str, int], dict[str, Any]] = {}
    for r in rows:
        seen[(r.get("repo", ""), r["pr"])] = r
    out: list[dict[str, Any]] = []
    for r in seen.values():
        if is_terminal(PRState(r["to_state"])):
            continue
        if session_id is not None and r.get("session_id", "") != session_id:
            continue
        out.append(r)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Watcher manager (subprocess control for `gh pr checks --watch`)
# ─────────────────────────────────────────────────────────────────────────────
def spawn_watcher(pr: int, repo: str | None = None,
                  *, dry_run: bool = False) -> subprocess.Popen[bytes] | None:
    """Spawn `gh pr checks <pr> --watch` detached. Returns the Popen or None
    in dry_run mode (used by tests and `--background --dry-run`)."""
    if dry_run:
        return None
    cmd = ["gh", "pr", "checks", str(pr), "--watch"]
    if repo:
        cmd += ["--repo", repo]
    return subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def is_watcher_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _watcher_grace_seconds() -> float:
    """How long a WATCHING/HEALING row is protected from reaping after its
    last event. Covers the window where the watcher pid is gone but the fold
    event may still be landing. Override via BROOMVA_P9_WATCHER_GRACE."""
    raw = os.environ.get("BROOMVA_P9_WATCHER_GRACE", "120")
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 120.0


def _row_pid(row: dict[str, Any]) -> int:
    try:
        return int((row.get("extra") or {}).get("pid", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _reconcile_dead_watcher(pr: int, repo: str, reconcile: bool) -> tuple[PRState, str]:
    """Decide the terminal state for a dead-watcher row. Always ABANDONED
    (frees the concurrency slot; a fresh `p9 watch` re-opens the PR since
    `cmd_watch` always starts a new PUSHED→WATCHING edge). When ``reconcile``
    and a repo is known, query GitHub only to enrich the reason."""
    if not reconcile or not repo:
        return PRState.ABANDONED, "watcher process gone (no gh reconcile)"
    cmd = ["gh", "pr", "view", str(pr), "--json", "state,mergedAt", "--repo", repo]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return PRState.ABANDONED, "watcher gone; gh unavailable"
    if out.returncode != 0:
        return PRState.ABANDONED, "watcher gone; gh query failed"
    try:
        gh_state = (json.loads(out.stdout).get("state") or "").upper()
    except json.JSONDecodeError:
        return PRState.ABANDONED, "watcher gone; gh returned non-JSON"
    if gh_state in ("MERGED", "CLOSED"):
        return PRState.ABANDONED, f"watcher gone; PR {gh_state.lower()} on GitHub"
    return (PRState.ABANDONED,
            "watcher gone; PR still OPEN — re-watch with `p9 watch <pr> --adopt`")


def reap_stale_watchers(*, grace_seconds: float | None = None,
                        reconcile: bool = False,
                        session_id: str | None = None) -> list[dict[str, Any]]:
    """Reconcile WATCHING/HEALING rows whose watcher process is dead and that
    have aged past the grace window. Without this, a crashed or closed session
    leaves a row that permanently consumes a concurrency slot (the gap that
    made parallel sessions collide on `max_concurrent_prs`).

    Liveness-only by default (`reconcile=False`, no network) so it is cheap
    enough to run as a preflight inside `watch`/`status`. `session_id` limits
    reaping to one session's rows (preflight passes the live session so a
    long-running watch never reaps another session's healthy row by mistake);
    None scans all rows (the standalone `p9 reap`)."""
    grace = _watcher_grace_seconds() if grace_seconds is None else grace_seconds
    reaped: list[dict[str, Any]] = []
    for row in open_prs(session_id=session_id):
        state = PRState(row["to_state"])
        if state not in (PRState.WATCHING, PRState.HEALING):
            continue
        pid = _row_pid(row)
        if pid > 0 and is_watcher_alive(pid):
            continue  # healthy watcher — leave it
        if _iso_age_seconds(row.get("ts", "")) < grace:
            continue  # too fresh — the fold may still land
        repo = row.get("repo") or ""
        pr = row["pr"]
        to_state, reason = _reconcile_dead_watcher(pr, repo, reconcile)
        append_state_event(PRStateEvent(
            ts=_utcnow(), pr=pr, repo=repo,
            from_state=state.value, to_state=to_state.value,
            watcher_id="reap", session_id=row.get("session_id", ""),
            extra={"reason": reason, "dead_pid": pid},
        ))
        enriched = dict(row)
        enriched.update(to_state=to_state.value, reason=reason)
        reaped.append(enriched)
    return reaped


# ─────────────────────────────────────────────────────────────────────────────
# Concurrency
# ─────────────────────────────────────────────────────────────────────────────
def enforce_concurrency_ceiling(
    policy: PolicyConfig, session_id: str | None = None
) -> None:
    """Enforce ``max_concurrent_prs``.

    With ``session_id`` set (production: ``cmd_watch`` passes the live
    session), the count is scoped to that session — N parallel agents can
    each hold their own watcher. ``session_id=None`` keeps the global count
    (direct/legacy callers and tests)."""
    open_count = len(open_prs(session_id=session_id))
    if open_count >= policy.ci_watch.max_concurrent_prs:
        scope = f" for session {session_id}" if session_id else ""
        raise ConcurrencyCeilingError(
            f"max_concurrent_prs={policy.ci_watch.max_concurrent_prs} "
            f"already in flight ({open_count} open{scope})"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Subcommand handlers
# ─────────────────────────────────────────────────────────────────────────────
def cmd_doctor(_args: argparse.Namespace) -> int:
    problems: list[str] = []
    # 1. gh present + authed
    try:
        out = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if out.returncode != 0:
            problems.append(f"gh auth status non-zero: {out.stderr.strip()[:200]}")
    except FileNotFoundError:
        problems.append("gh CLI not installed")
    except subprocess.TimeoutExpired:
        problems.append("gh auth status timed out")

    # 2. State directory writable
    try:
        p9_home().mkdir(parents=True, exist_ok=True)
        probe = p9_home() / ".doctor-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as e:
        problems.append(f"state directory not writable: {e}")

    # 3. Policy blocks present
    try:
        load_policy()
    except PolicyError as e:
        problems.append(f"policy: {e}")

    # 4. Rubric file present (if absent, builtin still works but we warn)
    if not rubric_md_path().exists():
        problems.append(
            f"references/scoring-rubric.md missing at {rubric_md_path()} "
            f"(builtin rubric still available but markdown is the human-canonical source)"
        )

    if not problems:
        print("p9 doctor: ok")
        return EXIT_OK
    print("p9 doctor: degraded")
    for p in problems:
        print(f"  - {p}")
    # Policy errors are exit 2 (fail-closed); other degradations exit 1.
    if any(p.startswith("policy:") for p in problems):
        return EXIT_POLICY_ERROR
    return EXIT_DEGRADED


def cmd_abandon(args: argparse.Namespace) -> int:
    """Mark a PR as ABANDONED.

    Idempotent on already-terminal states. Emits a terminal-state event so
    `max_concurrent_prs` accounting is freed and `p9 cleanup` doesn't
    re-flag it.
    """
    pr = int(args.pr)
    state = current_pr_state(pr)
    if state is None:
        print(f"PR #{pr}: no state to abandon", file=sys.stderr)
        return EXIT_DEGRADED
    if is_terminal(state):
        print(f"PR #{pr}: already terminal ({state.value}); no-op")
        return EXIT_OK
    repo = args.repo or _detect_repo() or ""
    append_state_event(PRStateEvent(
        ts=_utcnow(), pr=pr, repo=repo,
        from_state=state.value,
        to_state=PRState.ABANDONED.value,
        watcher_id="abandon",
        extra={"reason": args.reason or "manual abandon"},
    ))
    print(f"PR #{pr}: {state.value} → ABANDONED")
    return EXIT_OK


def cmd_cleanup(args: argparse.Namespace) -> int:
    """Drain orphan watchers by polling GitHub for each open row's true state.

    For every PR in a non-terminal local state, queries
    `gh pr view --json state,mergedAt`. If GitHub reports MERGED or CLOSED,
    appends a terminal ABANDONED event with the reason. If GitHub reports
    OPEN, leaves the row alone. PRs that fail to query are reported but
    not abandoned (no false-positive cleanup).
    """
    rows = open_prs()
    if not rows:
        print("p9 cleanup: no open PRs")
        return EXIT_OK
    cleaned = 0
    skipped = 0
    for row in rows:
        pr = row["pr"]
        repo = row.get("repo") or _detect_repo() or ""
        cmd = ["gh", "pr", "view", str(pr), "--json", "state,mergedAt"]
        if repo:
            cmd += ["--repo", repo]
        result = subprocess.run(cmd, capture_output=True, text=True,
                                timeout=30, check=False)
        if result.returncode != 0:
            print(f"  #{pr}: cannot query gh; leaving as {row['to_state']} "
                  f"({result.stderr.strip()[:80]})")
            skipped += 1
            continue
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            print(f"  #{pr}: gh returned non-JSON; leaving as {row['to_state']}")
            skipped += 1
            continue
        gh_state = (data.get("state") or "").upper()
        from_state = PRState(row["to_state"])
        if gh_state in ("MERGED", "CLOSED"):
            reason = ("merged outside p9" if gh_state == "MERGED"
                      else "closed outside p9")
            append_state_event(PRStateEvent(
                ts=_utcnow(), pr=pr, repo=repo,
                from_state=from_state.value,
                to_state=PRState.ABANDONED.value,
                watcher_id="cleanup",
                extra={"reason": reason, "gh_state": gh_state},
            ))
            print(f"  #{pr}: {from_state.value} → ABANDONED ({reason})")
            cleaned += 1
        else:
            print(f"  #{pr}: still OPEN; leaving as {from_state.value}")
    print(f"p9 cleanup: drained {cleaned}, skipped {skipped}")
    return EXIT_OK


def cmd_auto_merge(args: argparse.Namespace) -> int:
    """Auto-merge actuator. Closes the gap between MERGE_READY signal and
    actual `gh pr merge` execution.

    Flow:
      1. Load policy → bail if auto_merge.enabled is false.
      2. Verify PR is in MERGE_READY state.
      3. Fetch branch + touched paths via `gh pr view`.
      4. Match against policy rules → action ∈ {auto, require_human, notify}.
      5. auto → run `gh pr merge` (or print plan in --dry-run mode), transition
         MERGE_READY → MERGED, return 0.
         require_human / notify → idempotent self-transition with extra payload
         indicating block reason, return 7 (EXIT_AUTO_MERGE_BLOCKED).
    """
    pr = int(args.pr)
    repo = args.repo or _detect_repo() or ""
    policy = load_policy()
    if not policy.auto_merge.enabled:
        print("auto_merge.enabled=false in policy; refusing to merge", file=sys.stderr)
        return EXIT_POLICY_ERROR

    state = current_pr_state(pr)
    if state != PRState.MERGE_READY:
        print(
            f"PR #{pr} not in MERGE_READY (current={state.value if state else 'UNKNOWN'}); "
            f"call `p9 merge-ready` first",
            file=sys.stderr,
        )
        return EXIT_DEGRADED

    branch, paths = _gh_pr_branch_and_paths(pr, repo)
    action, reason = match_auto_merge_action(
        policy.auto_merge, branch=branch, paths_touched=paths,
    )

    if action != "auto":
        # Block: emit idempotent state event with rationale; never merge.
        append_state_event(PRStateEvent(
            ts=_utcnow(),
            pr=pr, repo=repo,
            from_state=PRState.MERGE_READY.value,
            to_state=PRState.MERGE_READY.value,
            watcher_id="auto-merge",
            extra={"auto_merge": {"action": action, "reason": reason,
                                  "branch": branch, "paths": list(paths)[:20]}},
        ))
        print(f"auto-merge blocked: action={action}; reason={reason}",
              file=sys.stderr)
        return EXIT_AUTO_MERGE_BLOCKED

    # Auto path
    if args.dry_run:
        print(f"auto-merge dry-run: would merge PR #{pr} ({branch}) via "
              f"`gh pr merge --{policy.auto_merge.merge_method}`")
        return EXIT_OK

    rc = _gh_pr_merge(
        pr, repo,
        method=policy.auto_merge.merge_method,
        delete_branch=policy.auto_merge.delete_branch,
    )
    if rc != 0:
        print(f"gh pr merge exited {rc}; PR not merged", file=sys.stderr)
        return EXIT_EXTERNAL_ERROR

    append_state_event(PRStateEvent(
        ts=_utcnow(),
        pr=pr, repo=repo,
        from_state=PRState.MERGE_READY.value,
        to_state=PRState.MERGED.value,
        watcher_id="auto-merge",
        extra={"auto_merge": {"action": "auto", "reason": reason,
                              "branch": branch,
                              "method": policy.auto_merge.merge_method}},
    ))
    print(f"auto-merge: PR #{pr} merged ({branch})")
    return EXIT_OK


def _gh_pr_branch_and_paths(pr: int, repo: str) -> tuple[str, list[str]]:
    """Return (head_branch, [files_touched]) for a PR via `gh pr view`."""
    cmd = ["gh", "pr", "view", str(pr),
           "--json", "headRefName,files",
           "-q", '{branch: .headRefName, files: [.files[].path]}']
    if repo:
        cmd += ["--repo", repo]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
    if out.returncode != 0:
        raise P9Error(f"gh pr view failed: {out.stderr.strip()[:200]}")
    try:
        data = json.loads(out.stdout)
    except json.JSONDecodeError as e:
        raise P9Error(f"gh pr view returned non-JSON: {e}") from e
    return str(data.get("branch", "")), list(data.get("files") or [])


def _gh_pr_merge(pr: int, repo: str, *, method: str, delete_branch: bool) -> int:
    """Invoke `gh pr merge` with the configured method. Returns exit code."""
    cmd = ["gh", "pr", "merge", str(pr), f"--{method}"]
    if delete_branch:
        cmd.append("--delete-branch")
    if repo:
        cmd += ["--repo", repo]
    return subprocess.run(cmd, check=False).returncode


def cmd_conformance(args: argparse.Namespace) -> int:
    """Run the full pytest battery (unit + integration + chaos).

    Used as the CI-lane validator and as a local pre-merge check. Honors
    BROOMVA_P9_PYTEST env var (default: `python3 -m pytest`) so callers can
    pin a specific interpreter or test runner.
    """
    runner = os.environ.get("BROOMVA_P9_PYTEST", f"{sys.executable} -m pytest")
    tests_dir = Path(__file__).resolve().parent.parent / "tests"
    if not tests_dir.exists():
        print(f"p9 conformance: tests directory not found at {tests_dir}",
              file=sys.stderr)
        return EXIT_DEGRADED
    cmd = runner.split() + [str(tests_dir)]
    if args.verbose:
        cmd.append("-v")
    if args.k:
        cmd += ["-k", args.k]
    print(f"p9 conformance: running {' '.join(cmd)}")
    rc = subprocess.run(cmd, check=False).returncode
    if rc == 0:
        print("p9 conformance: ok")
        return EXIT_OK
    print(f"p9 conformance: failed (pytest exit {rc})", file=sys.stderr)
    return EXIT_DEGRADED


def cmd_watch(args: argparse.Namespace) -> int:
    """Watch CI on a PR.

    Default behavior (PR E onwards): foreground — block on
    `gh pr checks --watch`, then fold the subprocess exit code into a state
    transition (WATCHING → GREEN on exit 0, WATCHING → RED_UNCLASSIFIED
    otherwise). Callers (the agent) wrap this in `run_in_background` so the
    bg-task notification fires when the *whole* watch+fold has finished —
    which is what the cardinal protocol actually wants.

    --detach reverts to the old fire-and-forget behavior (no fold; the
    caller is responsible for polling state). --background and --block are
    aliases for the default; they exist so historic AGENTS.md guidance
    using `p9 watch <pr> --background` keeps working.
    """
    policy = load_policy()
    if not policy.ci_watch.enabled:
        print("ci_watch.enabled=false in policy; refusing to watch", file=sys.stderr)
        return EXIT_POLICY_ERROR
    sid = current_session_id()
    pr = int(args.pr)
    repo = args.repo or _detect_repo()

    # Preflight: reap *this session's* dead-watcher rows so a prior crashed
    # watch doesn't permanently consume the slot we're about to claim.
    reap_stale_watchers(reconcile=False, session_id=sid)

    # De-dup: refuse to stack a second watcher on a PR that already has one,
    # unless it is provably dead (orphan recovery) or the caller overrides.
    adopt = bool(getattr(args, "adopt", False))
    force = bool(getattr(args, "force", False))
    existing = latest_row(pr, repo)
    if existing and PRState(existing["to_state"]) in (PRState.WATCHING, PRState.HEALING):
        epid = _row_pid(existing)
        alive = epid > 0 and is_watcher_alive(epid)
        fresh = _iso_age_seconds(existing.get("ts", "")) < _watcher_grace_seconds()
        if alive and not force:
            print(
                f"PR #{pr} already has a live watcher (pid={epid}, "
                f"session={existing.get('session_id', '') or 'legacy'}). "
                f"Refusing to double-watch; pass --force to supersede.",
                file=sys.stderr,
            )
            return EXIT_DEGRADED
        if not alive and fresh and not (adopt or force):
            print(
                f"PR #{pr} watcher pid={epid} is gone but the row is fresh "
                f"(<{int(_watcher_grace_seconds())}s); the fold may still land. "
                f"Re-run with --adopt to supersede now.",
                file=sys.stderr,
            )
            return EXIT_DEGRADED
        # Supersede the stale/forced row to free the slot before re-watching.
        append_state_event(PRStateEvent(
            ts=_utcnow(), pr=pr, repo=repo or "",
            from_state=existing["to_state"], to_state=PRState.ABANDONED.value,
            watcher_id="watch-supersede", session_id=existing.get("session_id", ""),
            extra={"reason": "superseded by re-watch",
                   "dead_pid": epid, "forced": force, "adopt": adopt},
        ))

    enforce_concurrency_ceiling(policy, session_id=sid)
    watcher_id = uuid.uuid4().hex[:12]
    proc = spawn_watcher(pr, repo, dry_run=args.dry_run)
    pid = proc.pid if proc else 0
    append_state_event(PRStateEvent(
        ts=_utcnow(),
        pr=pr,
        repo=repo or "",
        from_state=PRState.PUSHED.value,
        to_state=PRState.WATCHING.value,
        watcher_id=watcher_id,
        attempt=0,
        session_id=sid,
        extra={"pid": pid, "dry_run": args.dry_run, "detach": args.detach},
    ))
    if args.json:
        print(json.dumps({
            "watcher_id": watcher_id,
            "pid": pid,
            "pr": pr,
            "repo": repo,
            "mode": "detach" if args.detach else "foreground",
        }))
    else:
        mode = "detach" if args.detach else "foreground"
        print(f"watcher_id={watcher_id} pid={pid} pr={pr} repo={repo} mode={mode}")

    # Detach / dry-run: do NOT block; caller polls state.jsonl.
    if args.detach or args.dry_run or proc is None:
        return EXIT_OK

    # Foreground: block on subprocess, then fold result into a state event.
    rc = proc.wait()
    next_state = PRState.GREEN if rc == 0 else PRState.RED_UNCLASSIFIED
    append_state_event(PRStateEvent(
        ts=_utcnow(),
        pr=pr,
        repo=repo or "",
        from_state=PRState.WATCHING.value,
        to_state=next_state.value,
        watcher_id=watcher_id,
        attempt=0,
        session_id=sid,
        extra={"gh_exit_code": rc, "folded_by": "p9 watch"},
    ))
    if args.json:
        print(json.dumps({"watcher_id": watcher_id, "result": next_state.value, "gh_exit_code": rc}))
    else:
        print(f"folded: {next_state.value} (gh exit {rc})")
    return EXIT_OK


def cmd_status(args: argparse.Namespace) -> int:
    # Self-healing preflight: drain provably-dead watchers (liveness-only, no
    # network) so a crashed session's row stops counting against the ceiling
    # and stops showing as "in flight". --no-reap opts out.
    if not getattr(args, "no_reap", False):
        reap_stale_watchers(reconcile=False)
    session_id = None
    if getattr(args, "session", None):
        session_id = current_session_id() if args.session == "current" else args.session
    rows = open_prs(session_id=session_id)
    if args.pr is not None:
        rows = [r for r in rows if r["pr"] == int(args.pr)]
    if args.json:
        print(json.dumps({"open_prs": rows}, indent=2))
    else:
        if not rows:
            print("no PRs in flight")
            return EXIT_OK
        for r in rows:
            sess = r.get("session_id", "") or "-"
            print(
                f"#{r['pr']:<5} {r['to_state']:<18} "
                f"{(r.get('repo') or '-'):<24} "
                f"session={sess} watcher={r['watcher_id']} "
                f"attempt={r.get('attempt', 0)}"
            )
    return EXIT_OK


def cmd_wait_queue(args: argparse.Namespace) -> int:
    all_sessions = bool(getattr(args, "all", False))
    sub = args.action
    if sub == "push":
        item = queue_push(
            args.item, args.source, pr=args.pr,
            isolation_tier=args.tier or "none", repo=getattr(args, "repo", "") or "",
        )
        print(item.id)
        return EXIT_OK
    if sub == "pop":
        head = queue_pop(all_sessions=all_sessions)
        if not head:
            print("(empty)")
            return EXIT_OK
        print(json.dumps(dataclasses.asdict(head)))
        return EXIT_OK
    if sub == "list":
        items = queue_list(all_sessions=all_sessions)
        if args.json:
            print(json.dumps([dataclasses.asdict(it) for it in items], indent=2))
        else:
            for it in items:
                print(f"[{it.source:<7}] {it.id}  {it.item}")
        return EXIT_OK
    if sub == "clear":
        n = queue_clear(all_sessions=all_sessions)
        print(f"cleared {n} item(s)")
        return EXIT_OK
    print(f"unknown wait-queue action: {sub}", file=sys.stderr)
    return EXIT_USAGE


def cmd_heal(args: argparse.Namespace) -> int:
    apply = bool(getattr(args, "apply", False))
    if not args.classify and not apply:
        print("p9 heal requires --classify (read-only) or --apply (run heal)",
              file=sys.stderr)
        return EXIT_USAGE
    if args.log_file:
        log = Path(args.log_file).read_text(encoding="utf-8")
    elif not sys.stdin.isatty():
        log = sys.stdin.read()
    else:
        # Live mode: pull from gh
        log = _gh_log_failed(args.pr, args.repo)
    result = classify(log)

    if not apply:
        print(json.dumps(dataclasses.asdict(result), indent=2))
        return EXIT_OK

    # --apply path. Only auto-classifiable failures with a heal_command run;
    # everything else is an escalation (refuse, no action).
    base = dataclasses.asdict(result)
    if not result.classified or not result.heal_command:
        print(json.dumps({**base, "applied": False,
                          "reason": "not auto-classifiable — escalate"}, indent=2))
        return EXIT_DEGRADED
    if args.dry_run:
        print(json.dumps({**base, "applied": False, "dry_run": True,
                          "would_run": result.heal_command}, indent=2))
        return EXIT_OK

    # Serialize heal execution workspace-wide (spec §5.7 / heal.lock). Heal
    # commands touch shared tooling state — caches, generated files — that a
    # heal in a *parallel session* could race against. One heal in flight at a
    # time, machine-wide. This is the gap that left heal.lock defined-but-unused.
    timeout = float(getattr(args, "lock_timeout", 30.0) or 30.0)
    try:
        with file_lock(heal_lock_path(), timeout_s=timeout):
            rc = subprocess.run(result.heal_command, shell=True, check=False).returncode
    except P9Error as e:
        print(f"heal lock contention: {e}", file=sys.stderr)
        return EXIT_HEAL_LOCK_TIMEOUT
    print(json.dumps({**base, "applied": True, "heal_exit_code": rc}, indent=2))
    return EXIT_OK if rc == 0 else EXIT_DEGRADED


def cmd_reap(args: argparse.Namespace) -> int:
    """Reconcile dead-watcher rows so crashed/closed sessions stop holding
    concurrency slots. Liveness-based; enriches reasons via GitHub unless
    --no-reconcile."""
    reaped = reap_stale_watchers(
        reconcile=not getattr(args, "no_reconcile", False),
        grace_seconds=0.0 if getattr(args, "now", False) else None,
    )
    if getattr(args, "json", False):
        print(json.dumps({"reaped": reaped}, indent=2))
        return EXIT_OK
    if not reaped:
        print("p9 reap: nothing stale")
        return EXIT_OK
    for r in reaped:
        print(f"  #{r['pr']} ({r.get('repo') or '-'}): "
              f"{r['to_state']} ({r.get('reason', '')})")
    print(f"p9 reap: reaped {len(reaped)}")
    return EXIT_OK


def cmd_events_tail(args: argparse.Namespace) -> int:
    rows, _ = jsonl_read_all(state_jsonl())
    if args.since:
        cutoff = _parse_duration_ago(args.since)
        rows = [r for r in rows if r["ts"] >= cutoff]
    for r in rows:
        print(json.dumps(r))
    return EXIT_OK


def merge_ready_verdict(pr: int, repo: str | None) -> dict:
    """Query GitHub for the REAL merge predicate — not the `gh pr checks --watch`
    exit code, which is necessary-not-sufficient (it returns 0 on a subset of
    checks and before async bot reviews settle; observed three times on bstack
    PR #78 — see BRO-1489).

    Ready iff GitHub's server-computed ``mergeStateStatus`` says the required
    gates are satisfied AND there are zero unresolved review threads:

      - ``CLEAN``    → ready (everything green).
      - ``UNSTABLE`` → ready ONLY when 0 unresolved review threads. UNSTABLE means
                       mergeable with all *required* checks green but some
                       *non-required* check pending/failing (e.g. a CodeRabbit
                       soft-status that never resolves). GitHub computes
                       required-vs-non-required server-side, so we trust
                       mergeStateStatus instead of fragile isRequired parsing.
      - ``BLOCKED`` / ``DIRTY`` / ``BEHIND`` / ``DRAFT`` / ``UNKNOWN`` → not ready.
      - any unresolved review thread → not ready (stricter than branch protection;
        bstack reflex: every bot/human thread closed before merge).
      - any error querying gh → not ready (fail-safe; never merge blind).

    Returns a dict: {ready, state, mergeable, review_decision, unresolved_threads, reason}.
    ``unresolved_threads`` is -1 when it could not be determined (best-effort
    graphql); an undeterminable count does NOT block (the GitHub-enforced gates
    in mergeStateStatus already cover required conversation-resolution).
    """
    # mergeable / mergeStateStatus / reviewDecision are the valid `gh pr view
    # --json` fields. (reviewThreads is NOT a pr-view field — it needs graphql;
    # see _unresolved_review_threads below. This was caught by dogfooding.)
    cmd = ["gh", "pr", "view", str(pr), "--json",
           "mergeable,mergeStateStatus,reviewDecision"]
    if repo:
        cmd += ["--repo", repo]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return {"ready": False, "state": "QUERY_FAILED", "mergeable": "UNKNOWN",
                "review_decision": "", "unresolved_threads": -1,
                "reason": f"gh unavailable: {e}"}
    if out.returncode != 0:
        return {"ready": False, "state": "QUERY_FAILED", "mergeable": "UNKNOWN",
                "review_decision": "", "unresolved_threads": -1,
                "reason": (out.stderr.strip()[:200] or "gh pr view failed")}
    try:
        data = json.loads(out.stdout)
    except json.JSONDecodeError as e:
        return {"ready": False, "state": "QUERY_FAILED", "mergeable": "UNKNOWN",
                "review_decision": "", "unresolved_threads": -1,
                "reason": f"non-JSON from gh: {e}"}

    state = (data.get("mergeStateStatus") or "UNKNOWN").upper()
    mergeable = (data.get("mergeable") or "UNKNOWN").upper()
    decision = (data.get("reviewDecision") or "").upper()
    unresolved = _unresolved_review_threads(pr, repo)  # int, or -1 if undeterminable

    if mergeable == "CONFLICTING" or state in {"DIRTY", "BEHIND", "DRAFT", "BLOCKED", "UNKNOWN"}:
        ready, reason = False, f"mergeStateStatus={state} mergeable={mergeable}"
    elif decision == "CHANGES_REQUESTED":
        ready, reason = False, "reviewDecision=CHANGES_REQUESTED"
    elif unresolved > 0:
        ready, reason = False, f"{unresolved} unresolved review thread(s)"
    elif state == "CLEAN":
        ready, reason = True, "CLEAN"
    elif state == "UNSTABLE":
        ready, reason = True, ("UNSTABLE but required checks green + no blocking review "
                               "(only non-required checks un-green)")
    else:
        ready, reason = False, f"unrecognized mergeStateStatus={state}"

    return {"ready": ready, "state": state, "mergeable": mergeable,
            "review_decision": decision, "unresolved_threads": unresolved,
            "reason": reason}


def _unresolved_review_threads(pr: int, repo: str | None) -> int:
    """Count unresolved review threads via `gh api graphql` (best-effort).

    Returns the count, or -1 if it cannot be determined (no repo, gh/graphql
    error). -1 does not block a merge — mergeStateStatus already reflects
    GitHub-enforced conversation resolution when branch protection requires it;
    this is the stricter bstack reflex-18 layer on top.
    """
    if not repo or "/" not in repo:
        return -1
    owner, name = repo.split("/", 1)
    q = ("query($o:String!,$n:String!,$p:Int!){repository(owner:$o,name:$n)"
         "{pullRequest(number:$p){reviewThreads(first:100){nodes{isResolved}}}}}")
    cmd = ["gh", "api", "graphql", "-f", f"query={q}",
           "-F", f"o={owner}", "-F", f"n={name}", "-F", f"p={pr}"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
        if out.returncode != 0:
            return -1
        nodes = (json.loads(out.stdout)["data"]["repository"]["pullRequest"]
                 ["reviewThreads"]["nodes"])
        return sum(1 for t in nodes if not t.get("isResolved", False))
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError, KeyError, TypeError):
        return -1


def cmd_merge_status(args: argparse.Namespace) -> int:
    """Query + print the real merge predicate for a PR. The agent calls this
    instead of trusting the watcher exit code. Exit 0 iff merge-ready."""
    pr = int(args.pr)
    repo = args.repo or _detect_repo()
    v = merge_ready_verdict(pr, repo)
    if args.json:
        print(json.dumps(v))
    else:
        verdict = "READY" if v["ready"] else "NOT-READY"
        print(f"PR #{pr}: {verdict} — {v['reason']} "
              f"(mergeStateStatus={v['state']}, unresolved_threads={v['unresolved_threads']})")
    return EXIT_OK if v["ready"] else EXIT_DEGRADED


def cmd_merge_ready(args: argparse.Namespace) -> int:
    pr = int(args.pr)
    state = current_pr_state(pr)
    if state != PRState.GREEN:
        print(
            f"PR #{pr} not GREEN (current={state.value if state else 'UNKNOWN'})",
            file=sys.stderr,
        )
        return EXIT_DEGRADED
    repo = args.repo or _detect_repo()

    # Verify the REAL merge predicate before authorizing MERGE_READY. The GREEN
    # state only means `gh pr checks --watch` exited 0 — necessary, not
    # sufficient. Refuse if the PR is not actually mergeable (BRO-1489).
    verdict = None
    if not getattr(args, "no_verify", False):
        verdict = merge_ready_verdict(pr, repo)
        if not verdict["ready"]:
            print(
                f"PR #{pr} NOT merge-ready: {verdict['reason']} "
                f"(mergeStateStatus={verdict['state']}, "
                f"unresolved_threads={verdict['unresolved_threads']}).",
                file=sys.stderr,
            )
            print(
                "  The watcher exit code is necessary-not-sufficient; refusing to "
                "mark MERGE_READY. Re-run once checks settle, or --no-verify to override.",
                file=sys.stderr,
            )
            return EXIT_DEGRADED

    event = PRStateEvent(
        ts=_utcnow(),
        pr=pr,
        repo=repo or "",
        from_state=PRState.GREEN.value,
        to_state=PRState.MERGE_READY.value,
        watcher_id="merge-ready",
        attempt=0,
        extra={"merge_verdict": verdict} if verdict else {"merge_verdict": "skipped (--no-verify)"},
    )
    append_state_event(event)
    print(f"PR #{pr} marked MERGE_READY (control metalayer authorizes merge)")
    return EXIT_OK


# ─────────────────────────────────────────────────────────────────────────────
# Helpers (gh integration, cwd repo detection, time parsing)
# ─────────────────────────────────────────────────────────────────────────────
def _detect_repo() -> str | None:
    try:
        out = subprocess.run(
            ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if out.returncode == 0:
            return out.stdout.strip() or None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return None


def _gh_log_failed(pr: int, repo: str | None) -> str:
    cmd = ["gh", "run", "view", "--log-failed"]
    if repo:
        cmd += ["--repo", repo]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
    return out.stdout or out.stderr or ""


_DURATION_RE = re.compile(r"^(\d+)([smhd])$")


def _parse_duration_ago(spec: str) -> str:
    m = _DURATION_RE.match(spec)
    if not m:
        return spec  # treat as ISO timestamp passthrough
    n, unit = int(m.group(1)), m.group(2)
    secs = n * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
    return (
        _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(seconds=secs)
    ).isoformat(timespec="seconds")


# ─────────────────────────────────────────────────────────────────────────────
# CLI dispatch
# ─────────────────────────────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="p9",
        description=(
            "Broomva CI watcher + productive-wait primitive. "
            "See docs/superpowers/specs/2026-05-04-p9-ci-watcher-design.md"
        ),
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    pw = sub.add_parser("watch", help="Watch CI on a PR (foreground; folds result into state)")
    pw.add_argument("pr", help="PR number")
    pw.add_argument("--repo", help="OWNER/REPO (auto-detected if omitted)")
    pw.add_argument("--dry-run", action="store_true",
                    help="Do not actually spawn `gh pr checks --watch` (test mode)")
    pw.add_argument("--detach", action="store_true",
                    help="Fire-and-forget: spawn the watcher but do not block "
                         "or fold its exit into a state event. The caller is "
                         "responsible for finalizing state. Default is "
                         "foreground (block + fold).")
    # `--background` and `--block` are aliases for the default foreground
    # behavior. They exist so historic AGENTS.md guidance using
    # `p9 watch <pr> --background` keeps working without surprise errors.
    pw.add_argument("--background", action="store_true",
                    help="Alias for default foreground behavior (kept for "
                         "backwards compatibility with reflexive-rule guidance)")
    pw.add_argument("--block", action="store_true",
                    help="Alias for default foreground behavior")
    pw.add_argument("--adopt", action="store_true",
                    help="Re-watch a PR whose prior watcher pid is gone, "
                         "superseding the stale row immediately (orphan recovery "
                         "after a crashed/closed session).")
    pw.add_argument("--force", action="store_true",
                    help="Supersede an existing watcher for this PR even if it "
                         "appears live (overrides the double-watch guard).")
    pw.add_argument("--json", action="store_true")
    pw.set_defaults(func=cmd_watch)

    ps = sub.add_parser("status", help="Show in-flight PRs")
    ps.add_argument("--pr", help="filter by PR number")
    ps.add_argument("--session", default=None,
                    help="Filter to a session id ('current' = the active session)")
    ps.add_argument("--no-reap", action="store_true",
                    help="Skip the self-healing dead-watcher preflight")
    ps.add_argument("--json", action="store_true")
    ps.set_defaults(func=cmd_status)

    pq = sub.add_parser("wait-queue", help="Manage the productive-wait queue")
    pq.add_argument("action", choices=["push", "pop", "list", "clear"])
    pq.add_argument("--source", default="session",
                    choices=list(_QUEUE_PRIORITY))
    pq.add_argument("--item", default="", help="(push only) free-text item")
    pq.add_argument("--pr", type=int, default=None,
                    help="(push only) tag for this PR")
    pq.add_argument("--repo", default=None,
                    help="(push only) originating OWNER/REPO (for terminal-PR pruning)")
    pq.add_argument("--tier", default=None,
                    help="(push only) isolation tier")
    pq.add_argument("--all", action="store_true",
                    help="(pop/list/clear) act across ALL sessions, not just "
                         "the current one (default is current-session scope)")
    pq.add_argument("--json", action="store_true")
    pq.set_defaults(func=cmd_wait_queue)

    ph = sub.add_parser("heal", help="Classify (read-only) or apply a CI heal")
    ph.add_argument("pr", help="PR number")
    ph.add_argument("--repo", default=None)
    ph.add_argument("--classify", action="store_true",
                    help="Pure classifier read-out (no heal action)")
    ph.add_argument("--apply", action="store_true",
                    help="Run the classified heal_command under heal.lock "
                         "(serialized workspace-wide; auto-classifiable failures only)")
    ph.add_argument("--dry-run", action="store_true",
                    help="With --apply: print the heal command instead of running it")
    ph.add_argument("--lock-timeout", type=float, default=30.0,
                    help="Seconds to wait for heal.lock before giving up (default 30)")
    ph.add_argument("--log-file", default=None,
                    help="Read failure log from file instead of `gh run view`")
    ph.set_defaults(func=cmd_heal)

    prp = sub.add_parser("reap",
                         help="Reconcile dead-watcher rows (frees concurrency slots)")
    prp.add_argument("--no-reconcile", action="store_true",
                     help="Liveness only; do not query GitHub to enrich reasons")
    prp.add_argument("--now", action="store_true",
                     help="Ignore the grace window — reap dead watchers immediately")
    prp.add_argument("--json", action="store_true")
    prp.set_defaults(func=cmd_reap)

    pe = sub.add_parser("events", help="Stream P9 events")
    pe_sub = pe.add_subparsers(dest="events_cmd", required=True)
    pet = pe_sub.add_parser("tail")
    pet.add_argument("--since", default=None,
                     help="Filter events newer than DURATION (e.g. 6h, 30m)")
    pet.set_defaults(func=cmd_events_tail)

    pm = sub.add_parser("merge-ready", help="Mark PR as ready for metalayer-authorized merge")
    pm.add_argument("pr")
    pm.add_argument("--repo", default=None)
    pm.add_argument("--no-verify", action="store_true",
                    help="Skip the live mergeStateStatus check (test/offline only; "
                         "by default merge-ready verifies the real merge predicate)")
    pm.set_defaults(func=cmd_merge_ready)

    pms = sub.add_parser("merge-status",
                         help="Query the REAL merge predicate (mergeStateStatus + "
                              "unresolved review threads) — not the watcher exit code")
    pms.add_argument("pr")
    pms.add_argument("--repo", default=None)
    pms.add_argument("--json", action="store_true", help="Emit the verdict as JSON")
    pms.set_defaults(func=cmd_merge_status)

    pab = sub.add_parser("abandon",
                         help="Mark a PR as ABANDONED (frees concurrency slot)")
    pab.add_argument("pr")
    pab.add_argument("--repo", default=None)
    pab.add_argument("--reason", default=None,
                     help="Free-text reason recorded in extra.reason")
    pab.set_defaults(func=cmd_abandon)

    pcu = sub.add_parser("cleanup",
                         help="Drain orphan WATCHING/HEALING rows by polling "
                              "GitHub for each open PR's true state")
    pcu.set_defaults(func=cmd_cleanup)

    pa = sub.add_parser("auto-merge",
                        help="Run policy-gated auto-merge on a MERGE_READY PR")
    pa.add_argument("pr")
    pa.add_argument("--repo", default=None)
    pa.add_argument("--dry-run", action="store_true",
                    help="Print the planned merge instead of executing it")
    pa.set_defaults(func=cmd_auto_merge)

    pd = sub.add_parser("doctor", help="Health-check P9 dependencies")
    pd.set_defaults(func=cmd_doctor)

    pc = sub.add_parser("conformance",
                        help="Run the full pytest battery (unit + integration + chaos)")
    pc.add_argument("-v", "--verbose", action="store_true",
                    help="Verbose pytest output (-v)")
    pc.add_argument("-k", default=None,
                    help="Filter expression passed through to pytest -k")
    pc.set_defaults(func=cmd_conformance)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except P9Error as e:
        print(f"p9: {e}", file=sys.stderr)
        return e.code


if __name__ == "__main__":
    sys.exit(main())

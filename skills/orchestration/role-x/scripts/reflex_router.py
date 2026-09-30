"""reflex_router.py — role-x's reflex output (``ROLE_X_OUTPUT=reflex``).

Maps one prompt, plus cheap workspace state, to at most three lines, each a rule
stated as what the stack does and naming the command ("after a push, the stack runs
`p9 watch <pr> --background`"), with a fact about state in front when a predicate
holds. It replaces the lens block's persona lines and task-entity list, which the
context-ablation evals found the model almost never opens, with the kind of line
they found it acts on (#248, #251). Design of record: broomva/workspace
docs/specs/2026-09-30-reflex-router-and-ontology-ranked-context.html §5 (BRO-2674).

Selection, per catalog clause, cheapest first; each stage only narrows:
1. **Prompt.** A clause that asks anything of the prompt (regexes, phrases, named
   routes such as ``change_work``, ``requires``) is matched first: pure regex, no I/O.
2. **State.** Only then its state predicates, each read lazily and at most once per
   prompt: one ``git status --porcelain=v2 --branch``, one reflog tail, ctx-core's
   ``board.json`` cache (never its log). A predicate that raises counts as false
   and is logged; it never takes the other reflexes down with it.
3. **Narrowing, ``ROLE_X_JEV``.** The seam a typed classifier plugs into. v1 ships
   only ``off``. A narrower may drop candidates and never add one, and it cannot drop
   the pinned p9 rule once stages 1-2 kept it (spec §5.3).
Rank: a pinned entry (the p9 rule, spec I1) first, then state+prompt, state alone,
prompt alone, then priority. When several clauses of one entry fire, their facts are
merged. At most ``max_lines`` lines in ``max_chars`` characters, and a line goes out at
most ``REPEAT_CAP`` times per session for the same fact, the pinned rule excepted (a
per-session file, not the event log). No persona lines, no entity list, and nothing at
all when nothing fires.

Loaded by ``role-x.py`` by file path (the hooks run Python with ``-I``, which keeps
this directory off ``sys.path``). Catalog and I/O failures raise; the caller prints
nothing.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol, Sequence

HERE = Path(__file__).resolve().parent
CATALOG_PATH = HERE.parent / "references" / "reflexes.yaml"
#: Test and eval override for the catalog path. Unset means CATALOG_PATH.
CATALOG_ENV = "ROLE_X_REFLEX_CATALOG"
#: Stage 3. Unset or unknown means "off".
JEV_ENV = "ROLE_X_JEV"
#: ctx-core sits beside role-x both in this repo (skills/orchestration/) and in an
#: install (~/.agents/skills/). Absent means no board predicate, nothing else.
CTX_PY = HERE.parent.parent / "ctx-core" / "scripts" / "ctx.py"

HEADER = "[bstack reflexes]"
DEFAULT_BRANCHES = frozenset({"main", "master"})
#: A push this recent still counts as "just pushed".
PUSH_RECENT_S = 15 * 60
GIT_TIMEOUT_S = 1.0
#: The reflog tail read to find the last update; a line is ~150 bytes.
REFLOG_TAIL_BYTES = 4096
#: A catalog line longer than this is refused when the catalog loads.
LINE_MAX_CHARS = 200
#: A line goes out at most this many times per session per fact (spec §5.3, row 8).
REPEAT_CAP = 2
#: Per-session injection counts; one small file per session, pruned after a week.
SESSIONS_DIR_REL = Path(".config") / "broomva" / "role" / "reflex-sessions"
SESSION_TTL_S = 7 * 86400
SESSION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
#: A peer's branch or agent id shown in a line is flattened and cut to this.
PEER_FIELD_MAX = 60
CLAUSE_KEYS = frozenset({"state", "prompt", "phrases", "routes", "requires"})
KINDS = frozenset({"primitive", "skill", "convention"})
STATUSES = frozenset({"routed", "listed", "judgment"})
SIGNATURE_TOOLS = frozenset({"Bash", "Skill", "Read", "Write", "mcp"})
#: Interpreters and wrappers skipped before a Bash signature's argv_prefix is
#: compared, so `python3 …/p9.py watch` matches [p9, watch] (spec §5.6, row 3).
ARGV_WRAPPERS = frozenset({"python", "python3", "bash", "sh", "zsh", "node", "env", "uv", "run", "npx", "exec"})


class CatalogError(ValueError):
    """The catalog is missing, malformed, or names something that does not exist."""


# --------------------------------------------------------------------------
# catalog


@dataclass(frozen=True)
class Clause:
    state: tuple[str, ...]
    #: any of these matching the prompt satisfies the prompt side
    patterns: tuple[re.Pattern[str], ...]
    #: every one of these must also match (an artifact in the prompt, say)
    requires: tuple[re.Pattern[str], ...] = ()

    @property
    def has_prompt(self) -> bool:
        return bool(self.patterns or self.requires)

    def prompt_matches(self, text: str) -> bool:
        if self.patterns and not any(p.search(text) for p in self.patterns):
            return False
        return all(p.search(text) for p in self.requires)


@dataclass(frozen=True)
class Reflex:
    id: str
    kind: str
    status: str
    line: str
    source: str
    priority: int
    index: int
    clauses: tuple[Clause, ...]
    primitive: str = ""
    skill: str = ""
    skill_source: str = ""
    routing: str = ""
    phrases: tuple[str, ...] = ()
    signature: tuple[dict[str, Any], ...] = ()
    measured: str = ""
    #: spec I1: goes in the first slot when it fires, and the repeat cap skips it
    pinned: bool = False

    @property
    def routed(self) -> bool:
        return self.status == "routed"


@dataclass(frozen=True)
class Catalog:
    reflexes: tuple[Reflex, ...]
    max_lines: int
    max_chars: int
    routes: dict[str, tuple[re.Pattern[str], ...]] = field(default_factory=dict)


def phrase_pattern(phrase: str) -> re.Pattern[str]:
    """A literal phrase, case-insensitive, not inside a longer word."""
    return re.compile(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", re.IGNORECASE)


#: In a catalog regex, ``[^.?!]`` means "still in the same sentence". Punctuation
#: followed by a non-space (the dot in ``.worktrees/``, ``README.md``, ``v0.7``) is
#: not a sentence end, so the loader widens the class to let it through.
SAME_SENTENCE = "[^.?!]"
SAME_SENTENCE_WIDE = r"(?:[^.?!]|[.?!](?=\S))"


def prompt_pattern(rx: str) -> re.Pattern[str]:
    return re.compile(rx.replace(SAME_SENTENCE, SAME_SENTENCE_WIDE), re.IGNORECASE)


def _load_yaml(path: Path) -> Any:
    import yaml  # role-x.py has already made PyYAML importable under -I

    loader = getattr(yaml, "CSafeLoader", None) or yaml.SafeLoader
    with path.open(encoding="utf-8") as fh:
        return yaml.load(fh, Loader=loader)  # noqa: S506 - a safe loader


def catalog_path() -> Path:
    override = os.environ.get(CATALOG_ENV)
    return Path(override) if override else CATALOG_PATH


def load_catalog(path: Path | None = None) -> Catalog:
    """Parse and validate the catalog. Raises CatalogError on anything wrong, so a
    broken catalog routes nothing rather than half of what it says."""
    path = path or catalog_path()
    try:
        raw = _load_yaml(path)
    except OSError as exc:
        raise CatalogError(f"{path}: {exc}") from exc
    except Exception as exc:  # a YAML parse error
        raise CatalogError(f"{path}: not YAML: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("version") != 1:
        raise CatalogError("catalog must be a mapping with version: 1")
    max_lines, max_chars = raw.get("max_lines"), raw.get("max_chars")
    for name, val in (("max_lines", max_lines), ("max_chars", max_chars)):
        if not isinstance(val, int) or isinstance(val, bool) or val < 1:
            raise CatalogError(f"{name} must be a positive integer")
    routes_raw = raw.get("routes") or {}
    if not isinstance(routes_raw, dict):
        raise CatalogError("routes must be a mapping of name -> regex list")
    routes = {str(k): tuple(_compile_all(_str_list(v, f"route {k}"), f"route {k}"))
              for k, v in routes_raw.items()}
    entries = raw.get("reflexes")
    if not isinstance(entries, list) or not entries:
        raise CatalogError("reflexes must be a non-empty list")
    seen: set[str] = set()
    out = [_parse_entry(e, i, seen, routes) for i, e in enumerate(entries)]
    return Catalog(reflexes=tuple(out), max_lines=max_lines, max_chars=max_chars, routes=routes)


def _str_list(value: Any, what: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        raise CatalogError(f"{what} must be a list of non-empty strings")
    return value


def _compile_all(regexes: list[str], what: str) -> list[re.Pattern[str]]:
    out = []
    for rx in regexes:
        try:
            out.append(prompt_pattern(rx))
        except re.error as exc:
            raise CatalogError(f"{what}: bad regex {rx!r}: {exc}") from exc
    return out


def _parse_signature(value: Any, rid: str) -> tuple[dict[str, Any], ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not value:
        raise CatalogError(f"{rid}: signature must be a non-empty list")
    for sig in value:
        if not isinstance(sig, dict) or sig.get("tool") not in SIGNATURE_TOOLS:
            raise CatalogError(f"{rid}: a signature needs tool in {sorted(SIGNATURE_TOOLS)}")
        keys = set(sig) - {"tool"}
        if len(keys) != 1 or not keys <= {"argv_prefix", "name", "path_re"}:
            raise CatalogError(f"{rid}: a signature has exactly one of argv_prefix, name, path_re")
        if "argv_prefix" in sig:
            _str_list(sig["argv_prefix"], f"{rid}: signature argv_prefix")
        elif not isinstance(sig.get("name", sig.get("path_re")), str):
            raise CatalogError(f"{rid}: signature name/path_re must be a string")
        if "path_re" in sig:
            try:
                re.compile(sig["path_re"])
            except re.error as exc:
                raise CatalogError(f"{rid}: bad signature path_re: {exc}") from exc
    return tuple(value)


def _parse_entry(e: Any, index: int, seen: set[str], routes: dict[str, tuple]) -> Reflex:
    if not isinstance(e, dict):
        raise CatalogError(f"entry {index} is not a mapping")
    rid = e.get("id")
    if not isinstance(rid, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*\.[a-z0-9][a-z0-9-]*", rid):
        raise CatalogError(f"entry {index}: id must be <group>.<slug>, lowercase")
    if rid in seen:
        raise CatalogError(f"{rid}: duplicate id")
    seen.add(rid)
    kind, status = e.get("kind"), e.get("status")
    if kind not in KINDS:
        raise CatalogError(f"{rid}: kind must be one of {sorted(KINDS)}")
    if status not in STATUSES:
        raise CatalogError(f"{rid}: status must be one of {sorted(STATUSES)}")
    line, source = e.get("line"), e.get("source")
    if not isinstance(line, str) or not line.strip() or "\n" in line:
        raise CatalogError(f"{rid}: line must be one non-empty line")
    if len(line) > LINE_MAX_CHARS:
        raise CatalogError(f"{rid}: line is {len(line)} chars, over {LINE_MAX_CHARS}")
    if not isinstance(source, str) or not source.strip():
        raise CatalogError(f"{rid}: every entry cites a source")
    priority = e.get("priority", 100)
    if not isinstance(priority, int) or isinstance(priority, bool):
        raise CatalogError(f"{rid}: priority must be an integer")
    when = e.get("when")
    if not isinstance(when, list) or not when:
        raise CatalogError(f"{rid}: when must be a non-empty list of clauses")
    clauses: list[Clause] = []
    phrases_all: list[str] = []
    for c in when:
        if not isinstance(c, dict) or not c or set(c) - CLAUSE_KEYS:
            raise CatalogError(f"{rid}: a clause is a mapping of {sorted(CLAUSE_KEYS)}")
        state = _str_list(c.get("state"), f"{rid}: state")
        unknown = [s for s in state if s not in STATE_PREDICATES]
        if unknown:
            raise CatalogError(f"{rid}: unknown state predicate(s) {unknown}")
        pats = _compile_all(_str_list(c.get("prompt"), f"{rid}: prompt"), rid)
        phrases = _str_list(c.get("phrases"), f"{rid}: phrases")
        phrases_all.extend(phrases)
        pats.extend(phrase_pattern(p) for p in phrases)
        for name in _str_list(c.get("routes"), f"{rid}: routes"):
            if name not in routes:
                raise CatalogError(f"{rid}: unknown route {name!r}")
            pats.extend(routes[name])
        requires = _compile_all(_str_list(c.get("requires"), f"{rid}: requires"), rid)
        if not state and not pats and not requires:
            raise CatalogError(f"{rid}: a clause needs a state predicate or a prompt pattern")
        clauses.append(Clause(state=tuple(state), patterns=tuple(pats), requires=tuple(requires)))
    skill, skill_source = e.get("skill", ""), e.get("skill_source", "")
    if bool(skill) != bool(skill_source):
        raise CatalogError(f"{rid}: skill and skill_source go together")
    signature = _parse_signature(e.get("signature"), rid)
    if status == "routed" and not signature:
        raise CatalogError(f"{rid}: a routed entry names its signature (what following it looks like)")
    return Reflex(
        id=rid, kind=kind, status=status, line=line.strip(), source=source.strip(),
        priority=priority, index=index, clauses=tuple(clauses),
        primitive=str(e.get("primitive") or ""), skill=str(skill or ""),
        skill_source=str(skill_source or ""), routing=str(e.get("routing") or ""),
        phrases=tuple(phrases_all), signature=signature, measured=str(e.get("measured") or ""),
        pinned=e.get("pinned") is True,
    )


def _argv_words(command: str) -> list[str]:
    """The words of a shell command a signature compares: env assignments and
    interpreters dropped, each word reduced to its basename without .py/.sh."""
    try:
        words = shlex.split(command)
    except ValueError:
        words = command.split()
    out = []
    for w in words:
        if not out and ("=" in w.split("/")[0] or os.path.basename(w) in ARGV_WRAPPERS):
            continue  # VAR=x, python3, bash, uv run ... before the real command
        base = os.path.basename(w)
        out.append(re.sub(r"\.(py|sh)$", "", base))
    return out


def signature_matches(sig: dict[str, Any], tool: str, *, command: str = "", name: str = "",
                      path: str = "") -> bool:
    """Whether a tool call follows a reflex (for the ledger's follow-through, spec
    §5.5 M1). Bash matches on argv prefix after wrappers; Write covers Edit and
    MultiEdit; Skill and mcp match on name."""
    want = sig.get("tool")
    if want == "Write":
        if tool not in ("Write", "Edit", "MultiEdit"):
            return False
    elif tool != want:
        return False
    if "argv_prefix" in sig:
        prefix = list(sig["argv_prefix"])
        # each command of a chain (`cd x && gh pr merge 1`, `a; b`, `a || b`, `a | b`)
        return any(_argv_words(part)[:len(prefix)] == prefix
                   for part in re.split(r"&&|\|\||;|\|", command))
    if "path_re" in sig:
        return bool(re.search(sig["path_re"], path or ""))
    return name == sig.get("name")


# --------------------------------------------------------------------------
# state: read once, lazily, and never more than once per prompt


@dataclass
class GitState:
    #: "ok", "no-repo" (git ran and said no), "timeout", or "error"
    status: str = "error"
    branch: str | None = None  # None when detached or unknown
    oid: str | None = None
    upstream: str | None = None
    ahead: int | None = None
    staged: int = 0

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def parse_porcelain_v2(text: str) -> GitState:
    g = GitState(status="ok")
    for line in text.splitlines():
        if line.startswith("# branch.oid "):
            oid = line[len("# branch.oid "):].strip()
            g.oid = oid if re.fullmatch(r"[0-9a-f]{40,64}", oid) else None
        elif line.startswith("# branch.head "):
            head = line[len("# branch.head "):].strip()
            g.branch = None if head == "(detached)" else head
        elif line.startswith("# branch.upstream "):
            g.upstream = line[len("# branch.upstream "):].strip() or None
        elif line.startswith("# branch.ab "):
            m = re.match(r"# branch\.ab \+(\d+) -(\d+)", line)
            g.ahead = int(m.group(1)) if m else None
        elif line[:2] in ("1 ", "2 ", "u ") and len(line) > 3 and line[2] != ".":
            g.staged += 1
    return g


def git_common_dir(start: Path) -> Path | None:
    """The git common dir for *start*, from the filesystem the way git finds it: a
    `.git` directory, or a `.git` file's `gitdir:` target and its `commondir`."""
    for d in (start, *start.parents):
        dotgit = d / ".git"
        if dotgit.is_dir():
            gitdir = dotgit
        elif dotgit.is_file():
            try:
                text = dotgit.read_text(encoding="utf-8", errors="replace")[:4096].strip()
            except OSError:
                return None
            if not text.startswith("gitdir:"):
                return None
            gitdir = (d / text[len("gitdir:"):].strip()).resolve()
        else:
            continue
        try:
            rel = (gitdir / "commondir").read_text(encoding="utf-8").strip()
        except OSError:
            return gitdir.resolve()
        return (gitdir / rel).resolve()
    return None


def last_reflog_entry(path: Path) -> tuple[str, float, str] | None:
    """(new sha, unix time, message) of a reflog's last line, reading only its tail."""
    try:
        with path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - REFLOG_TAIL_BYTES))
            tail = fh.read().decode("utf-8", "replace")
    except OSError:
        return None
    lines = [ln for ln in tail.splitlines() if ln.strip()]
    if not lines:
        return None
    head, _, msg = lines[-1].partition("\t")
    m = re.match(r"^[0-9a-f]+ ([0-9a-f]+) .* (\d+) [+-]\d{4}$", head)
    if not m:
        return None
    return m.group(1), float(m.group(2)), msg.strip()


def _load_ctx() -> Any:
    """ctx-core's module, by file path, or None when it is not installed."""
    name = "role_x_ctx_core"
    if name in sys.modules:
        return sys.modules[name]
    if not CTX_PY.is_file():
        return None
    spec = importlib.util.spec_from_file_location(name, CTX_PY)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return mod


@dataclass
class State:
    """Everything the predicates read. Each source is read at most once."""

    cwd: Path
    session_id: str = ""
    now: float = field(default_factory=time.time)
    run: Callable[..., Any] = subprocess.run
    ctx_loader: Callable[[], Any] = _load_ctx
    _git: GitState | None = None
    _peer: tuple[bool, str] | None = None
    #: Each source read this prompt and how it went (git: ok/no-repo/timeout/error;
    #: board: ok/no-ctx/no-scope/empty/too-big/error). The budget test reads this.
    reads: dict[str, str] = field(default_factory=dict)

    @property
    def git(self) -> GitState:
        if self._git is None:
            env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0", "LC_ALL": "C"}
            try:
                p = self.run(
                    ["git", "-C", str(self.cwd), "status", "--porcelain=v2", "--branch",
                     "--untracked-files=no"],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                    timeout=GIT_TIMEOUT_S, env=env)
                self._git = parse_porcelain_v2(p.stdout) if p.returncode == 0 else GitState("no-repo")
            except subprocess.TimeoutExpired:
                self._git = GitState("timeout")
            except (OSError, subprocess.SubprocessError, ValueError):
                self._git = GitState("error")
            self.reads["git"] = self._git.status
        return self._git

    @property
    def peer(self) -> tuple[bool, str]:
        """(a live peer is on this branch, the fact to show), from the ctx board
        cache. The log is never read: only ctx's own ``load_board``."""
        if self._peer is None:
            self._peer = (False, "")
            ctx = self.ctx_loader()
            if ctx is None:
                self.reads["board"] = "no-ctx"
            else:
                self.reads["board"], self._peer = _live_peer(ctx, self.cwd, self.session_id, self.now)
        return self._peer


def _peer_text(ctx: Any, value: Any) -> str:
    """A board string as a line may show it: ctx's own flatten and clip, then no
    backticks, so text another session controls cannot leave its code span."""
    flat = getattr(ctx, "_flat", lambda s: str(s))
    clip = getattr(ctx, "_clip", None)
    s = clip(value, PEER_FIELD_MAX) if clip else flat(value)[:PEER_FIELD_MAX]
    return str(s).replace("`", "'")


def _live_peer(ctx: Any, cwd: Path, session_id: str, now: float) -> tuple[str, tuple[bool, str]]:
    """Live means what ctx's brief means: the same repo and branch, not died, an
    event inside ctx's live window (ctx.render_brief, ctx.is_live)."""
    scope = ctx.resolve_scope(str(cwd))
    if scope is None:
        return "no-scope", (False, "")
    try:
        board = ctx.load_board(scope, cap=ctx.HOOK_BOARD_CAP)
    except ctx.BoardTooBig:
        return "too-big", (False, "")
    if not board:
        return "empty", (False, "")
    flat = getattr(ctx, "_flat", str)
    me = scope.where
    my_repo = flat(me.common_dir)
    my_branch = flat(me.branch) if me.branch else None
    if not my_branch:
        return "ok", (False, "")
    best = None
    for r in (board.get("sessions") or {}).values():
        if not isinstance(r, dict) or r.get("session_id") == session_id:
            continue
        if r.get("repo") != my_repo or r.get("branch") != my_branch or not ctx.is_live(r, now):
            continue
        if best is None or str(r.get("last_ts")) > str(best.get("last_ts")):
            best = r
    if best is None:
        return "ok", (False, "")
    who = f"session {_peer_text(ctx, best.get('session_id'))[:8]}"
    if best.get("paseo_agent_id"):
        who += f" (Paseo agent {_peer_text(ctx, best['paseo_agent_id'])})"
    age_min = max(0, int((now - ctx.parse_ts(best["last_ts"])) // 60))
    branch = _peer_text(ctx, best.get("branch") or "-")
    return "ok", (True, f"ctx board: {who} is live on `{branch}`, last event {age_min} min ago")


# --------------------------------------------------------------------------
# state predicates: name -> (held?, fact shown when a state clause fires)


def _branch_pushed_recently(s: State) -> tuple[bool, str]:
    """HEAD is a non-default branch, level with its upstream, and the upstream's
    reflog says its last update was a push of this very commit, minutes ago. (The
    spec's PR-level facts need a local link from session to PR, which v1 lacks.)"""
    g = s.git
    if not (g.ok and g.branch and g.branch not in DEFAULT_BRANCHES and g.upstream
            and g.oid and g.ahead == 0):
        return False, ""
    common = git_common_dir(s.cwd)
    if common is None:
        return False, ""
    entry = last_reflog_entry(common / "logs" / "refs" / "remotes" / g.upstream)
    if entry is None:
        return False, ""
    new, when, msg = entry
    age = s.now - when
    if new != g.oid or not msg.startswith("update by push") or not 0 <= age <= PUSH_RECENT_S:
        return False, ""
    return True, f"`{g.branch}` was pushed {int(age // 60)} min ago"


def _on_default_branch(s: State) -> tuple[bool, str]:
    g = s.git
    if g.ok and g.branch in DEFAULT_BRANCHES:
        return True, f"this checkout is on `{g.branch}`"
    return False, ""


def _staged_on_default_branch(s: State) -> tuple[bool, str]:
    g = s.git
    if g.ok and g.branch in DEFAULT_BRANCHES and g.staged > 0:
        return True, f"`{g.branch}` has {g.staged} staged change(s)"
    return False, ""


def _live_peer_on_branch(s: State) -> tuple[bool, str]:
    return s.peer


def _in_git_repo(s: State) -> tuple[bool, str]:
    return s.git.ok, ""


def _unshipped_work(s: State) -> tuple[bool, str]:
    """Spec I1's state signal for change work: staged changes, a branch ahead of its
    upstream, or a feature branch with no upstream yet (its commits exist nowhere
    else). From the same one `git status`."""
    g = s.git
    if not g.ok:
        return False, ""
    if g.staged:
        return True, f"`{g.branch or 'HEAD'}` has {g.staged} staged change(s)"
    if g.branch and g.branch not in DEFAULT_BRANCHES:
        if g.upstream and (g.ahead or 0) > 0:
            return True, f"`{g.branch}` is {g.ahead} commit(s) ahead of `{g.upstream}`"
        if not g.upstream:
            return True, f"`{g.branch}` has no upstream yet"
    return False, ""


STATE_PREDICATES: dict[str, Callable[[State], tuple[bool, str]]] = {
    "branch_pushed_recently": _branch_pushed_recently,
    "on_default_branch": _on_default_branch,
    "staged_on_default_branch": _staged_on_default_branch,
    "live_peer_on_branch": _live_peer_on_branch,
    "in_git_repo": _in_git_repo,
    "unshipped_work": _unshipped_work,
}


# --------------------------------------------------------------------------
# stage 3: the narrowing seam


@dataclass(frozen=True)
class Candidate:
    """One clause that survived stages 1 and 2."""

    key: str  # "<reflex id>#<clause index>"
    reflex: Reflex
    clause: Clause
    facts: tuple[str, ...]


class Narrower(Protocol):
    name: str

    def narrow(self, prompt: str, candidates: Sequence[Candidate]) -> set[str]:
        """The keys to keep. Anything returned that was not offered is ignored, and a
        pinned candidate is kept whatever is returned."""


class Off:
    """``ROLE_X_JEV=off`` (v1's only stage 3): keep everything the stages before kept."""

    name = "off"

    def narrow(self, prompt: str, candidates: Sequence[Candidate]) -> set[str]:
        return {c.key for c in candidates}


#: A typed classifier (Jev, spec §5.3) registers here under its ROLE_X_JEV value.
#: It sees only the clauses stages 1-2 kept, and may abstain. Per the spec it must
#: run async (a cache the next prompt reads) before any value but off ships.
NARROWERS: dict[str, Callable[[], Narrower]] = {"off": Off}


def get_narrower(name: str | None = None) -> Narrower:
    chosen = name if name is not None else os.environ.get(JEV_ENV, "off")
    return NARROWERS.get(chosen, Off)()


# --------------------------------------------------------------------------
# per-session repeat cap (a file per session, never the event log)


def sessions_dir(home: Path | None = None) -> Path:
    return (home or Path(os.environ.get("HOME") or Path.home())) / SESSIONS_DIR_REL


def _session_file(session_id: str, home: Path | None = None) -> Path | None:
    if not SESSION_ID_RE.match(session_id or "") or session_id in ("unknown", "offline"):
        return None
    return sessions_dir(home) / f"{session_id}.json"


def load_counts(session_id: str, home: Path | None = None) -> dict[str, int]:
    path = _session_file(session_id, home)
    if path is None:
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in raw.items() if isinstance(k, str) and isinstance(v, int)} if isinstance(raw, dict) else {}


def save_counts(session_id: str, counts: dict[str, int], home: Path | None = None) -> None:
    """Atomic replace of this session's counts; then prune a few week-old files."""
    path = _session_file(session_id, home)
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(counts, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)
    cutoff = time.time() - SESSION_TTL_S
    for i, old in enumerate(path.parent.glob("*.json")):
        if i >= 200:
            break
        try:
            if old.stat().st_mtime < cutoff:
                old.unlink()
        except OSError:
            continue


# --------------------------------------------------------------------------
# routing and rendering

#: How a reflex fired, best first.
VIA_RANK = {"state+prompt": 0, "state": 1, "prompt": 2}


@dataclass(frozen=True)
class Fired:
    reflex: Reflex
    via: str
    facts: tuple[str, ...]
    clause: int = 0

    @property
    def sort_key(self) -> tuple[int, int, int, int]:
        # a pinned rule takes the first slot whenever it fires (spec I1)
        return (0 if self.reflex.pinned else 1, VIA_RANK[self.via], self.reflex.priority, self.reflex.index)

    @property
    def repeat_key(self) -> str:
        """(id, fact key): a new fact (another branch, a new push) is a new line;
        digits are dropped so "pushed 2 min ago" and "3 min ago" are one fact."""
        # only counts and ages vary between prompts; a branch name's digits are the fact
        return self.reflex.id + "|" + re.sub(r"\b\d+(?= (min|commit|staged))", "#", "; ".join(self.facts))


@dataclass
class Routed:
    fired: list[Fired]
    predicates_true: list[str]
    predicate_errors: dict[str, str]
    stage_ms: dict[str, float]


def normalize_prompt(prompt: str) -> str:
    table = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"'})
    return " ".join(prompt.translate(table).split())


def route_detail(prompt: str, state: State, catalog: Catalog,
                 narrower: Narrower | None = None) -> Routed:
    """Every routed reflex that fires, best first, with what decided it."""
    text = normalize_prompt(prompt)
    if not text:
        return Routed([], [], {}, {})
    narrower = narrower or get_narrower()
    held: dict[str, tuple[bool, str]] = {}
    errors: dict[str, str] = {}
    timing = {"prompt": 0.0, "state": 0.0, "narrow": 0.0}

    def check(name: str) -> tuple[bool, str]:
        if name not in held:
            t = time.monotonic()
            try:
                held[name] = STATE_PREDICATES[name](state)
            except Exception as exc:  # noqa: BLE001 — one source never blanks the rest
                held[name] = (False, "")
                errors[name] = type(exc).__name__
            timing["state"] += time.monotonic() - t
        return held[name]

    kept: list[Candidate] = []
    for r in catalog.reflexes:
        if not r.routed:
            continue
        for i, c in enumerate(r.clauses):
            if c.has_prompt:  # the prompt first: pure regex, no I/O
                t = time.monotonic()
                ok = c.prompt_matches(text)
                timing["prompt"] += time.monotonic() - t
                if not ok:
                    continue
            facts: list[str] = []
            for name in c.state:  # in order, stopping at the first that fails
                ok, fact = check(name)
                if not ok:
                    break
                if fact:
                    facts.append(fact)
            else:
                kept.append(Candidate(f"{r.id}#{i}", r, c, tuple(facts)))
    t = time.monotonic()
    keep = narrower.narrow(text, kept) if kept else set()
    # the pin is applied after narrowing (spec §5.3): a narrower cannot drop p9
    kept = [c for c in kept if c.key in keep or c.reflex.pinned]
    timing["narrow"] += time.monotonic() - t
    best: dict[str, Fired] = {}
    for c in kept:
        via = ("state+prompt" if c.clause.has_prompt else "state") if c.clause.state else "prompt"
        f = Fired(c.reflex, via, c.facts, int(c.key.rsplit("#", 1)[1]))
        prev = best.get(c.reflex.id)
        if prev is not None:
            # one line per entry: the best-ranked clause, with every clause's facts
            top, other = (f, prev) if f.sort_key < prev.sort_key else (prev, f)
            f = Fired(top.reflex, top.via, tuple(dict.fromkeys(top.facts + other.facts)), top.clause)
        best[c.reflex.id] = f
    return Routed(
        fired=sorted(best.values(), key=lambda f: f.sort_key),
        predicates_true=sorted(n for n, (ok, _) in held.items() if ok),
        predicate_errors=errors,
        stage_ms={k: round(v * 1000, 1) for k, v in timing.items()},
    )


def route(prompt: str, state: State, catalog: Catalog, narrower: Narrower | None = None) -> list[Fired]:
    return route_detail(prompt, state, catalog, narrower).fired


def _sentence(fact: str) -> str:
    return fact[:1].upper() + fact[1:] if fact[:1].isalpha() else fact


def render_line(f: Fired) -> str:
    tag = f" [{f.reflex.primitive}]" if f.reflex.primitive else ""
    lead = "; ".join(_sentence(x) if i == 0 else x for i, x in enumerate(f.facts))
    return f"- {lead + '. ' if lead else ''}{f.reflex.line}{tag}"


def render(fired: Sequence[Fired], max_lines: int, max_chars: int,
           counts: dict[str, int] | None = None) -> tuple[str, list[Fired]]:
    """The block and the reflexes in it. Empty when nothing fits: never a bare header.
    A line already injected ``REPEAT_CAP`` times this session for the same fact is
    skipped, unless its entry is pinned (spec §5.3 row 8, I1)."""
    counts = counts or {}
    out, shown, used, seen = [HEADER], [], len(HEADER), set()
    for f in fired:
        if len(shown) >= max_lines:
            break
        if f.reflex.line in seen:
            continue
        if not f.reflex.pinned and counts.get(f.repeat_key, 0) >= REPEAT_CAP:
            continue
        text = render_line(f)
        if used + 1 + len(text) > max_chars:
            continue  # atomic: a line that does not fit is dropped, never cut
        out.append(text)
        shown.append(f)
        seen.add(f.reflex.line)
        used += 1 + len(text)
    return ("\n".join(out), shown) if shown else ("", [])


def run(prompt: str, cwd: Path, session_id: str = "", *, catalog: Catalog | None = None,
        state: State | None = None, narrower: Narrower | None = None,
        count: bool = True) -> tuple[str, dict[str, Any]]:
    """The whole reflex path: (text to print, the event record's fields). With
    ``count`` the session's repeat counts advance; shadow counts too, so its record
    is what reflex would have injected. Only the offline CLI passes False."""
    started = time.monotonic()
    catalog = catalog or load_catalog()
    state = state or State(cwd=cwd, session_id=session_id)
    narrower = narrower or get_narrower()
    routed = route_detail(prompt, state, catalog, narrower)
    counts = load_counts(session_id) if count else {}
    text, shown = render(routed.fired, catalog.max_lines, catalog.max_chars, counts)
    shown_ids = [f.reflex.id for f in shown]
    if count and shown_ids:
        for f in shown:
            counts[f.repeat_key] = counts.get(f.repeat_key, 0) + 1
        try:
            save_counts(session_id, counts)
        except OSError:
            pass  # a lost count repeats a line once more; it never blocks the hook
    meta = {
        "selected": shown_ids,
        "via": {f.reflex.id: f.via for f in shown},
        "clause": {f.reflex.id: f.clause for f in shown},
        "cut": [f.reflex.id for f in routed.fired if f.reflex.id not in shown_ids],
        "predicates_true": routed.predicates_true,
        "jev": narrower.name,
        "bytes": len(text.encode("utf-8")),
        "reads": dict(state.reads),
        "stage_ms": routed.stage_ms,
        "ms": round((time.monotonic() - started) * 1000, 1),
    }
    if routed.predicate_errors:
        meta["predicate_errors"] = routed.predicate_errors
    return text, meta

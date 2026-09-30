"""reflex_router.py — role-x's reflex output (``ROLE_X_OUTPUT=reflex``).

Maps one prompt, plus cheap workspace state, to at most three factual lines, each
naming the command this stack uses at that moment ("after a push, the stack runs
`p9 watch <pr> --background`"). It replaces the lens block's persona lines and
task-entity list, which the context-ablation evals found the model almost never
opens, with the kind of line they found it acts on (#248, #251). Design of record:
broomva/workspace docs/specs/2026-09-30-reflex-router-and-ontology-ranked-context.html
§5 (BRO-2674).

Selection runs cheapest first, and each stage only narrows what it is given:
1. **State predicates.** One ``git status --porcelain=v2 --branch`` call, one reflog
   tail read, and ctx-core's ``board.json`` cache when a scope exists (never its
   log). Deterministic and local. They catch a moment the prompt does not name: a
   push that just landed, a commit about to go onto main.
2. **Prompt routing, lexical.** The catalog's own regexes and phrases, over the
   clauses whose state gate is open. It abstains by default: no match, no line.
3. **Narrowing, ``ROLE_X_JEV``.** The seam a typed classifier (Jev) plugs into
   later. v1 ships only ``off``, which keeps stage 2's set. A narrower may drop
   candidates and never add one.
Then at most ``max_lines`` lines in ``max_chars`` characters. No persona lines, no
entity list, and nothing at all when nothing fires.

Loaded by ``role-x.py`` by file path (the hooks run Python with ``-I``, which keeps
this directory off ``sys.path``). Every failure raises; the caller prints nothing.
"""
from __future__ import annotations

import importlib.util
import os
import re
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
CLAUSE_KEYS = frozenset({"state", "prompt", "phrases"})
KINDS = frozenset({"primitive", "skill", "convention"})
STATUSES = frozenset({"routed", "judgment"})
SIGNATURE_TOOLS = frozenset({"Bash", "Skill", "Read", "Write", "mcp"})


class CatalogError(ValueError):
    """The catalog is missing, malformed, or names something that does not exist."""


# --------------------------------------------------------------------------
# catalog


@dataclass(frozen=True)
class Clause:
    state: tuple[str, ...]
    patterns: tuple[re.Pattern[str], ...]

    @property
    def has_prompt(self) -> bool:
        return bool(self.patterns)


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

    @property
    def routed(self) -> bool:
        return self.status == "routed"


@dataclass(frozen=True)
class Catalog:
    reflexes: tuple[Reflex, ...]
    max_lines: int
    max_chars: int


def phrase_pattern(phrase: str) -> re.Pattern[str]:
    """A literal phrase, case-insensitive, not inside a longer word."""
    return re.compile(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", re.IGNORECASE)


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
    entries = raw.get("reflexes")
    if not isinstance(entries, list) or not entries:
        raise CatalogError("reflexes must be a non-empty list")
    seen: set[str] = set()
    out = [_parse_entry(e, i, seen) for i, e in enumerate(entries)]
    return Catalog(reflexes=tuple(out), max_lines=max_lines, max_chars=max_chars)


def _str_list(value: Any, what: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        raise CatalogError(f"{what} must be a list of non-empty strings")
    return value


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


def _parse_entry(e: Any, index: int, seen: set[str]) -> Reflex:
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
        pats: list[re.Pattern[str]] = []
        for rx in _str_list(c.get("prompt"), f"{rid}: prompt"):
            try:
                pats.append(re.compile(rx, re.IGNORECASE))
            except re.error as exc:
                raise CatalogError(f"{rid}: bad regex {rx!r}: {exc}") from exc
        phrases = _str_list(c.get("phrases"), f"{rid}: phrases")
        phrases_all.extend(phrases)
        pats.extend(phrase_pattern(p) for p in phrases)
        if not state and not pats:
            raise CatalogError(f"{rid}: a clause needs a state predicate or a prompt pattern")
        clauses.append(Clause(state=tuple(state), patterns=tuple(pats)))
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
    )


# --------------------------------------------------------------------------
# state: read once, lazily, and never more than once per route


@dataclass
class GitState:
    ok: bool = False
    branch: str | None = None  # None when detached or unknown
    oid: str | None = None
    upstream: str | None = None
    ahead: int | None = None
    staged: int = 0


def parse_porcelain_v2(text: str) -> GitState:
    g = GitState(ok=True)
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
    #: How many times each source was actually read (the budget test reads this).
    reads: dict[str, int] = field(default_factory=dict)

    def _count(self, source: str) -> None:
        self.reads[source] = self.reads.get(source, 0) + 1

    @property
    def git(self) -> GitState:
        if self._git is None:
            self._count("git")
            env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0", "LC_ALL": "C"}
            try:
                p = self.run(
                    ["git", "-C", str(self.cwd), "status", "--porcelain=v2", "--branch",
                     "--untracked-files=no"],
                    capture_output=True, text=True, timeout=GIT_TIMEOUT_S, env=env)
                self._git = parse_porcelain_v2(p.stdout) if p.returncode == 0 else GitState()
            except (OSError, subprocess.SubprocessError):
                self._git = GitState()
        return self._git

    @property
    def peer(self) -> tuple[bool, str]:
        """(a live peer shares this branch or cwd, the fact to show), from the ctx
        board cache. The log is never read: only ctx's own ``load_board``."""
        if self._peer is None:
            self._count("board")
            self._peer = (False, "")
            ctx = self.ctx_loader()
            if ctx is not None:
                self._peer = _live_peer(ctx, self.cwd, self.session_id, self.now)
        return self._peer


def _live_peer(ctx: Any, cwd: Path, session_id: str, now: float) -> tuple[bool, str]:
    scope = ctx.resolve_scope(str(cwd))
    if scope is None:
        return False, ""
    try:
        board = ctx.load_board(scope, cap=ctx.HOOK_BOARD_CAP)
    except ctx.BoardTooBig:
        return False, ""
    if not board:
        return False, ""
    flat = getattr(ctx, "_flat", str)
    me = scope.where
    my_cwd, my_repo = flat(me.cwd), flat(me.common_dir)
    my_branch = flat(me.branch) if me.branch else None
    best = None
    for r in (board.get("sessions") or {}).values():
        if not isinstance(r, dict) or r.get("session_id") == session_id:
            continue
        same_branch = bool(my_branch) and r.get("repo") == my_repo and r.get("branch") == my_branch
        if not (same_branch or r.get("cwd") == my_cwd) or not ctx.is_live(r, now):
            continue
        if best is None or str(r.get("last_ts")) > str(best.get("last_ts")):
            best = r
    if best is None:
        return False, ""
    who = f"session {str(best.get('session_id'))[:8]}"
    if best.get("paseo_agent_id"):
        who += f" (Paseo agent {str(best['paseo_agent_id'])[:16]})"
    age_min = max(0, int((now - ctx.parse_ts(best["last_ts"])) // 60))
    branch = str(best.get("branch") or "-")[:60]
    return True, f"ctx board: {who} is live on `{branch}`, last event {age_min} min ago"


# --------------------------------------------------------------------------
# state predicates: name -> (held?, fact shown when a state clause fires)


def _branch_pushed_recently(s: State) -> tuple[bool, str]:
    """HEAD is a non-default branch, level with its upstream, and the upstream's
    reflog says its last update was a push of this very commit, minutes ago. (The
    spec's pushed_pr_without_watcher also needs the PR number and p9's watcher
    state, which come from the SessionStart state cache, a later phase.)"""
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


STATE_PREDICATES: dict[str, Callable[[State], tuple[bool, str]]] = {
    "branch_pushed_recently": _branch_pushed_recently,
    "on_default_branch": _on_default_branch,
    "staged_on_default_branch": _staged_on_default_branch,
    "live_peer_on_branch": _live_peer_on_branch,
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
        """The keys to keep. Anything returned that was not offered is ignored."""


class Off:
    """``ROLE_X_JEV=off`` (v1's only stage 3): keep everything stage 2 kept."""

    name = "off"

    def narrow(self, prompt: str, candidates: Sequence[Candidate]) -> set[str]:
        return {c.key for c in candidates}


#: A typed classifier (Jev, spec §5.2 stage 3) registers here under its
#: ROLE_X_JEV value. It sees only the clauses stages 1-2 kept, and may abstain.
NARROWERS: dict[str, Callable[[], Narrower]] = {"off": Off}


def get_narrower(name: str | None = None) -> Narrower:
    chosen = name if name is not None else os.environ.get(JEV_ENV, "off")
    return NARROWERS.get(chosen, Off)()


# --------------------------------------------------------------------------
# routing and rendering

#: How a reflex fired, best first.
VIA_RANK = {"state+prompt": 0, "state": 1, "prompt": 2}


@dataclass(frozen=True)
class Fired:
    reflex: Reflex
    via: str
    facts: tuple[str, ...]

    @property
    def sort_key(self) -> tuple[int, int, int]:
        return (VIA_RANK[self.via], self.reflex.priority, self.reflex.index)


@dataclass
class Routed:
    fired: list[Fired]
    predicates_true: list[str]
    stage_ms: dict[str, float]


def normalize_prompt(prompt: str) -> str:
    table = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"'})
    return " ".join(prompt.translate(table).split())


def _ms(t0: float) -> float:
    return round((time.monotonic() - t0) * 1000, 1)


def route_detail(prompt: str, state: State, catalog: Catalog,
                 narrower: Narrower | None = None) -> Routed:
    """Every routed reflex that fires, best first, with what decided it."""
    text = normalize_prompt(prompt)
    if not text:
        return Routed([], [], {})
    narrower = narrower or get_narrower()
    held: dict[str, tuple[bool, str]] = {}

    def check(name: str) -> tuple[bool, str]:
        if name not in held:
            held[name] = STATE_PREDICATES[name](state)
        return held[name]

    t0 = time.monotonic()
    gated: list[Candidate] = []  # stage 1: clauses whose state gate is open
    for r in catalog.reflexes:
        if not r.routed:
            continue
        for i, c in enumerate(r.clauses):
            facts: list[str] = []
            for name in c.state:  # in order, stopping at the first that fails
                ok, fact = check(name)
                if not ok:
                    break
                if fact:
                    facts.append(fact)
            else:
                gated.append(Candidate(f"{r.id}#{i}", r, c, tuple(facts)))
    state_ms = _ms(t0)
    t1 = time.monotonic()  # stage 2: the prompt, for clauses that ask it anything
    kept = [c for c in gated
            if not c.clause.has_prompt or any(p.search(text) for p in c.clause.patterns)]
    prompt_ms = _ms(t1)
    t2 = time.monotonic()  # stage 3: narrow only
    keep = narrower.narrow(text, kept) if kept else set()
    kept = [c for c in kept if c.key in keep]
    narrow_ms = _ms(t2)
    best: dict[str, Fired] = {}
    for c in kept:
        via = ("state+prompt" if c.clause.has_prompt else "state") if c.clause.state else "prompt"
        f = Fired(c.reflex, via, c.facts)
        if c.reflex.id not in best or f.sort_key < best[c.reflex.id].sort_key:
            best[c.reflex.id] = f
    return Routed(
        fired=sorted(best.values(), key=lambda f: f.sort_key),
        predicates_true=sorted(n for n, (ok, _) in held.items() if ok),
        stage_ms={"state": state_ms, "prompt": prompt_ms, "narrow": narrow_ms},
    )


def route(prompt: str, state: State, catalog: Catalog, narrower: Narrower | None = None) -> list[Fired]:
    return route_detail(prompt, state, catalog, narrower).fired


def _sentence(fact: str) -> str:
    return fact[:1].upper() + fact[1:] if fact[:1].isalpha() else fact


def render_line(f: Fired) -> str:
    tag = f" [{f.reflex.primitive}]" if f.reflex.primitive else ""
    lead = "; ".join(_sentence(x) if i == 0 else x for i, x in enumerate(f.facts))
    return f"- {lead + '. ' if lead else ''}{f.reflex.line}{tag}"


def render(fired: Sequence[Fired], max_lines: int, max_chars: int) -> tuple[str, list[Fired]]:
    """The block and the reflexes in it. Empty when nothing fits: never a bare header."""
    out, shown, used, seen = [HEADER], [], len(HEADER), set()
    for f in fired:
        if len(shown) >= max_lines:
            break
        if f.reflex.line in seen:
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
        state: State | None = None, narrower: Narrower | None = None) -> tuple[str, dict[str, Any]]:
    """The whole reflex path: (text to print, the event record's fields)."""
    started = time.monotonic()
    catalog = catalog or load_catalog()
    state = state or State(cwd=cwd, session_id=session_id)
    narrower = narrower or get_narrower()
    routed = route_detail(prompt, state, catalog, narrower)
    text, shown = render(routed.fired, catalog.max_lines, catalog.max_chars)
    shown_ids = {f.reflex.id for f in shown}
    meta = {
        "selected": [f.reflex.id for f in shown],
        "via": {f.reflex.id: f.via for f in shown},
        "cut": [f.reflex.id for f in routed.fired if f.reflex.id not in shown_ids],
        "predicates_true": routed.predicates_true,
        "jev": narrower.name,
        "bytes": len(text.encode("utf-8")),
        "reads": dict(state.reads),
        "stage_ms": routed.stage_ms,
        "ms": _ms(started),
    }
    return text, meta

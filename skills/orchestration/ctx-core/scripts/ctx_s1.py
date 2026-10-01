"""ctx System 1: one decision function, applied at every hook stage.

For each hook event: build a cheap key from the event payload and the session
(paths in tool_input, the branch, prompt terms, a PR number), look the keys up
in the per-scope cache System 2 wrote (ctx_s2.py), and inject the best cached
claims only if their score clears the stage's floor. Abstaining is the default:
no key, no candidate, below the floor, already injected, over a cap, or over
the budget all end in no output.

    stage          hook                                   keys                      at most
    session-start  SessionStart startup|resume|clear      branch                    5 claims, 1,500 chars, once per start
    compact        SessionStart compact                   claims already received,  5, 1,500; the one stage that repeats
                                                          re-ranked by branch
    prompt         UserPromptSubmit                       prompt words, tickets,    3, 1,500
                                                          PR refs, paths, branch
    pre-edit       PreToolUse Edit|Write|MultiEdit|       the file path             2, 600; each path once; 10 a session
                   NotebookEdit
    post-read      PostToolUse Read|Grep|Glob             the path read             2, 600; each path once; 10 a session
    post-bash      PostToolUse Bash                       git push -> branch;       2, 600; each path once; 10 a session
                                                          gh pr ... -> PR; paths
                                                          `cat`/`sed`/`rg` read
    subagent       SubagentStart                          the parent's claims,      3, 1,000; once per subagent; none for
                                                          branch                    reviewer agent types
    post-compact   PostCompact                            (measurement only: which injected ids the summary kept)

Across stages: a claim goes out at most once per session (compact excepted) and
at most 30 claims per session. Tool stages abstain inside a subagent.

Output is `hookSpecificOutput.additionalContext`: a `[ctx claims]` header and
one line per claim, each a copy of a source field (an entity's core_claim, a
spec's lede, a PR's title and state, a memory rule's description, quoted) with
its source id. The gate writes no instruction of its own: the header states what
the lines are, and a memory rule is quoted as data. (A copied field can still
be worded as advice; the phase-0 spike found imperative hook text reads as
prompt injection, which is why the framing stays factual.)

Every decision, inject or abstain, is appended to the scope's decisions log
(`s1-decisions.jsonl`): stage, key kinds, the top candidates with scores, the
floor, the outcome and why, bytes and latency. No prompt text and no raw key is
written there.

Floors and weights come from `references/s1-params.json` (or CTX_S1_PARAMS).
A stage with no floor abstains on everything; `ctx-s1 tune` fits floors on the
E1 replay and a reviewed change ships them.

No network and no model call on this path. No subprocess either, except
ctx-core's own bounded, killed-on-deadline git fallback for scope resolution
when GIT_DIR, GIT_WORK_TREE or GIT_COMMON_DIR redirect git, or for a reftable
HEAD (ctx.locate). Imports: ctx (stdlib), ctx_keys, fcntl/json/os/time.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import time
from pathlib import Path

import ctx
import ctx_keys as K

TYPE_CHECKING = False
if TYPE_CHECKING:
    from typing import Any, Callable, Dict, List, Optional, Set, Tuple

SCHEMA = 1
HEADER = "[ctx claims]"
SESSION_MAX = 30
LOG_NAME = "s1-decisions.jsonl"
LOG_ROTATE = 8 << 20
STATE_DIR = "s1-sessions"
STATE_LOCK_S = 0.020
TOP_LOGGED = 5
OPENED_KEEP = 200
#: Time an injection must still have for the save, the log line and the print.
DELIVERY_MARGIN_S = 0.008
PROMPT_CAP = 8000
#: Unique prompt words kept, in order; a stage's `max_terms` uses the first N.
PROMPT_TERMS = 120
DEFAULT_MAX_TERMS = 60

#: The stage table. `tools` is the matcher the registration uses; `event` the
#: hook event name the output must carry. Budgets are characters of output.
STAGES: Dict[str, Dict[str, Any]] = {
    "session-start": {"event": "SessionStart", "max": 5, "budget": 1500, "deadline_ms": 300,
                      "matcher": "startup|resume|clear"},
    "compact": {"event": "SessionStart", "max": 5, "budget": 1500, "deadline_ms": 300, "matcher": "compact",
                "reoffer": True},
    "prompt": {"event": "UserPromptSubmit", "max": 3, "budget": 1500, "deadline_ms": 300},
    "pre-edit": {"event": "PreToolUse", "max": 2, "budget": 600, "deadline_ms": 70, "per_session": 10,
                 "path_once": True, "matcher": "Edit|Write|MultiEdit|NotebookEdit"},
    "post-read": {"event": "PostToolUse", "max": 2, "budget": 600, "deadline_ms": 70, "per_session": 10,
                  "path_once": True, "matcher": "Read|Grep|Glob"},
    "post-bash": {"event": "PostToolUse", "max": 2, "budget": 600, "deadline_ms": 70, "per_session": 10,
                  "path_once": True, "matcher": "Bash"},
    "subagent": {"event": "SubagentStart", "max": 3, "budget": 1000, "deadline_ms": 150, "reoffer": True},
    "post-compact": {"event": "PostCompact", "max": 0, "budget": 0, "deadline_ms": 150, "measure_only": True},
}
TOOL_STAGES = ("pre-edit", "post-read", "post-bash")
INJECT_STAGES = tuple(s for s in STAGES if not STAGES[s].get("measure_only"))
#: compact and subagent only re-offer claims the session already received, so
#: on their own (no other stage on) they never inject: E1 cannot judge them
#: alone, tune does not fit them, and E2 has no one-stage arm for them.
ALONE_STAGES = tuple(s for s in INJECT_STAGES if not STAGES[s].get("reoffer"))

#: Agent types that must stay independent of the parent's claims (Cross-Review
#: strata, adversarial reviewers). Matched against SubagentStart's agent_type,
#: which carries no prompt, so this goes by name. `Explore` is on it because the
#: cross-review skill runs Stratum B as an Explore subagent: every Explore agent
#: gets no brief, the price of not biasing a reviewer.
REVIEWER_RE = re.compile(r"review|devil|advocate|thermo|audit|critic|stratum|judge|verif|red-?team|^explore$",
                         re.I)
#: A cached claim about a live session or an open PR goes stale: past these
#: ages (of the cache build) it is not offered. Specs, entities and memory rules
#: carry no "as of".
MAX_AGE_S = {"session": 6 * 3600, "pr": 24 * 3600}
#: Prompts the harness writes, not the user.
HARNESS_PROMPT_RE = re.compile(r"^\s*<(task-notification|local-command|command-|system-reminder|bash-)", re.I)
BARE_PR_RE = re.compile(r"(?:\bPR\s*#?|(?<![\w/])#)(\d{2,6})\b", re.I)

DEFAULT_PARAMS: Dict[str, Any] = {
    "version": "v0-abstain",
    "channel_weights": {"p": 1.0, "d": 0.4, "f": 0.6, "b": 0.5, "pr": 1.0, "t": 1.0, "w": 1.0, "s": 1.0},
    "type_weights": {},
    "stages": {},
}


class Busy(Exception):
    """The session state lock was held past its budget."""


# --------------------------------------------------------------------------
# Parameters

def params_path() -> Path:
    env = os.environ.get("CTX_S1_PARAMS")
    if env:
        return Path(env)
    return Path(os.path.dirname(os.path.realpath(__file__))).parent / "references" / "s1-params.json"


def load_params() -> Dict[str, Any]:
    try:
        raw = json.loads(params_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dict(DEFAULT_PARAMS)
    out = dict(DEFAULT_PARAMS)
    out.update({k: raw[k] for k in ("version", "channel_weights", "type_weights", "stages") if k in raw})
    return out


def stage_cfg(stage: str, params: Dict[str, Any]) -> Dict[str, Any]:
    cfg = dict(STAGES[stage])
    cfg.update((params.get("stages") or {}).get(stage) or {})
    return cfg


# --------------------------------------------------------------------------
# The cache reader. Resolves `rank-current` once, then reads only that build.

class CacheReader:
    def __init__(self, store: Path):
        link = store / K.CACHE_LINK
        target = os.readlink(str(link))
        if "/" in target or not target.startswith(K.CACHE_PREFIX):
            raise ValueError("unexpected cache link target")
        self.dir = store / target
        self.meta = json.loads((self.dir / "meta.json").read_bytes())
        self.types = self.meta.get("types") or []
        try:
            self.built_at: Optional[float] = ctx.parse_ts(str(self.meta.get("built_at")))
        except (ValueError, IndexError):
            self.built_at = None
        self._post: Dict[str, Dict[str, Any]] = {}
        self._items: Dict[str, Dict[str, Any]] = {}

    @property
    def build_id(self) -> str:
        return str(self.meta.get("build_id") or "?")

    def postings(self, key: str) -> List[List[Any]]:
        b = K.bucket(key)
        shard = self._post.get(b)
        if shard is None:
            try:
                shard = json.loads((self.dir / "postings" / (b + ".json")).read_bytes())
            except FileNotFoundError:
                shard = {}
            self._post[b] = shard
        return shard.get(key) or []

    def item(self, idx: int) -> Dict[str, Any]:
        f = K.item_file(idx)
        shard = self._items.get(f)
        if shard is None:
            shard = json.loads((self.dir / "items" / (f + ".json")).read_bytes())
            self._items[f] = shard
        return shard[str(idx)]

    def type_of(self, code: int) -> str:
        return self.types[code] if 0 <= code < len(self.types) else "?"


# --------------------------------------------------------------------------
# Keys from one event

def _toplevel_for(abs_path: str, where, scope_id: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    """(keyable, top level of the repo the path is in). Under the session's top
    level it is the session's own, unless a nested repo sits in between (a
    `.git` on the way up: a few stats); otherwise it is found the way git does,
    no process. A path in no repo is keyable (as `~/...`); a path in another
    repo only when scopes.yaml puts that repo in the session's scope, so a read
    of a nested Stimulus checkout is not keyed, or logged, as this scope's."""
    top = getattr(where, "toplevel", None)
    d = os.path.dirname(abs_path)
    nested = None
    if top and (abs_path == top or abs_path.startswith(top.rstrip("/") + "/")):
        top_s = top.rstrip("/")
        while d and len(d) > len(top_s) and d.startswith(top_s + "/"):
            if os.path.lexists(os.path.join(d, ".git")):
                nested = d
                break
            d = os.path.dirname(d)
        if nested is None:
            return True, top
        d = nested
    else:
        while d and d != "/" and not os.path.isdir(d):
            d = os.path.dirname(d)
    loc = ctx.locate(d, timeout=0) if d and d != "/" else None
    if loc is None:
        # in no repo: keyable as `~/...`; but a nested `.git` we cannot read
        # (a git env override, a stale .git file) is a repo we cannot place
        return (nested is None), None
    if loc.common_dir == getattr(where, "common_dir", None):
        return True, loc.toplevel
    if not scope_id or ctx.load_scopes().by_repo.get(loc.common_dir) != scope_id:
        return False, None
    return True, loc.toplevel


def _path_keys_for(abs_path: str, where, scope_id: Optional[str] = None
                   ) -> Tuple[Dict[str, List[str]], Set[str], Optional[str]]:
    keys = K.empty_keys()
    mk = K.memory_key(abs_path)
    if mk:
        return keys, {mk}, None  # a memory file: nothing cites it by path
    keyable, top = _toplevel_for(abs_path, where, scope_id)
    rel = K.rel_to_repo(abs_path, top) if keyable else None
    if not rel or "crm/" in "/" + rel.lower():
        return keys, set(), None
    K.add_path(keys, rel)
    return keys, {"o:" + rel.lower()}, rel


def _merge(a: Dict[str, List[str]], b: Dict[str, List[str]]) -> None:
    for ch, ks in b.items():
        a.setdefault(ch, []).extend(ks)


def extract_keys(stage: str, data: Dict[str, Any], where, repo: Optional[str] = None,
                 scope_id: Optional[str] = None) -> Tuple[Dict[str, List[str]], Set[str], Optional[str], str]:
    """(keys, self objects, path key, label) for one hook payload. `self`
    objects are the event's own targets: an item whose object is the file being
    edited or read is never offered for it. The label is what the header names.
    `scope_id` admits paths in the scope's other repos; without it only the
    session's own repo keys."""
    keys = K.empty_keys()
    self_obj: Set[str] = set()
    path_key: Optional[str] = None
    branch = (getattr(where, "branch", None) or "").lower()
    label = ""
    if stage == "prompt":
        prompt = data.get("prompt") if isinstance(data.get("prompt"), str) else ""
        if not prompt.strip() or HARNESS_PROMPT_RE.match(prompt):
            return keys, self_obj, None, ""
        text = prompt[:PROMPT_CAP]
        tk = K.text_keys(text, words=False)
        tk["w"] = ["w:" + w for w in K.unique(K.terms(text))[:PROMPT_TERMS]]
        _merge(keys, tk)
        top = getattr(where, "toplevel", None)
        roots = [(top, repo or "")] if top else []
        for p in K.cited_paths(text, roots, cap=8):
            K.add_path(keys, p)
        if repo:
            keys["pr"] += ["pr:%s#%s" % (repo, n) for n in BARE_PR_RE.findall(text)]
        if branch and not branch.startswith("detached@"):
            keys["b"].append("b:" + branch)
        label = "this prompt"
    elif stage in ("pre-edit", "post-read"):
        ti = data.get("tool_input") if isinstance(data.get("tool_input"), dict) else {}
        p = ti.get("file_path") or ti.get("notebook_path") or ti.get("path") or ""
        if isinstance(p, str) and p:
            if not os.path.isabs(p) and isinstance(data.get("cwd"), str):
                p = os.path.join(data["cwd"], p)
            keys, self_obj, path_key = _path_keys_for(os.path.normpath(p), where, scope_id)
            label = path_key or ""
    elif stage == "post-bash":
        ti = data.get("tool_input") if isinstance(data.get("tool_input"), dict) else {}
        cmd = ti.get("command") if isinstance(ti.get("command"), str) else ""
        acts = K.bash_actions(cmd)
        labels = []
        search = K.bash_search_terms(cmd)
        if search:
            keys["s"] = ["w:" + w for w in search]
            labels.append("this search")
        for act, num, act_repo in acts:
            if act == "push" and branch and not branch.startswith("detached@"):
                keys["b"].append("b:" + branch)
                labels.append("branch " + branch)
            elif act.startswith("pr-"):
                if not num:
                    resp = data.get("tool_response")
                    out = resp.get("stdout") if isinstance(resp, dict) else (resp if isinstance(resp, str) else "")
                    m = K.PR_URL_RE.search(out or "")
                    num, act_repo = (m.group(2), m.group(1).lower()) if m else (None, act_repo)
                pr_repo = act_repo or repo  # -R / a URL names the repo; else the session's
                if num and pr_repo:
                    keys["pr"].append("pr:%s#%s" % (pr_repo, num))
                    labels.append("%s#%s" % (pr_repo, num))
                elif branch and not branch.startswith("detached@"):
                    keys["b"].append("b:" + branch)
                    labels.append("branch " + branch)
        for t in K.bash_read_targets(cmd, data.get("cwd") if isinstance(data.get("cwd"), str) else None, cap=3):
            k2, s2, rel = _path_keys_for(t, where, scope_id)
            _merge(keys, k2)
            self_obj |= s2
            if rel and path_key is None:
                path_key = rel
                labels.append(rel)
        label = ", ".join(labels[:2])
    elif stage in ("session-start", "compact", "subagent"):
        if branch and not branch.startswith("detached@"):
            keys["b"].append("b:" + branch)
        label = "branch " + branch if branch else ""
    return keys, self_obj, path_key, label


# --------------------------------------------------------------------------
# Session state: what this session already got. One small JSON file per
# session, read and rewritten in place under an flock.

def _state_path(store: Path, session_id: str, shadow: bool) -> Path:
    return store / STATE_DIR / ("%s%s.json" % (session_id, ".shadow" if shadow else ""))


def open_state(store: Path, session_id: str, shadow: bool = False, budget: float = STATE_LOCK_S
               ) -> Tuple[Tuple[int, Path], Dict[str, Any]]:
    """Lock the session's state and read it. The lock is a sibling `.lock`
    file; the state is only ever replaced whole (temp file, then rename), so a
    process killed mid-write leaves the previous state, never a torn one.
    Returns (handle, state); pass the handle to save_state or release_state."""
    d = store / STATE_DIR
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = _state_path(store, session_id, shadow)
    fd = os.open(str(path.with_suffix(".lock")), os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    end = time.monotonic() + max(0.0, budget)
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            if time.monotonic() >= end:
                os.close(fd)
                raise Busy()
            time.sleep(0.002)
            continue
        # housekeeping (ctx_s2.gc_sessions) may have unlinked the lock file
        # between our open and our lock: a lock on an orphan is no lock
        try:
            same = os.fstat(fd).st_ino == os.stat(str(path.with_suffix(".lock"))).st_ino
        except OSError:
            same = False
        if same:
            break
        os.close(fd)
        raise Busy()
    try:
        os.utime(fd)  # in use: housekeeping keeps a lock touched within its window
    except OSError:
        pass
    try:
        state = json.loads(path.read_bytes().decode("utf-8"))
        if not isinstance(state, dict):
            state = {}
    except FileNotFoundError:
        state = {}
    except (OSError, ValueError, UnicodeDecodeError):
        state = {}  # unreadable (hand-edited, disk error): start the session's record over
    state.setdefault("v", SCHEMA)
    state.setdefault("injected", {})
    state.setdefault("paths", {})
    state.setdefault("counts", {})
    state.setdefault("subagents", [])
    state.setdefault("opened", [])
    return (fd, path), state


def save_state(handle: Tuple[int, Path], state: Dict[str, Any]) -> None:
    fd, path = handle
    data = json.dumps(state, separators=(",", ":"), sort_keys=True).encode("utf-8")
    tmp = path.parent / (".%s.%d.tmp" % (path.name, os.getpid()))
    try:
        wfd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            view = memoryview(data)
            while view:
                view = view[os.write(wfd, view):]
        finally:
            os.close(wfd)
        os.replace(str(tmp), str(path))
    finally:
        os.close(fd)  # releases the lock


def release_state(handle: Tuple[int, Path]) -> None:
    try:
        os.close(handle[0])
    except OSError:
        pass


# --------------------------------------------------------------------------
# The decision

def _abstain(reason: str, **kw: Any) -> Dict[str, Any]:
    d = {"outcome": "abstain", "reason": reason, "injected": [], "bytes": 0, "text": ""}
    d.update(kw)
    return d


def render(stage: str, label: str, lines: List[str]) -> str:
    what = {
        "prompt": "Recorded facts in this scope that match this prompt",
        "pre-edit": "Recorded facts in this scope that cite %s" % label,
        "post-read": "Recorded facts in this scope that cite %s" % label,
        "post-bash": "Recorded facts in this scope linked to %s" % label,
        "session-start": "Recorded facts in this scope linked to %s" % label,
        "compact": "Claims this session received before compaction, ranked for %s" % label,
        "subagent": "Claims the parent session received",
    }[stage]
    return "%s %s:\n%s" % (HEADER, ctx._clip(what, 160), "\n".join(lines))


def claim_line(claim: str, source: str) -> str:
    # the source is provenance: kept whole up to a generous cap, so it can be followed
    return "- %s [%s]" % (ctx._clip(claim, 260), ctx._clip(source, 240))


def decide(stage: str, keys: Dict[str, List[str]], self_obj: Set[str], state: Dict[str, Any],
           reader: Optional[CacheReader], params: Dict[str, Any], label: str = "",
           path_key: Optional[str] = None, agent_id: Optional[str] = None, agent_type: str = "",
           mode: str = "gate", eligible: Optional[Callable[[int], bool]] = None,
           now: Optional[float] = None) -> Dict[str, Any]:
    """The one decision. Pure apart from reading the cache: it neither writes
    state nor logs. `mode` is "gate" (the real one), or an E1 arm: "always"
    (inject the best candidates whatever the floor and caps) or "never".
    With `now`, a session or PR claim from a cache older than MAX_AGE_S is not
    offered (the replay passes none: its snapshot has no clock).
    Returns the decision; `outcome` is "inject" or "abstain" (or "measure")."""
    cfg = stage_cfg(stage, params)
    key_kinds = {ch: len(ks) for ch, ks in keys.items() if ks}
    base = {"stage": stage, "key_kinds": key_kinds, "n_keys": sum(key_kinds.values()),
            "floor": cfg.get("floor"), "top": []}
    if mode == "never":
        return _abstain("arm-never", **base)
    if stage == "subagent" and REVIEWER_RE.search(agent_type or ""):
        return _abstain("independent-reviewer", **base)
    if stage == "subagent" and agent_id and agent_id in state.get("subagents", []):
        return _abstain("dedup", **base)
    # Candidates: from the cache by key, and for compact and subagent from the
    # claims this session already received.
    scores: Dict[str, float] = {}
    recs: Dict[str, Dict[str, Any]] = {}
    cw = params.get("channel_weights") or DEFAULT_PARAMS["channel_weights"]
    tw = params.get("type_weights") or {}
    injected = state.get("injected", {})
    stale = set()
    if reader is not None and now is not None and reader.built_at is not None:
        age = now - reader.built_at
        stale = {t for t, limit in MAX_AGE_S.items() if age > limit}
    if stage in ("compact", "subagent"):
        for iid, rec in injected.items():
            kind = iid.split(":", 1)[0]
            if now is not None and kind in MAX_AGE_S and (
                    kind in stale or now - float(rec.get("as_of") or rec.get("ts") or 0) > MAX_AGE_S[kind]):
                continue  # a session or PR claim that old (by its as-of time) is not offered again
            scores[iid] = float(rec.get("score") or 0.0)
            recs[iid] = {"id": iid, "claim": rec.get("claim", ""), "source": rec.get("source", ""),
                         "obj": rec.get("obj", []), "as_of_ts": rec.get("as_of")}
    if reader is not None:
        by_idx: Dict[int, float] = {}
        max_terms = int(cfg.get("max_terms") or DEFAULT_MAX_TERMS)
        for ch, ks in keys.items():
            w = float(cw.get(ch, 0.0))
            if not w or not ks:
                continue
            if ch in ("w", "s"):
                ks = ks[:max_terms]
            # in order, once each: a set's order varies with the hash seed, and
            # float sums in another order can flip a near-tie
            for k in K.unique(ks):
                for idx, s, tc in reader.postings(k):
                    if eligible is not None and not eligible(idx):
                        continue
                    if stale and reader.type_of(tc) in stale:
                        continue
                    t = float(tw.get(reader.type_of(tc), 1.0))
                    by_idx[idx] = by_idx.get(idx, 0.0) + w * s * t
        if stage in ("compact", "subagent"):
            # compact and subagent offer only what the session already received
            # (the subagent's header says so); the cache only reorders it
            for idx, s in by_idx.items():
                it = reader.item(idx)
                if it["id"] in scores:
                    scores[it["id"]] += s
        else:
            for idx, s in sorted(by_idx.items(), key=lambda kv: (-kv[1], kv[0]))[:64]:
                it = reader.item(idx)
                iid = it["id"]
                scores[iid] = scores.get(iid, 0.0) + s
                if iid not in recs:  # as of this build: a re-offer later ages from here
                    recs[iid] = dict(it, as_of_ts=reader.built_at)
    if not scores:
        return _abstain("no-key" if not base["n_keys"] and stage not in ("compact", "subagent")
                        else "no-candidate", **base)
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    base["top"] = [[iid, round(s, 4)] for iid, s in ranked[:TOP_LOGGED]]
    # Never the event's own file, never a file this session already opened
    # (a read the tool stages saw), and never twice a session (compact excepted).
    opened = set(state.get("opened") or [])
    pool = []
    for iid, s in ranked:
        obj = set(recs[iid].get("obj") or [])
        if obj & self_obj or (obj & opened and stage not in ("compact", "subagent")):
            continue
        # compact re-injects what the session had; a subagent starts empty, so
        # the parent's claims are exactly what it may get
        if stage not in ("compact", "subagent") and iid in injected:
            continue
        pool.append((iid, s))
    if not pool:
        return _abstain("dedup", **base)
    if mode != "always":
        floor = cfg.get("floor")
        if floor is None:
            return _abstain("no-floor", **base)
        pool = [(iid, s) for iid, s in pool if s >= float(floor)]
        if not pool:
            return _abstain("below-floor", **base)
        if cfg.get("path_once") and path_key and path_key in state.get("paths", {}).get(stage, []):
            return _abstain("path-seen", **base)
        used = state.get("counts", {}).get(stage, 0)
        if cfg.get("per_session") and used >= int(cfg["per_session"]):
            return _abstain("stage-cap", **base)
        total = state.get("counts", {}).get("total", 0)
        # compact re-injects what the session had, and a subagent's claims go
        # into its own context: neither spends the session's allowance
        room = SESSION_MAX - total if stage not in ("compact", "subagent") else cfg["max"]
        if room <= 0:
            return _abstain("session-cap", **base)
        pool = pool[: min(int(cfg["max"]), room)]
    else:
        pool = pool[: int(cfg["max"]) or 3]
    lines, chosen = [], []
    budget = int(cfg.get("budget") or 0)
    for iid, s in pool:
        rec = recs[iid]
        line = claim_line(rec.get("claim", ""), rec.get("source", ""))
        if len(render(stage, label, lines + [line])) > budget and mode != "always":
            continue  # a line that does not fit is dropped, not cut
        lines.append(line)
        chosen.append((iid, s, rec))
    if not chosen:
        return _abstain("budget", **base)
    text = render(stage, label, lines)
    base.update({"outcome": "inject", "reason": "cleared-floor" if mode != "always" else "arm-always",
                 "injected": [iid for iid, _, _ in chosen], "bytes": len(text.encode("utf-8")), "text": text,
                 "_chosen": chosen})
    return base


def record(state: Dict[str, Any], stage: str, decision: Dict[str, Any], path_key: Optional[str],
           agent_id: Optional[str], now: float, opened: Optional[Set[str]] = None) -> None:
    """Update session state: what the session opened (the read stages see it,
    whatever they decide), and for an injection the dedup, caps and path seen."""
    if opened and stage in ("post-read", "post-bash"):
        lst = state.setdefault("opened", [])
        lst.extend(o for o in sorted(opened) if o not in lst)
        del lst[:-OPENED_KEEP]
    counts = state.setdefault("counts", {})
    if stage == "subagent" and agent_id:
        state.setdefault("subagents", []).append(agent_id)
        del state["subagents"][:-64]
    if decision.get("outcome") != "inject":
        return
    if stage == "subagent":
        return  # the claims went into the subagent's context, not this session's
    for iid, s, rec in decision.get("_chosen", []):
        if stage == "compact" and iid in state["injected"]:
            continue
        state["injected"][iid] = {"stage": stage, "ts": round(now, 3), "score": round(s, 4),
                                  "as_of": rec.get("as_of_ts"),
                                  "claim": rec.get("claim", ""), "source": rec.get("source", ""),
                                  "obj": list(rec.get("obj") or [])[:4]}
    n = len(decision.get("_chosen", []))
    counts[stage] = counts.get(stage, 0) + 1
    if stage != "compact":
        counts["total"] = counts.get("total", 0) + n
    if path_key and STAGES[stage].get("path_once"):
        seen = state.setdefault("paths", {}).setdefault(stage, [])
        seen.append(path_key)
        del seen[:-64]


# --------------------------------------------------------------------------
# The decisions log

def log_path(store: Path) -> Path:
    return store / LOG_NAME


def append_log(store: Path, rec: Dict[str, Any]) -> None:
    path = log_path(store)
    try:
        if path.stat().st_size >= LOG_ROTATE:
            os.replace(str(path), str(path) + ".1")
    except FileNotFoundError:
        pass
    line = (json.dumps(rec, separators=(",", ":"), sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    fd = os.open(str(path), os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        os.write(fd, line)
    finally:
        os.close(fd)


def log_record(decision: Dict[str, Any], data: Dict[str, Any], scope_id: str, build: str,
               params: Dict[str, Any], shadow: bool, ms: float, path_key: Optional[str]) -> Dict[str, Any]:
    rec = {
        "v": SCHEMA, "ts": ctx.now_ts(), "scope": scope_id, "stage": decision.get("stage"),
        "mode": "shadow" if shadow else "inject", "session": data.get("session_id"),
        "outcome": decision.get("outcome"), "reason": decision.get("reason"),
        "key_kinds": decision.get("key_kinds", {}), "n_keys": decision.get("n_keys", 0),
        "top": decision.get("top", []), "floor": decision.get("floor"), "params": params.get("version"),
        "build": build, "injected": decision.get("injected", []), "bytes": decision.get("bytes", 0),
        "ms": round(ms, 2),
    }
    for k in ("prompt_id", "tool_use_id", "agent_id", "tool_name", "source"):
        v = data.get(k)
        if isinstance(v, str) and ctx.SESSION_ID_RE.match(v):
            rec[k] = v
    if path_key and ctx.guard_ok(path_key) and "crm/" not in "/" + path_key.lower():
        rec["path"] = ctx._clip(path_key, 200)
    return rec


# --------------------------------------------------------------------------
# The hook entry's work. ctx_s1_hook.py wraps this with the deadline and exit 0.

STAGE: str = "start"


def enabled(stage: str, env: Optional[Dict[str, str]] = None) -> bool:
    e = os.environ if env is None else env
    if e.get("CTX_S1") != "1":
        return False
    wanted = {s.strip() for s in (e.get("CTX_S1_STAGES") or "").split(",") if s.strip()}
    return stage in wanted or "all" in wanted


def run_stage(stage: str, raw: str, deadline: float, now: Optional[float] = None,
              emit: Optional[Callable[[str], None]] = None) -> str:
    """Handle one hook event for one stage. Returns stdout ("" for none).
    With `emit`, the output is handed to it as soon as the state is saved,
    before the log line, so a deadline that fires during the log does not cost
    a claim the state already lists. Raises on anything unexpected; the caller
    turns that into exit 0."""
    global STAGE
    t0 = time.monotonic()
    STAGE = "parse"
    if stage not in STAGES or not enabled(stage):
        return ""
    data = json.loads(raw) if raw.strip() else None
    if not isinstance(data, dict):
        return ""
    session_id = data.get("session_id")
    cwd = data.get("cwd")
    if not isinstance(session_id, str) or not ctx.SESSION_ID_RE.match(session_id):
        return ""
    if not isinstance(cwd, str) or not os.path.isabs(cwd):
        return ""
    if stage == "compact" and data.get("source") != "compact":
        return ""
    if stage == "session-start" and data.get("source") == "compact":
        return ""
    left = lambda: deadline - time.monotonic()
    STAGE = "scope"
    scope = ctx.resolve_scope(cwd, timeout=max(0.0, left() - 0.03))
    if scope is None:
        return ""
    shadow = os.environ.get("CTX_S1_SHADOW") == "1"
    params = load_params()
    agent_id = data.get("agent_id") if isinstance(data.get("agent_id"), str) else None
    now = time.time() if now is None else now
    STAGE = "keys"
    repo = K.repo_name(scope.where.common_dir)
    keys, self_obj, path_key, label = extract_keys(stage, data, scope.where, repo, scope.id)
    reader: Optional[CacheReader] = None
    decision: Dict[str, Any]
    build = "-"
    if stage in TOOL_STAGES and agent_id:
        # a subagent's tool call: not this session's context, so its state is
        # not touched (no lock taken, nothing recorded as opened or injected)
        append_log(scope.store, log_record(_abstain("in-subagent", stage=stage), data, scope.id, build,
                                           params, shadow, (time.monotonic() - t0) * 1000, path_key))
        return ""
    STAGE = "state"
    try:
        handle, state = open_state(scope.store, session_id, shadow)
    except Busy:
        decision = _abstain("state-busy", stage=stage)
        append_log(scope.store, log_record(decision, data, scope.id, build, params, shadow,
                                           (time.monotonic() - t0) * 1000, path_key))
        return ""
    out = ""
    saved = False
    try:
        STAGE = "decide"
        if stage == "post-compact":
            summary = data.get("compact_summary") if isinstance(data.get("compact_summary"), str) else ""
            kept = [iid for iid, rec in state.get("injected", {}).items()
                    if rec.get("source") and rec["source"] in summary]
            decision = {"stage": stage, "outcome": "measure", "reason": "post-compact",
                        "injected": [], "kept": kept, "bytes": 0,
                        "key_kinds": {}, "n_keys": 0, "top": [], "floor": None}
        else:
            try:
                reader = CacheReader(scope.store)
                build = reader.build_id
            except (OSError, ValueError):
                reader = None
            if reader is None and stage not in ("compact", "subagent"):
                decision = _abstain("no-cache", stage=stage)
            elif left() <= 0.005:
                decision = _abstain("deadline", stage=stage)
            else:
                decision = decide(stage, keys, self_obj, state, reader, params, label=label,
                                  path_key=path_key, agent_id=agent_id,
                                  agent_type=str(data.get("agent_type") or ""), now=now)
        # An injection that cannot be delivered in time is an abstention, and is
        # decided BEFORE anything is recorded: state only ever lists claims the
        # hook went on to print (a kill between the save and the print is the
        # one gap left, and it errs toward not repeating a claim).
        if decision.get("outcome") == "inject" and not shadow and left() <= DELIVERY_MARGIN_S:
            decision = _abstain("deadline", stage=stage, top=decision.get("top", []))
        STAGE = "record"
        record(state, stage, decision, path_key, agent_id, now, opened=self_obj)
        save_state(handle, state)
        saved = True
        if decision.get("outcome") == "inject" and not shadow:
            out = json.dumps({"hookSpecificOutput": {"hookEventName": STAGES[stage]["event"],
                                                     "additionalContext": decision["text"]}},
                             ensure_ascii=False)
    finally:
        if not saved:
            release_state(handle)
    if out and emit is not None:
        STAGE = "emit"
        emit(out)
    STAGE = "log"
    rec = log_record(decision, data, scope.id, build, params, shadow, (time.monotonic() - t0) * 1000, path_key)
    if decision.get("kept") is not None:
        rec["kept"] = decision["kept"]
    append_log(scope.store, rec)
    return out

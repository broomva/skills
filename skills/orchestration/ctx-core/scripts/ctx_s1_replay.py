"""E1, part 1: turn real transcripts into a replay set with counterfactual truth.

    ctx-s1 snapshot [--out DIR] [--scope broomva] [--days 14]

The snapshot is PRIVATE: it is written under ~/.local/state/ctx/<scope>/e1/
by default and refused anywhere inside a git checkout. Only E1's aggregate
reports are committed; CI replays a synthetic fixture
(tests/test_s1_e1_synthetic.py).

Reads the scope's main transcripts under ~/.claude/projects (subagent files
only through their parent), and turns each into the hook events System 1
would have seen, in order:

    session-start  the session's first record
    prompt         each human prompt (harness-written ones are skipped)
    pre-edit       each Edit / Write / MultiEdit / NotebookEdit tool call
    post-read      each Read / Grep / Glob tool call
    post-bash      each Bash tool call
    subagent       each Agent / Task tool call, with the subagent's own fetches
    compact        each compaction summary

Keys come from ctx_s1.extract_keys on a payload rebuilt from the transcript:
the same code the hook runs.

GROUND TRUTH IS COUNTERFACTUAL. An item was *needed* in a session when the
agent fetched it on its own: its first tool call in that session that opened
the item's object (a Read or shell read of its file, `kg load` naming it,
`gh pr view|diff|checks N`). Nothing had injected it. Two masks keep this from
being tautological (memory ground-truth-from-one-arm-is-tautological):
  - pointed: a fetch after any injected text (a hook's output, the instruction
    files, MEMORY.md's index, a skill body, an @-mention, a queued command)
    named the item's object, by path, entity slug or file stem (the same
    recognizer as the echo check), is not counterfactual; the item is never
    "needed" in that session, and an injection of it there is reported as
    unjudgeable, not scored. A subagent's fetches are masked the same way by
    its own prompt and its own injected text;
  - authored: a fetch of a file the session itself wrote earlier is not
    retrieval.
Items created after an event are not candidates for it (the replay's
`eligible`: to the second, or for a creation known only to the day, from 36 h
after that UTC midnight unless the file's mtime is sooner), so a spec written
later cannot score.

The snapshot stays on the owner's machine, and its keys are hashed as well:
every key and object id is replaced by HMAC-SHA256 under a local salt
(~/.config/ctx/s1-eval-salt), keeping only its channel, and no claim text,
prompt, path or session id is written. That is a second line, not the first:
keys keep each event's order (the live gate cuts prompt words at `max_terms`
in that order), and an ordered sequence of hashed words is open to frequency
analysis, so the file is not fit to publish. Items keep their type, claim
length, creation and edit times, and hashed keys; events keep their stage,
position, time, hashed keys and truth. PR items and every repo's items are
kept, so the replay's item set is the live cache's. BM25 and System 1 work on
hashed keys exactly as on raw ones, so the replay decides as the live gate
would have on the same cache. What it cannot replay is a change to how keys
are made (tokenisation); that needs a new snapshot from the raw transcripts.
"""

from __future__ import annotations

import gzip
import hashlib
import hmac
import json
import os
import re
import time
import sys
from collections import namedtuple
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import ctx  # noqa: E402
import ctx_keys as K
import ctx_s1
import ctx_s2

TYPE_CHECKING = False
if TYPE_CHECKING:
    from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

SNAPSHOT_SCHEMA = 5
EXTRACTOR_VERSION = 5
DEFAULT_DAYS = 14
#: How far after an event a fetch counts as one the event could have pre-empted,
#: in tool calls. A tool stage's claim lands next to one tool result; a prompt's,
#: a start's or a compaction's bears on the turn that follows.
DEFAULT_WINDOW = 10
TURN_WINDOW = 30
SUB_WINDOW = 20
#: Sessions split by start time: the first 60% train (tune fits on it), the next
#: 20% validation (tune accepts on it), the last 20% test (nothing looks at it
#: until the spec's bar is checked there).
TRAIN_SHARE = 0.6
VALIDATION_SHARE = 0.2
DAY = 86400
#: A creation time known only to the day (a dated file name, a `created:`
#: date) is UTC midnight; the item may have been written up to a day and a
#: half later in the owner's time zone, so the replay makes it a candidate only
#: from then, or from its file's mtime if that is earlier.
DATE_ONLY_SLACK = 36 * 3600
HASH_HEX = 12
SUB_FETCH_CAP = 40
Where = namedtuple("Where", "cwd toplevel common_dir branch")

EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
READ_TOOLS = ("Read", "Grep", "Glob")
AGENT_TOOLS = ("Agent", "Task")
AGENT_ID_RE = re.compile(r"agentId:\s*([0-9a-f]{8,40})")
KG_PATH_RE = re.compile(r"research/entities/([\w./-]+?)\.md\b")
SPECS_PATH_RE = re.compile(r"\b((?:docs/(?:specs|plans|adrs))/[\w./-]+\.(?:md|html?))\b")
MEM_LINK_RE = re.compile(r"\]\(([\w.-]+\.md)\)")
MEM_PATH_RE = re.compile(r"/memory/([\w.-]+\.md)\b")
PR_OBJ_RE = re.compile(r"\b([a-z][\w.-]{1,40})#(\d{1,6})\b")


# --------------------------------------------------------------------------
# Salt and hashing

def salt_path() -> Path:
    return ctx.home() / ".config" / "ctx" / "s1-eval-salt"


def load_salt(create: bool = True) -> bytes:
    p = salt_path()
    try:
        return bytes.fromhex(p.read_text().strip())
    except (OSError, ValueError):
        if not create:
            raise
    p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    s = os.urandom(32)
    fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, s.hex().encode())
    finally:
        os.close(fd)
    return s


class Hasher:
    def __init__(self, salt: bytes):
        self.salt = salt
        self.salt_id = hashlib.sha256(b"ctx-s1-salt:" + salt).hexdigest()[:10]
        self._memo: Dict[str, str] = {}

    def key(self, k: str) -> str:
        h = self._memo.get(k)
        if h is None:
            ch, _, val = k.partition(":")
            h = ch + ":" + hmac.new(self.salt, k.encode("utf-8"), hashlib.sha256).hexdigest()[:HASH_HEX]
            self._memo[k] = h
        return h


# --------------------------------------------------------------------------
# Reading one transcript: structure only

def iter_records(path: Path):
    try:
        with open(path, "rb") as fh:
            for line in fh:
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if isinstance(obj, dict):
                    yield obj
    except OSError:
        return


def _msg_content(obj: Dict[str, Any]):
    msg = obj.get("message")
    return msg.get("content") if isinstance(msg, dict) else None


def _prompt_text(obj: Dict[str, Any]) -> Optional[str]:
    """The human prompt of a user record, or None (tool results, meta records,
    compaction summaries and harness-written prompts are not prompts)."""
    if obj.get("type") != "user" or obj.get("isMeta") or obj.get("isCompactSummary") or obj.get("isSidechain"):
        return None
    c = _msg_content(obj)
    if isinstance(c, str):
        text = c
    elif isinstance(c, list):
        kinds = {it.get("type") for it in c if isinstance(it, dict)}
        if "tool_result" in kinds:
            return None
        text = "\n".join(it.get("text", "") for it in c if isinstance(it, dict) and it.get("type") == "text")
    else:
        return None
    if not text.strip() or ctx_s1.HARNESS_PROMPT_RE.match(text):
        return None
    return text


def _injected_texts(obj: Dict[str, Any]) -> List[str]:
    """Text injected into the model by the harness: hook output (plain or
    JSON additionalContext), hook_additional_context, instruction files,
    nested memory. The pointed mask reads these."""
    if obj.get("type") != "attachment":
        return []
    att = obj.get("attachment")
    if not isinstance(att, dict):
        return []
    at = att.get("type")
    out: List[str] = []
    if at == "hook_success":
        for f in ("content", "stdout"):
            v = att.get(f)
            if isinstance(v, str) and v.strip():
                out.append(v)
    elif at == "hook_additional_context":
        c = att.get("content")
        out += [x for x in (c if isinstance(c, list) else [c]) if isinstance(x, str)]
    elif at == "instructions":
        for f in att.get("files") or []:
            if isinstance(f, dict) and isinstance(f.get("content"), str):
                out.append(f["content"])
    elif at == "nested_memory":
        c = att.get("content")
        if isinstance(c, dict) and isinstance(c.get("content"), str):
            out.append(c["content"])
    elif at in ("file", "compact_file_reference"):
        # an @-mentioned file, or one the compaction summary refers back to
        for f in ("filename", "displayPath"):
            if isinstance(att.get(f), str):
                out.append(att[f])
        if isinstance(att.get("content"), str):
            out.append(att["content"][:20000])
    elif at == "queued_command":
        # user text sent mid-turn: it can name a file as a prompt can
        if isinstance(att.get("prompt"), str):
            out.append(att["prompt"][:20000])
    return out


def _meta_text(obj: Dict[str, Any]) -> str:
    """Text of a meta user record (a skill's body, a harness notice): injected
    into context though no hook printed it."""
    c = _msg_content(obj)
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "\n".join(it.get("text", "") for it in c if isinstance(it, dict) and it.get("type") == "text")
    return ""


def _result_text(item: Dict[str, Any]) -> str:
    c = item.get("content")
    if isinstance(c, str):
        return c[:20000]
    if isinstance(c, list):
        return "\n".join(str(x.get("text", "")) for x in c if isinstance(x, dict))[:20000]
    return ""


def _obj_named(ob: str, text: str) -> bool:
    """Whether a tool's output named an object (its file name or entity slug):
    the fetch that follows is then the agent reading what a search listed."""
    tail = ob.split(":", 1)[-1].rsplit("/", 1)[-1]
    return len(tail) >= 6 and tail in text


def pointer_objs(text: str) -> Set[str]:
    """Object keys a piece of injected text points at."""
    out: Set[str] = set()
    for m in KG_PATH_RE.findall(text):
        out.add("kg:" + m.lower())
        out.add("o:research/entities/%s.md" % m.lower())
    for m in SPECS_PATH_RE.findall(text):
        out.add("o:" + m.lower())
    for m in MEM_LINK_RE.findall(text):
        out.add("m:" + m.lower())
    for m in MEM_PATH_RE.findall(text):
        out.add("m:" + m.lower())
    for repo, n in PR_OBJ_RE.findall(text):
        out.add("o:pr:%s#%s" % (repo.lower(), n))
    return out


def _path_objs(p: str, where: Where, scope_id: Optional[str]) -> Set[str]:
    """The objects a path names, resolved exactly as the gate resolves an
    event's own file (ctx_s1._path_keys_for): against the repo it is in when
    that repo is in the scope, so a nested repo's file is that repo's."""
    _, objs, rel = ctx_s1._path_keys_for(os.path.normpath(p), where, scope_id)
    out = set(objs)
    m = re.match(r"research/entities/(.+)\.md$", (rel or "").lower())
    if m:
        out.add("kg:" + m.group(1))
    return out


def fetch_objs(name: str, inp: Dict[str, Any], where: Where, repo: Optional[str],
               scope_id: Optional[str] = None) -> Set[str]:
    """Object keys one tool call opened: the ledger's notion of a use."""
    out: Set[str] = set()

    def add_path(p: str) -> None:
        out.update(_path_objs(p, where, scope_id))

    if name in ("Read", "Grep"):
        p = inp.get("file_path") or inp.get("path")
        if isinstance(p, str) and p:
            add_path(p if os.path.isabs(p) else os.path.join(where.cwd, p))
    elif name == "Bash":
        cmd = inp.get("command") if isinstance(inp.get("command"), str) else ""
        for t in K.bash_read_targets(cmd, where.cwd, cap=8):
            add_path(t)
        for seg in K._segments(cmd):
            prog = os.path.basename(seg[0])
            if prog in ("kg", "kg.py") and seg[1:2] == ["load"]:
                for a in seg[2:]:
                    if not a.startswith("-"):
                        a = a.lower().strip("'\"")
                        out.add("kg:" + (a[:-3] if a.endswith(".md") else a))
            if prog == "python3" and len(seg) > 2 and seg[1].endswith("kg.py") and seg[2] == "load":
                for a in seg[3:]:
                    if not a.startswith("-"):
                        out.add("kg:" + a.lower())
        for act, num, act_repo in K.bash_actions(cmd):
            if act in ("pr-view", "pr-diff", "pr-checks") and num and (act_repo or repo):
                out.add("o:pr:%s#%s" % (act_repo or repo, num))
    elif name == "WebFetch":
        m = K.PR_URL_RE.search(str(inp.get("url") or ""))
        if m:
            out.add("o:pr:%s#%s" % (m.group(1).lower(), m.group(2)))
    elif name == "Skill" and str(inp.get("skill") or "").lower() == "kg":
        args = str(inp.get("args") or "").split()
        if args[:1] == ["load"]:
            out |= {"kg:" + a.lower() for a in args[1:] if not a.startswith("-")}
    return out


def authored_objs(name: str, inp: Dict[str, Any], where: Where, scope_id: Optional[str] = None) -> Set[str]:
    if name not in EDIT_TOOLS:
        return set()
    p = inp.get("file_path") or inp.get("notebook_path")
    if not isinstance(p, str) or not p:
        return set()
    if not os.path.isabs(p):
        p = os.path.join(where.cwd, p)
    return _path_objs(p, where, scope_id)


# --------------------------------------------------------------------------
# Where a session ran, even when its worktree is gone

def _paseo_root(cwd: str) -> Optional[str]:
    m = re.match(r"^(.*/\.paseo/worktrees/[^/]+/[^/]+)", cwd)
    if m:
        return m.group(1)
    m = re.match(r"^(.*/\.worktrees/[^/]+)", cwd)
    return m.group(1) if m else None


def infer_where(cwd: str, branch: Optional[str], scopes: ctx.Scopes) -> Tuple[Optional[str], Optional[Where]]:
    """(scope id, Where) for a transcript's cwd. A live checkout resolves as the
    hook would. A deleted Paseo worktree is resolved through a sibling in the
    same group; a deleted `.worktrees/x` through its parent repo. Anything under
    a Stimulus path, or unresolvable, has no scope and is left out."""
    if not cwd or "/stimulus/" in cwd or re.search(r"/sri(/|$)", cwd):
        return None, None
    loc = ctx.locate(cwd, timeout=0.5) if os.path.isdir(cwd) else None
    if loc is not None:
        sid = scopes.by_repo.get(loc.common_dir)
        return (sid, Where(cwd, loc.toplevel, loc.common_dir, branch or loc.branch)) if sid else (None, None)
    root = _paseo_root(cwd)
    if not root:
        return None, None
    common = None
    if "/.paseo/worktrees/" in root:
        group = os.path.dirname(root)
        try:
            for sib in sorted(os.listdir(group)):
                gf = os.path.join(group, sib, ".git")
                if os.path.isfile(gf):
                    target = ctx._gitdir_from_file(gf)
                    if target:
                        common = ctx._common_of(target)
                        break
        except OSError:
            pass
    else:
        parent = root.split("/.worktrees/")[0]
        loc = ctx.locate(parent, timeout=0.5) if os.path.isdir(parent) else None
        common = loc.common_dir if loc else None
    sid = scopes.by_repo.get(common) if common else None
    return (sid, Where(cwd, root, common, branch)) if sid else (None, None)


# --------------------------------------------------------------------------
# One session -> events, fetches, masks

def _ts(obj: Dict[str, Any]) -> Optional[float]:
    t = obj.get("timestamp")
    if isinstance(t, str) and len(t) >= 19:
        try:
            return ctx.parse_ts(t[:19] + ".000Z")
        except (ValueError, IndexError):
            return None
    return None


def subagent_fetches(path: Path, where: Where, repo: Optional[str], point, scope_id: Optional[str] = None,
                     cap: int = SUB_FETCH_CAP
                     ) -> Tuple[List[Tuple[int, List[str], List[str]]], List[Tuple[int, List[str]]]]:
    """([(ordinal, objects, listed)], [(ordinal, pointed objects)]) for a
    subagent transcript's own tool calls, masked and flagged as the parent's
    are: its own injected text (instruction files, hook output) points, and a
    tool output that named an object makes the fetch after it a listed one."""
    out, pointed, n = [], [], 0
    recent_out: List[str] = []
    for obj in iter_records(path):
        texts = _injected_texts(obj)
        if obj.get("type") == "user" and obj.get("isMeta"):
            texts = texts + [_meta_text(obj)]
        objs = set()
        for t in texts:
            objs |= point(t, where)
        if objs:
            pointed.append((n, sorted(objs)))
        if obj.get("type") == "user":
            c = _msg_content(obj)
            for it in c if isinstance(c, list) else []:
                if isinstance(it, dict) and it.get("type") == "tool_result":
                    recent_out = (recent_out + [_result_text(it)])[-3:]
            continue
        c = _msg_content(obj) if obj.get("type") == "assistant" else None
        for it in c if isinstance(c, list) else []:
            if isinstance(it, dict) and it.get("type") == "tool_use":
                inp = it.get("input") if isinstance(it.get("input"), dict) else {}
                objs = fetch_objs(str(it.get("name") or ""), inp, where, repo, scope_id)
                if objs:
                    seen = "\n".join(recent_out)
                    out.append((n, sorted(objs), sorted(o for o in objs if _obj_named(o, seen))))
                n += 1
                if n >= cap:
                    return out, pointed
    return out, pointed


def read_session(path: Path, scopes: ctx.Scopes, want_scope: str, point=None) -> Optional[Dict[str, Any]]:
    """The raw replay record of one main transcript, or None when it is not in
    `want_scope`. Keys are still raw here; `build_snapshot` hashes them.
    `point(text, where)` names the objects a piece of injected text points at
    (default: paths, entity paths, memory links and PR refs only)."""
    point = point or (lambda text, where: pointer_objs(text))
    batch_end: Dict[str, int] = {}  # assistant message id -> its last tool call's ordinal
    records = list(iter_records(path))
    first = next((r for r in records if isinstance(r.get("cwd"), str)), None)
    if first is None:
        return None
    sid, where0 = infer_where(first["cwd"], first.get("gitBranch"), scopes)
    if sid != want_scope or where0 is None:
        return None
    repo0 = K.repo_name(where0.common_dir)
    sub_dir = path.parent / path.stem / "subagents"
    events: List[Dict[str, Any]] = []
    fetches: List[Tuple[int, List[str], List[str]]] = []
    recent_out: List[str] = []   # the last three tool outputs
    pointed: List[Tuple[int, List[str]]] = []
    authored: List[Tuple[int, List[str]]] = []
    agent_calls: Dict[str, Dict[str, Any]] = {}
    bash_calls: Dict[str, Tuple[Dict[str, Any], int, str]] = {}
    placed: Dict[str, Optional[Tuple[str, str]]] = {where0.cwd: (where0.toplevel, where0.common_dir)}
    ordinal = 0
    start = None
    for obj in records:
        ts = _ts(obj)
        if start is None and ts:
            start = ts
        if obj.get("isSidechain"):
            continue
        branch = obj.get("gitBranch") if isinstance(obj.get("gitBranch"), str) else where0.branch
        cwd = obj.get("cwd") if isinstance(obj.get("cwd"), str) else where0.cwd
        if cwd not in placed:
            # the session moved (`cd skills`): the hook resolves the repo, and
            # the scope, from the cwd it is given, so the replay does too
            sid2, w2 = infer_where(cwd, branch, scopes)
            placed[cwd] = (w2.toplevel, w2.common_dir) if sid2 == want_scope and w2 else None
        if placed[cwd] is None:
            # another scope's (or no scope's) directory: its events are that
            # scope's; only the ordinal advances here
            if obj.get("type") == "assistant":
                c = _msg_content(obj)
                ordinal += sum(1 for it in (c if isinstance(c, list) else [])
                               if isinstance(it, dict) and it.get("type") == "tool_use")
            continue
        where = Where(cwd, placed[cwd][0], placed[cwd][1], branch)
        repo = K.repo_name(where.common_dir) or repo0
        texts = _injected_texts(obj)
        if texts:
            objs = set()
            for t in texts:
                objs |= point(t, where)
            if objs:
                pointed.append((ordinal, sorted(objs)))
        if obj.get("type") == "user" and obj.get("isMeta"):
            objs = point(_meta_text(obj), where)
            if objs:
                pointed.append((ordinal, sorted(objs)))
            continue
        if obj.get("type") == "user" and obj.get("isCompactSummary"):
            events.append({"stage": "compact", "anchor": ordinal, "ts": ts, "payload": {"source": "compact"},
                           "where": where, "repo": repo})
            continue
        prompt = _prompt_text(obj)
        if prompt is not None:
            events.append({"stage": "prompt", "anchor": ordinal, "ts": ts, "repo": repo,
                           "payload": {"prompt": prompt}, "where": where, "echo_text": prompt[:8000]})
            continue
        if obj.get("type") == "user":
            c = _msg_content(obj)
            for it in c if isinstance(c, list) else []:
                if isinstance(it, dict) and it.get("type") == "tool_result":
                    out_text = _result_text(it)
                    recent_out = (recent_out + [out_text])[-3:]
                    bc = bash_calls.get(str(it.get("tool_use_id")))
                    if bc is not None:
                        # the live post-bash hook sees the output: a number-less
                        # `gh pr view` keys (and opens) the PR its URL names
                        ev_b, o_b, cmd_b = bc
                        ev_b["payload"]["tool_response"] = {"stdout": out_text[:4000]}
                        m = K.PR_URL_RE.search(out_text)
                        if m and any(act in ("pr-view", "pr-diff", "pr-checks") and not num
                                     for act, num, _ in K.bash_actions(cmd_b)):
                            fetches.append((o_b, ["o:pr:%s#%s" % (m.group(1).lower(), m.group(2))], []))
                    call = agent_calls.get(str(it.get("tool_use_id")))
                    if call is not None:
                        m = AGENT_ID_RE.search(json.dumps(it.get("content"))[:4000])
                        if m:
                            call["agent_file"] = str(sub_dir / ("agent-%s.jsonl" % m.group(1)))
            continue
        if obj.get("type") != "assistant":
            continue
        c = _msg_content(obj)
        msg = obj.get("message") if isinstance(obj.get("message"), dict) else {}
        mid = str(msg.get("id") or obj.get("uuid") or ordinal)
        for it in c if isinstance(c, list) else []:
            if not (isinstance(it, dict) and it.get("type") == "tool_use"):
                continue
            name = str(it.get("name") or "")
            inp = it.get("input") if isinstance(it.get("input"), dict) else {}
            batch_end[mid] = ordinal
            objs = fetch_objs(name, inp, where, repo, want_scope)
            if objs:
                seen_text = "\n".join(recent_out)
                fetches.append((ordinal, sorted(objs), sorted(o for o in objs if _obj_named(o, seen_text))))
            a = authored_objs(name, inp, where, want_scope)
            if a:
                authored.append((ordinal, sorted(a)))
            payload = {"tool_name": name, "cwd": where.cwd,
                       "tool_input": {k: v for k, v in inp.items()
                                      if k in ("file_path", "notebook_path", "path", "command", "pattern")}}
            # a tool stage's claim can first be used by the NEXT assistant
            # message: calls issued in parallel with this one were already
            # written. The anchor is fixed once the batch is known (below).
            if name in EDIT_TOOLS:
                events.append({"stage": "pre-edit", "anchor": ordinal + 1, "ts": ts, "payload": payload,
                               "where": where, "mid": mid, "repo": repo})
            elif name in READ_TOOLS:
                events.append({"stage": "post-read", "anchor": ordinal + 1, "ts": ts, "payload": payload,
                               "where": where, "mid": mid, "repo": repo})
            elif name == "Bash":
                ev = {"stage": "post-bash", "anchor": ordinal + 1, "ts": ts, "payload": payload, "repo": repo,
                      "where": where, "mid": mid, "echo_text": str(inp.get("command") or "")[:4000]}
                events.append(ev)
                bash_calls[str(it.get("id"))] = (ev, ordinal, str(inp.get("command") or ""))
            elif name in AGENT_TOOLS:
                ev = {"stage": "subagent", "anchor": ordinal + 1, "ts": ts, "where": where, "mid": mid,
                      "repo": repo,
                      "payload": {"agent_type": str(inp.get("subagent_type") or "general-purpose")},
                      "agent_prompt_objs": sorted(point(str(inp.get("prompt") or ""), where))}
                events.append(ev)
                agent_calls[str(it.get("id"))] = ev
            ordinal += 1
    if start is None:
        return None
    events.insert(0, {"stage": "session-start", "anchor": 0, "ts": start, "payload": {"source": "startup"},
                      "where": where0, "repo": repo0})
    for ev in events:
        if ev.get("mid") in batch_end:
            ev["anchor"] = batch_end[ev["mid"]] + 1
        if ev["stage"] == "subagent" and ev.get("agent_file") and os.path.isfile(ev["agent_file"]):
            ev["sub_fetches"], ev["sub_pointed"] = subagent_fetches(Path(ev["agent_file"]), ev["where"],
                                                                    ev["repo"], point, want_scope)
    return {"path": str(path), "start": start, "n_tools": ordinal, "repo": repo0, "events": events,
            "fetches": fetches, "pointed": pointed, "authored": authored}


_SLUG_RE = re.compile(r"[a-z0-9]+(?:[-_][a-z0-9]+)+")


def slug_objs(items: List[Dict[str, Any]]) -> Dict[str, Set[str]]:
    """slug -> object keys, for an item's file stem (`gate-that-cannot-fail`)."""
    out: Dict[str, Set[str]] = {}
    for it in items:
        for ob in it.get("obj") or []:
            stem = ob.rsplit("/", 1)[-1]
            stem = re.sub(r"\.(md|html?)$", "", stem.split(":", 1)[-1])
            if "-" in stem or "_" in stem:
                out.setdefault(stem, set()).add(ob)
    return out


def echo_objs(text: str, where: Where, slugs: Dict[str, Set[str]], cap: int = 20, repo: Optional[str] = None,
              roots: Sequence[Tuple[str, str]] = ()) -> Set[str]:
    """Objects a text names: a path (repo-relative, or absolute in any of the
    scope's repos), an entity path, a memory link, a PR (`repo#n`, a URL, a
    bare `#n` or `PR n`, or the number a `gh pr` command takes), or an item's
    file stem (`[[slug]]` or bare). A partial path the gate matches by its
    tail (`ctx-core/SKILL.md`) is named only through its stem, when that is a
    slug. The echo check and the pointer masks both use it."""
    low = text.lower()
    out = pointer_objs(text) | _echo_paths(text, where, cap, roots)
    for tok in set(_SLUG_RE.findall(low)):
        out |= slugs.get(tok, set())
    if repo:
        out |= {"o:pr:%s#%s" % (repo, n) for n in ctx_s1.BARE_PR_RE.findall(text)}
    for _, num, act_repo in K.bash_actions(text):
        if num and (act_repo or repo):
            out.add("o:pr:%s#%s" % (act_repo or repo, num))
    return out


def _echo_paths(text: str, where: Where, cap: int = 20, roots: Sequence[Tuple[str, str]] = ()) -> Set[str]:
    roots = sorted(set(roots) | ({(where.toplevel, "")} if where.toplevel else set()), key=lambda r: -len(r[0]))
    out = set()
    for p in K.cited_paths(text, roots, cap=cap):
        out.add("o:" + p.lower())
        m = re.match(r"research/entities/(.+)\.md$", p.lower())
        if m:
            out.add("kg:" + m.group(1))
    return out


# --------------------------------------------------------------------------
# Truth: needed fetches per session, after the masks

def needed_fetches(raw: Dict[str, Any], obj_index: Dict[str, List[int]]
                   ) -> Tuple[List[Tuple[int, int, int]], Dict[int, int]]:
    """([(item, ordinal, listed)] first self-directed fetches, {item: ordinal it
    was first pointed at by injected text}). `listed` is 1 when the tool output
    just before the fetch named the item (a search listed it): still the agent's
    own fetch, but an easy one, which E1 reports apart."""
    pointed_at: Dict[int, int] = {}
    for o, objs in raw["pointed"]:
        for ob in objs:
            for i in obj_index.get(ob, ()):
                pointed_at.setdefault(i, o)
    authored_at: Dict[int, int] = {}
    for o, objs in raw["authored"]:
        for ob in objs:
            for i in obj_index.get(ob, ()):
                authored_at.setdefault(i, o)
    first: Dict[int, Tuple[int, int]] = {}
    for o, objs, listed in raw["fetches"]:
        listed_set = set(listed)
        for ob in objs:
            for i in obj_index.get(ob, ()):
                if i not in first or o < first[i][0]:  # the earliest, whatever order they were added in
                    first[i] = (o, 1 if ob in listed_set else 0)
    needed = []
    for i, (o, listed) in sorted(first.items(), key=lambda kv: (kv[1][0], kv[0])):
        if i in pointed_at and pointed_at[i] <= o:
            continue
        if i in authored_at and authored_at[i] <= o:
            continue
        needed.append((i, o, listed))
    return needed, pointed_at


def sub_needed(ev: Dict[str, Any], obj_index: Dict[str, List[int]]) -> List[Tuple[int, int, int]]:
    """[(item, ordinal, listed)]: a subagent's first self-directed fetches. Its
    prompt masks from the start; its own injected text from where it lands."""
    pointed_at: Dict[int, int] = {}
    for ob in ev.get("agent_prompt_objs") or []:
        for i in obj_index.get(ob, ()):
            pointed_at[i] = -1
    for o, objs in ev.get("sub_pointed") or []:
        for ob in objs:
            for i in obj_index.get(ob, ()):
                pointed_at.setdefault(i, o)
    first: Dict[int, Tuple[int, int]] = {}
    for o, objs, listed in ev.get("sub_fetches") or []:
        for ob in objs:
            for i in obj_index.get(ob, ()):
                if i not in first:
                    first[i] = (o, 1 if ob in listed else 0)
    return sorted([(i, o, listed) for i, (o, listed) in first.items()
                   if not (i in pointed_at and pointed_at[i] <= o)], key=lambda x: (x[1], x[0]))


# --------------------------------------------------------------------------
# The snapshot

def transcripts(days: float, now: float, root: Optional[Path] = None) -> List[Path]:
    base = root or (ctx.home() / ".claude" / "projects")
    cut = now - days * 86400
    out = []
    for d in sorted(base.iterdir()) if base.is_dir() else []:
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.jsonl")):
            try:
                if f.stat().st_mtime >= cut:
                    out.append(f)
            except OSError:
                pass
    return out


def default_dir(scope_id: str) -> Path:
    """Where a scope's private snapshot lives: beside its cache, never in a repo."""
    return ctx.state_root() / scope_id / "e1"


def _git_checkout_of(path: Path) -> Optional[Path]:
    p = path.resolve()
    for d in [p] + list(p.parents):
        if (d / ".git").exists():
            return d
    return None


def build_snapshot(scope_id: str, out_dir: Path, days: float = DEFAULT_DAYS, network: bool = True,
                   now: Optional[float] = None, root: Optional[Path] = None, salt: Optional[bytes] = None,
                   items: Optional[List[Dict[str, Any]]] = None, progress=None) -> Dict[str, Any]:
    """Extract, compute truth, hash, and write `snapshot.jsonl.gz` plus
    `snapshot.meta.json` under out_dir. Returns the meta. Refuses an out_dir
    inside a git checkout: the file is derived from private transcripts and is
    not fit to commit (see the module docstring)."""
    checkout = _git_checkout_of(out_dir)
    if checkout is not None:
        raise ValueError("refusing to write the E1 snapshot inside the git checkout %s: it is derived from "
                         "private transcripts; use the default %s" % (checkout, default_dir(scope_id)))
    now = time.time() if now is None else now
    scopes = ctx.load_scopes()
    if items is None:
        scope = ctx.Scope(id=scope_id, store=ctx.state_root() / scope_id, where=None)
        items, _ = ctx_s2.gather(scope, network=network, now=now)
    H = Hasher(salt if salt is not None else load_salt())
    obj_index: Dict[str, List[int]] = {}
    for idx, it in enumerate(items):
        for ob in it.get("obj") or []:
            obj_index.setdefault(ob, []).append(idx)
    slug_index = slug_objs(items)
    roots = [(r, "") for r, _ in ctx_s2.scope_roots(scope_id)]
    repo_of = lambda where: K.repo_name(where.common_dir) if where and where.common_dir else None
    point = lambda text, where: echo_objs(text, where, slug_index, cap=200, repo=repo_of(where), roots=roots)
    sessions = []
    used_keys: Set[str] = set()
    window_start = now - days * DAY
    paths = transcripts(days, now, root)
    for n, p in enumerate(paths):
        if progress and n % 50 == 0:
            progress("%d/%d transcripts, %d sessions kept" % (n, len(paths), len(sessions)))
        raw = read_session(p, scopes, scope_id, point)
        if raw is None or not raw["events"] or raw["start"] < window_start:
            continue  # a transcript touched recently can hold an older session: the window is by start
        needed, pointed_at = needed_fetches(raw, obj_index)
        evs = []
        keyless: Dict[str, int] = {}
        for ev in raw["events"]:
            data = dict(ev["payload"])
            keys, self_obj, path_key, label = ctx_s1.extract_keys(ev["stage"], data, ev["where"], ev["repo"],
                                                                  scope_id)
            if not any(keys.values()) and ev["stage"] not in ("compact", "subagent"):
                # No key: System 1 abstains on it whatever the parameters. Only
                # the count is kept, for the rates' denominators.
                keyless[ev["stage"]] = keyless.get(ev["stage"], 0) + 1
                continue
            for ks in keys.values():
                used_keys.update(ks)
            # keys keep the event's own order (the live gate cuts prompt words
            # at max_terms in that order), deduplicated
            rec = {"st": ev["stage"], "a": ev["anchor"], "ts": int(ev["ts"] or raw["start"]),
                   "k": {ch: [H.key(k) for k in K.unique(ks)] for ch, ks in keys.items() if ks},
                   "self": sorted(H.key(o) for o in self_obj),
                   "pk": H.key("p:" + path_key.lower()) if path_key else None, "ll": len(label)}
            if ev.get("echo_text"):
                # Items the event's own text names (a path, an entity slug, a PR):
                # a hit on one of these is an echo, reported apart.
                echo = set()
                for ob in echo_objs(ev["echo_text"], ev["where"], slug_index, repo=ev["repo"], roots=roots):
                    echo.update(obj_index.get(ob, ()))
                if echo:
                    rec["echo"] = sorted(echo)
            if ev["stage"] == "subagent":
                rec["rev"] = bool(ctx_s1.REVIEWER_RE.search(data.get("agent_type", "")))
                rec["sub"] = sub_needed(ev, obj_index) if ev.get("sub_fetches") is not None else None
            evs.append(rec)
        sessions.append({"start": raw["start"], "n": raw["n_tools"], "events": evs, "keyless": keyless,
                         "needed": [[i, o, listed] for i, o, listed in needed],
                         "pointed": sorted([[i, o] for i, o in pointed_at.items()])})
    sessions.sort(key=lambda s: s["start"])
    n_train = int(len(sessions) * TRAIN_SHARE)
    n_valid = int(len(sessions) * VALIDATION_SHARE)
    for s_idx, s in enumerate(sessions):
        s["s"] = s_idx
        s["split"] = "train" if s_idx < n_train else ("validation" if s_idx < n_train + n_valid else "test")
        s["start"] = int(s["start"])
    # An item keeps only the keys some event names, plus its field lengths:
    # BM25 depends on tf, the field length, the key's document frequency and N,
    # and a kept key keeps every item that holds it, so the replay's scores are
    # the live ones. (A ranker that links items through keys no event names,
    # such as a graph walk, sees fewer edges here than live.) `slen` is the
    # source's length: a claim line's bytes are the claim's plus the source's.
    hitems = []
    for idx, it in enumerate(items):
        counts = ctx_s2.key_counts(it)
        links = [j for j in it.get("links") or [] if 0 <= j < len(items)]
        hitems.append({"i": idx, "t": it["type"], "len": len(it.get("claim") or ""),
                       "slen": len(it.get("source") or ""),
                       "c": _eligible_from(it), "m": int(it.get("mtime") or it.get("created") or 0),
                       "L": {ch: sum(kc.values()) for ch, kc in counts.items() if kc},
                       "k": {ch: dict(sorted((H.key(k), tf) for k, tf in kc.items() if k in used_keys))
                             for ch, kc in counts.items() if any(k in used_keys for k in kc)},
                       "o": sorted(H.key(o) for o in it.get("obj") or []),
                       "ln": sorted(links)})
    splits = {sp: sum(1 for s in sessions if s["split"] == sp) for sp in ("train", "validation", "test")}
    meta = {"schema": SNAPSHOT_SCHEMA, "extractor": EXTRACTOR_VERSION, "scope": scope_id,
            "salt_id": H.salt_id, "created_day": time.strftime("%Y-%m-%d", time.gmtime(now)), "days": days,
            "splits": splits, "items": len(hitems), "sessions": len(sessions),
            "events": sum(len(s["events"]) + sum(s["keyless"].values()) for s in sessions),
            "keyed_events": sum(len(s["events"]) for s in sessions),
            "by_stage": _count_stages(sessions),
            "needed": sum(len(s["needed"]) for s in sessions),
            "by_type": _count_types(hitems)}
    out_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    body = "\n".join(json.dumps(x, sort_keys=True, separators=(",", ":"))
                     for x in [{"kind": "meta", **meta}] + [{"kind": "item", **h} for h in hitems]
                     + [{"kind": "session", **s} for s in sessions]) + "\n"
    data = body.encode("utf-8")
    meta["sha256"] = hashlib.sha256(data).hexdigest()
    tmp = out_dir / ".snapshot.jsonl.gz.tmp"
    with os.fdopen(os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "wb") as fh:
        with gzip.GzipFile(fileobj=fh, mode="wb", mtime=0, compresslevel=9) as gz:
            gz.write(data)
    os.replace(str(tmp), str(out_dir / "snapshot.jsonl.gz"))
    with os.fdopen(os.open(str(out_dir / "snapshot.meta.json"), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600),
                   "w") as fh:
        fh.write(json.dumps(meta, indent=1, sort_keys=True) + "\n")
    return meta


def _eligible_from(it: Dict[str, Any]) -> int:
    """When the replay lets an item be a candidate: its creation time, or for a
    date-only one (UTC midnight) DATE_ONLY_SLACK later unless its file's mtime
    shows it existed sooner."""
    c = int(it.get("created") or 0)
    if c and c % DAY == 0:
        m = int(it.get("mtime") or 0)
        return m if c <= m < c + DATE_ONLY_SLACK else c + DATE_ONLY_SLACK
    return c


def _count_stages(sessions) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for s in sessions:
        for e in s["events"]:
            out[e["st"]] = out.get(e["st"], 0) + 1
        for st, n in s.get("keyless", {}).items():
            out[st] = out.get(st, 0) + n
    return out


def _count_types(items) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for h in items:
        out[h["t"]] = out.get(h["t"], 0) + 1
    return out


def load_snapshot(path: Path) -> Dict[str, Any]:
    """{meta, items, sessions}, verified against the meta's sha256 when a
    sibling snapshot.meta.json exists."""
    data = gzip.decompress(Path(path).read_bytes())
    meta_path = Path(path).parent / "snapshot.meta.json"
    if meta_path.exists():
        want = json.loads(meta_path.read_text()).get("sha256")
        got = hashlib.sha256(data).hexdigest()
        if want and want != got:
            raise ValueError("snapshot sha256 %s does not match its meta (%s)" % (got[:12], want[:12]))
    meta, items, sessions = {}, [], []
    for line in data.decode("utf-8").splitlines():
        rec = json.loads(line)
        kind = rec.pop("kind")
        if kind == "meta":
            meta = rec
        elif kind == "item":
            items.append(rec)
        elif kind == "session":
            sessions.append(rec)
    items.sort(key=lambda h: h["i"])
    meta["sha256"] = hashlib.sha256(data).hexdigest()  # what was loaded, whatever the meta file says
    return {"meta": meta, "items": items, "sessions": sessions}

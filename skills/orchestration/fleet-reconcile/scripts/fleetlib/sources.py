"""Where each surface is read from. Every command and every file read the tick
makes goes through a Sources object, so tests substitute FixtureSources (a
directory of captured copies) and nothing else changes.

Each method returns raw text (or raises SourceError); parsing is parsers.py's.
A command that exits non-zero, times out or is missing raises SourceError, so
the observation of that surface fails rather than reading as empty.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

import ctx_compare  # ctx-core, beside this skill (fleet_reconcile.py puts it on sys.path)

from . import common


class SourceError(RuntimeError):
    pass


#: gh reads GitHub on the owner's keyring login (since 0.4.0; owner decision
#: 2026-10-01). A token inherited from a shell would make gh act as that token
#: instead, so Sources drops both variables from the process environment when
#: it starts: every gh call and every child reads GitHub as the owner's login,
#: as tick.sh's steps do (it unsets them too).
_TOKEN_VARS = ("GH_TOKEN", "GITHUB_TOKEN")


def _drop_token() -> None:
    for k in _TOKEN_VARS:
        os.environ.pop(k, None)


#: What a session started from a session inherits and must not (evidence §1:
#: an inherited CLAUDE_CODE_CHILD_SESSION turns transcript saving off): every
#: CLAUDE_CODE_* (the session's markers, its messaging token and socket) and
#: PASEO_* variable, but the auth and provider settings a headless run needs.
CHILD_DROP = ("CLAUDECODE", "CLAUDE_CODE_", "PASEO_")
CHILD_KEEP = ("CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX",
              "CLAUDE_CODE_USE_FOUNDRY", "CLAUDE_CODE_SKIP_BEDROCK_AUTH", "CLAUDE_CODE_SKIP_VERTEX_AUTH",
              "CLAUDE_CODE_MAX_OUTPUT_TOKENS", "CLAUDE_CODE_API_KEY_HELPER_TTL_MS")


def child_env(extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """The environment for a session the fleet starts (spawn, resume, the
    coordinator): without Claude Code's or Paseo's variables or the fleet
    credential, and with FLEET_CHILD set to 1 (the recursion guard)."""
    env = {k: v for k, v in os.environ.items() if k in CHILD_KEEP or not k.startswith(CHILD_DROP)}
    for k in _TOKEN_VARS:
        env.pop(k, None)
    env["FLEET_CHILD"] = "1"
    env.update(extra or {})
    return env


def _run(argv: List[str], timeout: float, cwd: Optional[str] = None, env: Optional[Dict[str, str]] = None) -> str:
    if env is None:
        env = {k: v for k, v in os.environ.items() if k not in _TOKEN_VARS}
    try:
        proc = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=timeout, cwd=cwd, env=env)
    except FileNotFoundError:
        raise SourceError("%s: not found" % argv[0])
    except subprocess.TimeoutExpired:
        raise SourceError("%s: timed out after %gs" % (" ".join(argv[:3]), timeout))
    if proc.returncode != 0:
        err = common.safe_text(proc.stderr.decode("utf-8", "replace"), 160)
        raise SourceError("%s exited %d: %s" % (" ".join(argv[:4]), proc.returncode, err))
    return proc.stdout.decode("utf-8", "replace")


#: The limit line inside a transcript's JSON string: up to its closing quote,
#: an escape or a newline.
_LIMIT_LINE = re.compile(r'hit your (?:[a-z0-9-]+ )?limit[^"\\\n]{0,80}', re.IGNORECASE)


def _last_limit(text: str) -> Optional[str]:
    found = None
    for m in _LIMIT_LINE.finditer(text):
        found = m.group(0)
    return found


def last_activity_ts(path: str) -> Optional[float]:
    """A transcript's last activity (spec §5.3): the latest timestamp among its
    assistant entries and tool results. Not any entry: a queue-operation is
    stamped when a message is delivered, so a mail to a hung session would read
    as activity; and not the file's mtime, which Claude Code moves with
    untimestamped records (last-prompt, cost-state) long after a turn. Reads
    the tail through ctx-core's reader (it widens past a large last line), and
    only type, content kinds and timestamp. None when no such entry is in the
    last 16 MiB."""
    return ctx_compare.last_in_tail(path, _activity_in)


def _activity_in(lines: List[bytes]) -> Optional[float]:
    for raw in reversed(lines):
        if b'"timestamp"' not in raw or (b'"assistant"' not in raw and b'"tool_result"' not in raw):
            continue
        try:
            e = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            continue
        if not isinstance(e, dict):
            continue
        kind = e.get("type")
        content = (e.get("message") or {}).get("content") if isinstance(e.get("message"), dict) else None
        tool_result = kind == "user" and isinstance(content, list) and any(
            isinstance(c, dict) and c.get("type") == "tool_result" for c in content)
        if kind == "assistant" or tool_result:
            t = common.parse_iso(e.get("timestamp"))
            if t is not None:
                return t
    return None


class Sources:
    """The machine: commands on PATH (FLEET_CLAUDE_BIN, FLEET_GH_BIN override)
    and files under $HOME."""

    def __init__(self) -> None:
        _drop_token()
        self.claude = os.environ.get("FLEET_CLAUDE_BIN") or "claude"
        self.gh = os.environ.get("FLEET_GH_BIN") or "gh"

    # Claude Code ---------------------------------------------------------
    def claude_version(self) -> str:
        return _run([self.claude, "--version"], 20)

    def agents_listing(self, timeout: float = 30) -> str:
        return _run([self.claude, "agents", "--json", "--all"], timeout)

    def claude_dir(self) -> Path:
        base = os.environ.get("CLAUDE_CONFIG_DIR")
        return Path(base) if base else common.home() / ".claude"

    def job_states(self) -> Iterator[Tuple[str, str]]:
        root = self.claude_dir() / "jobs"
        if not root.is_dir():
            raise SourceError("%s: missing" % common.tilde(str(root)))
        for d in sorted(root.iterdir()):
            p = d / "state.json"
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:  # not a job dir, or removed while the tick read the others
                continue
            yield d.name, text

    def transcript_index(self) -> Dict[str, Dict[str, Any]]:
        """{session id: {"mtime": top-level transcript, "path": it, "sub":
        newest subagent transcript}} over every project directory. A session id
        seen in two project directories keeps the newer of each."""
        root = self.claude_dir() / "projects"
        out: Dict[str, Dict[str, Any]] = {}
        try:
            pdirs = [p for p in root.iterdir() if p.is_dir()]
        except OSError:
            raise SourceError("%s: unreadable" % common.tilde(str(root)))
        for pdir in pdirs:
            try:
                entries = list(os.scandir(pdir))
            except OSError:
                continue
            for e in entries:
                try:
                    if e.name.endswith(".jsonl") and e.is_file():
                        slot = out.setdefault(e.name[:-6], {})
                        mt = e.stat().st_mtime
                        if mt >= slot.get("mtime", 0.0):
                            slot["mtime"], slot["path"] = mt, e.path
                    elif e.is_dir():
                        sub = Path(e.path) / "subagents"
                        if sub.is_dir():
                            subs = sorted(((f.stat().st_mtime, str(f)) for f in sub.glob("*.jsonl")), reverse=True)
                            if subs:
                                slot = out.setdefault(e.name, {})
                                slot["sub"] = max(slot.get("sub", 0.0), subs[0][0])
                                slot["sub_paths"] = [p for _, p in subs[:3]]  # an entry is at or before its mtime
                except OSError:
                    continue
        return out

    def limit_text(self, sid: str, info: Dict[str, Any]) -> Optional[str]:
        """The last usage-limit line in a transcript's final 64 KiB ("hit your
        session limit · resets 10:50pm (America/Bogota)"), or None. Only the
        match is kept; nothing else of the transcript is read into the tick."""
        path = info.get("path")
        if not path:
            return None
        try:
            tail = common.read_tail(Path(path), 64 * 1024).decode("utf-8", "replace")
        except OSError:
            return None
        return _last_limit(tail)

    def activity(self, info: Dict[str, Any]) -> Optional[float]:
        """The session's last activity over its transcript and its newest
        subagent transcripts (spec §5.3)."""
        times = [last_activity_ts(p) for p in [info.get("path")] + list(info.get("sub_paths") or []) if p]
        times = [t for t in times if t is not None]
        return max(times) if times else None

    # Paseo (read-only, from disk) ----------------------------------------
    def paseo_dir(self) -> Path:
        return common.home() / ".paseo"

    def paseo_records(self) -> Iterator[Tuple[str, str]]:
        root = self.paseo_dir() / "agents"
        if not root.is_dir():
            raise SourceError("%s: missing" % common.tilde(str(root)))
        for p in sorted(root.glob("*/*.json")):
            yield str(p.relative_to(root)), p.read_text(encoding="utf-8", errors="replace")

    def paseo_schedules(self) -> Iterator[Tuple[str, str]]:
        root = self.paseo_dir() / "schedules"
        if not root.is_dir():
            raise SourceError("%s: missing" % common.tilde(str(root)))
        for p in sorted(root.glob("*.json")):
            yield p.name, p.read_text(encoding="utf-8", errors="replace")

    # git and GitHub ------------------------------------------------------
    def origin_url(self, common_dir: str) -> str:
        return _run(["git", "--git-dir", common_dir, "remote", "get-url", "origin"], 10).strip()

    def default_branch(self, slug: str) -> str:
        return _run([self.gh, "api", "repos/%s" % slug, "--jq", ".default_branch"], 30).strip()

    def rules(self, slug: str, branch: str) -> str:
        return _run([self.gh, "api", "repos/%s/rules/branches/%s" % (slug, branch)], 30)

    def open_prs(self, slug: str, limit: int) -> str:
        from .parsers import PR_FIELDS

        return _run([self.gh, "pr", "list", "-R", slug, "--state", "open", "--limit", str(limit),
                     "--json", PR_FIELDS], 60)

    def pr_files(self, slug: str, number: int) -> str:
        """A JSON array of every changed path of the PR, a rename's old path
        too (the owner-merge check), through REST with --paginate: `gh pr view
        --json files` stops at 100. GitHub lists at most 3000 files, so a list
        shorter than the PR's changed_files raises SourceError: the
        owner-merge check never passes on part of one."""
        total = _run([self.gh, "api", "repos/%s/pulls/%d" % (slug, number), "--jq", ".changed_files"], 60).strip()
        out = _run([self.gh, "api", "--paginate", "repos/%s/pulls/%d/files?per_page=100" % (slug, number),
                    "--jq", ".[] | [.filename, .previous_filename]"], 120)
        try:
            rows = [json.loads(ln) for ln in out.splitlines() if ln.strip()]
        except ValueError:
            raise SourceError("%s#%d's file list isn't JSON" % (slug, number))
        if not total.isdigit() or len(rows) < int(total):
            raise SourceError("GitHub listed %d of %s#%d's %s changed files (it lists at most 3000)"
                              % (len(rows), slug, number, common.safe_text(total, 20) or "?"))
        return json.dumps([f for row in rows if isinstance(row, list) for f in row if isinstance(f, str)])

    def pr_heads(self, slug: str, branch: str) -> str:
        """A JSON array of {number, state} for PRs from this head branch (the janitor)."""
        return _run([self.gh, "pr", "list", "-R", slug, "--head", branch, "--state", "all", "--json", "number,state"],
                    60)

    def pr_labels(self, slug: str, number: int) -> str:
        """A JSON array of the PR's label names (recovering a label intent)."""
        return _run([self.gh, "pr", "view", str(number), "-R", slug, "--json", "labels", "--jq",
                     "[.labels[].name]"], 60)

    def gh_api(self, method: str, path: str, fields: Optional[Dict[str, str]] = None) -> str:
        argv = [self.gh, "api", "-X", method, path]
        for k, v in (fields or {}).items():
            argv += ["-f", "%s=%s" % (k, v)]
        return _run(argv, 60)

    def run_claude(self, args: List[str], cwd: Optional[str] = None, timeout: float = 120) -> str:
        """`claude <args>` as a fleet child (spawn, resume, stop, rm)."""
        return _run([self.claude] + args, timeout, cwd=cwd, env=child_env())

    def pid_started(self, pid: int) -> Optional[float]:
        """When a process started (epoch), from ps; None when it isn't running."""
        try:
            out = _run(["ps", "-o", "lstart=", "-p", str(int(pid))], 10).strip()
        except SourceError:
            return None
        try:
            return time.mktime(time.strptime(" ".join(out.split()), "%a %b %d %H:%M:%S %Y"))
        except ValueError:
            return None

    def transcript_path(self, sid: str) -> Optional[str]:
        return (self.transcript_index().get(sid) or {}).get("path")

    # launchd and run logs ------------------------------------------------
    def launch_agents(self, prefix: str) -> Iterator[Tuple[str, str]]:
        """(label, the plist as JSON text) for each LaunchAgent with the prefix."""
        root = common.home() / "Library" / "LaunchAgents"
        if not root.is_dir():
            return
        for p in sorted(root.glob(prefix + "*.plist")):
            yield p.stem, _run(["plutil", "-convert", "json", "-o", "-", str(p)], 10)

    def launchctl_print(self, label: str) -> Optional[str]:
        """None when the job is not loaded."""
        try:
            return _run(["launchctl", "print", "gui/%d/%s" % (os.getuid(), label)], 10)
        except SourceError:
            return None

    def mtime(self, path: str) -> Optional[float]:
        try:
            return common.expand(path).stat().st_mtime
        except OSError:
            return None

    def tail(self, path: str, max_bytes: int = 256 * 1024) -> bytes:
        try:
            return common.read_tail(common.expand(path), max_bytes)
        except OSError as exc:
            raise SourceError("%s: %s" % (common.tilde(str(common.expand(path))), exc.strerror or exc))


class FixtureSources(Sources):
    """Captured copies under one directory, laid out as tests/fixtures/README.md
    describes. A file that is absent raises SourceError, as the real command
    would fail."""

    def __init__(self, root: Path, home: Optional[Path] = None) -> None:
        super().__init__()
        self.root = Path(root)
        self.calls: List[List[str]] = []

    def _read(self, rel: str) -> str:
        p = self.root / rel
        if not p.is_file():
            raise SourceError("fixture %s: missing" % rel)
        return p.read_text(encoding="utf-8")

    def claude_version(self) -> str:
        return self._read("claude/version.txt")

    def agents_listing(self, timeout: float = 30) -> str:
        return self._read("claude/agents.json")

    def claude_dir(self) -> Path:
        return self.root / "claude"

    def transcript_index(self) -> Dict[str, Dict[str, Any]]:
        p = self.root / "claude" / "transcripts.json"
        if not p.is_file():
            raise SourceError("fixture claude/transcripts.json: missing")
        return {k: {kk: (float(vv) if kk in ("mtime", "sub", "activity") and vv is not None else vv)
                    for kk, vv in v.items()}
                for k, v in json.loads(p.read_text()).items()}

    def activity(self, info: Dict[str, Any]) -> Optional[float]:
        v = info.get("activity")
        return float(v) if v is not None else None

    def limit_text(self, sid: str, info: Dict[str, Any]) -> Optional[str]:
        p = self.root / "claude" / "transcript-tails" / (sid + ".txt")
        return _last_limit(p.read_text(encoding="utf-8")) if p.is_file() else None

    def paseo_dir(self) -> Path:
        return self.root / "paseo"

    def origin_url(self, common_dir: str) -> str:
        remotes = json.loads(self._read("git/remotes.json"))
        if common_dir not in remotes:
            raise SourceError("git: no origin for %s" % common_dir)
        return remotes[common_dir]

    def _gh(self, slug: str, name: str) -> str:
        return self._read("gh/%s/%s" % (slug.replace("/", "__"), name))

    def default_branch(self, slug: str) -> str:
        return self._gh(slug, "default_branch.txt").strip()

    def rules(self, slug: str, branch: str) -> str:
        return self._gh(slug, "rules.json")

    def open_prs(self, slug: str, limit: int) -> str:
        return self._gh(slug, "prs.json")

    def pr_files(self, slug: str, number: int) -> str:
        return self._gh(slug, "pr-%d-files.json" % number)

    def pr_heads(self, slug: str, branch: str) -> str:
        return self._gh(slug, "prs-head-%s.json" % branch.replace("/", "__"))

    def gh_api(self, method: str, path: str, fields: Optional[Dict[str, str]] = None) -> str:
        self.calls.append(["gh", "api", "-X", method, path] + ["%s=%s" % kv for kv in (fields or {}).items()])
        return "{}"

    def run_claude(self, args: List[str], cwd: Optional[str] = None, timeout: float = 120) -> str:
        """Recorded, never run; the reply is claude/run-<verb>.txt when the fixture has one."""
        self.calls.append(["claude"] + list(args))
        p = self.root / "claude" / ("run-%s.txt" % args[0].lstrip("-"))
        return p.read_text() if p.is_file() else ""

    def pr_labels(self, slug: str, number: int) -> str:
        return self._gh(slug, "pr-%d-labels.json" % number)

    def pid_started(self, pid: int) -> Optional[float]:
        p = self.root / "claude" / "pids.json"
        v = json.loads(p.read_text()).get(str(pid)) if p.is_file() else None
        return float(v) if v is not None else None

    def transcript_path(self, sid: str) -> Optional[str]:
        p = self.root / "claude" / "transcript-files" / (sid + ".jsonl")
        return str(p) if p.is_file() else None

    def launch_agents(self, prefix: str) -> Iterator[Tuple[str, str]]:
        root = self.root / "launchd"
        if not root.is_dir():
            return
        for p in sorted(root.glob(prefix + "*.json")):
            yield p.stem, p.read_text()

    def launchctl_print(self, label: str) -> Optional[str]:
        p = self.root / "launchd" / (label + ".print.txt")
        return p.read_text() if p.is_file() else None

    def mtime(self, path: str) -> Optional[float]:
        mt = self.root / "mtimes.json"
        if mt.is_file():
            v = json.loads(mt.read_text()).get(path)
            return float(v) if v is not None else None
        return None

    def tail(self, path: str, max_bytes: int = 256 * 1024) -> bytes:
        p = self.root / "files" / Path(path).name
        if not p.is_file():
            raise SourceError("fixture files/%s: missing" % Path(path).name)
        return p.read_bytes()

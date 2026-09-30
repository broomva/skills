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
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from . import common


class SourceError(RuntimeError):
    pass


#: Only gh needs the fleet token. Sources takes it out of the process
#: environment when it starts, so no child inherits it (git run by ctx, say),
#: and hands it to gh alone.
_TOKEN_VARS = ("GH_TOKEN", "GITHUB_TOKEN")
_TOKEN: Dict[str, str] = {}


def _take_token() -> None:
    for k in _TOKEN_VARS:
        if k in os.environ:
            _TOKEN[k] = os.environ.pop(k)


def _run(argv: List[str], timeout: float, cwd: Optional[str] = None, token: bool = False) -> str:
    env = dict(os.environ, **_TOKEN) if token else {k: v for k, v in os.environ.items() if k not in _TOKEN_VARS}
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


class Sources:
    """The machine: commands on PATH (FLEET_CLAUDE_BIN, FLEET_GH_BIN override)
    and files under $HOME."""

    def __init__(self) -> None:
        _take_token()
        self.claude = os.environ.get("FLEET_CLAUDE_BIN") or "claude"
        self.gh = os.environ.get("FLEET_GH_BIN") or "gh"

    # Claude Code ---------------------------------------------------------
    def claude_version(self) -> str:
        return _run([self.claude, "--version"], 20)

    def agents_listing(self) -> str:
        return _run([self.claude, "agents", "--json", "--all"], 30)

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
                            m = max((f.stat().st_mtime for f in sub.glob("*.jsonl")), default=None)
                            if m is not None:
                                slot = out.setdefault(e.name, {})
                                slot["sub"] = max(slot.get("sub", 0.0), m)
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

    def last_entry(self, info: Dict[str, Any]) -> Optional[float]:
        """The time of the transcript's last timestamped entry (ctx-core's
        reader, so the core's comparison and the classes agree)."""
        import ctx_compare

        return ctx_compare.last_entry_ts(info["path"]) if info.get("path") else None

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
        return _run([self.gh, "api", "repos/%s" % slug, "--jq", ".default_branch"], 30, token=True).strip()

    def rules(self, slug: str, branch: str) -> str:
        return _run([self.gh, "api", "repos/%s/rules/branches/%s" % (slug, branch)], 30, token=True)

    def open_prs(self, slug: str, limit: int) -> str:
        from .parsers import PR_FIELDS

        return _run([self.gh, "pr", "list", "-R", slug, "--state", "open", "--limit", str(limit),
                     "--json", PR_FIELDS], 60, token=True)

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

    def _read(self, rel: str) -> str:
        p = self.root / rel
        if not p.is_file():
            raise SourceError("fixture %s: missing" % rel)
        return p.read_text(encoding="utf-8")

    def claude_version(self) -> str:
        return self._read("claude/version.txt")

    def agents_listing(self) -> str:
        return self._read("claude/agents.json")

    def claude_dir(self) -> Path:
        return self.root / "claude"

    def transcript_index(self) -> Dict[str, Dict[str, Any]]:
        p = self.root / "claude" / "transcripts.json"
        if not p.is_file():
            raise SourceError("fixture claude/transcripts.json: missing")
        return {k: {kk: (float(vv) if kk in ("mtime", "sub", "last_entry") and vv is not None else vv)
                    for kk, vv in v.items()}
                for k, v in json.loads(p.read_text()).items()}

    def last_entry(self, info: Dict[str, Any]) -> Optional[float]:
        v = info.get("last_entry")
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

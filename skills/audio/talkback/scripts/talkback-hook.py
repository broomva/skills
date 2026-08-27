#!/usr/bin/env python3
"""talkback turn-end hook — speak a readback, in THIS session and no other.

OFF by default. Talk mode is enabled per session:

    talkback-hook.py --on          # continuous readback, THIS session only
    talkback-hook.py --off         # silence THIS session
    talkback-hook.py --status      # this session + anything else that is talking
    talkback-hook.py --outputs     # audio output devices on this host

The flag is `~/.talkback/sessions/<session-id>`. A session that never opted in
has no flag, so the hook exits 0 without a sound — which is what makes it safe
to register the hook once, globally and permanently, while only one session is
ever audible. The point of the whole design: parallel agents in other worktrees
stay silent, because talk mode is a property of a session, not of the machine.

Three detail levels, stored in the flag's body:

  full  (session default)  speak the WHOLE turn. The point of a readback is to
                           walk away and come back knowing what happened; a
                           capped excerpt is a preview of the answer, not the
                           answer.
  brief                    the opening TALKBACK_HOOK_CHARS of turns over
                           MIN_CHARS — the 0.3.0 behaviour.
  marker                   only turns where the agent deliberately left a
                           `<!-- talkback: ... -->` marker.

`--on --global` restores the pre-0.3.0 machine-wide flag. It is a deliberate,
separate gesture and it defaults to `marker`, because a global flag makes every
concurrent agent audible at once.

Registered for two events:

  Stop        speak the readback
  SessionEnd  drop this session's flag, so talk mode never outlives the session
              that asked for it

Readbacks run the full quality ladder — elevenlabs, then omnivoice, then the OS
voice — descending a rung whenever one is unusable, so an unattended turn
degrades in voice rather than falling silent. TALKBACK_HOOK_BACKEND (or
`--on --backend say`) pins a rung and only descends from there.
"""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent

#: The complete CLI surface, in one place. `--help` prints it, and a test in
#: tests/test_talkback_docs.py asserts every flag the dispatcher accepts appears
#: here AND in SKILL.md — an undocumented flag is a flag no agent will ever use,
#: and the failure is silent in both directions.
USAGE = """\
usage: talkback-hook.py <command> [options]
       talkback-hook.py                  # no args: run as a hook, payload on stdin

commands:
  --on [full|brief|marker]   talk mode ON for THIS session (detail level, default full)
  --off                      stop talking in this session
  --status                   mode, backend, output, who else is talking, is it registered
  --sessions                 every session currently talking
  --outputs                  audio output devices on this host
  --install                  register the Stop + SessionEnd hooks in ~/.claude/settings.json
  --uninstall                remove them again
  -h, --help                 this text

options:
  --global                   --on/--off act on the machine-wide flag: EVERY session speaks
  --all                      --off kill switch: clear every session flag and the global one
  --backend <name>           elevenlabs | omnivoice | say — the top rung for this session
  --output <device>          output device, by name or `say -a` id (list them with --outputs)
  --session <id>             target another session instead of the current one
  --quiet                    --on skips the spoken "talk mode on" confirmation
  --dry-run                  --install prints what would change and writes nothing

one-off speech (not talk mode) lives in the sibling script:
  talkback.py --help
"""

#: How much of the turn gets spoken. `--on` will set any of these.
MODES = ("full", "brief", "marker")
#: `always` was 0.3.0's name for "speak every turn"; it meant the capped
#: opening. It now resolves to `full`, because a readback you come back to has
#: to carry the details, not a preview of them.
MODE_ALIASES = {"always": "full"}
#: `--off` writes `off` as a session tombstone when a global flag is set —
#: without it, deleting the session flag would fall back to the global one and
#: "stop talking" would not stop the talking.
MUTED = "off"
READABLE_MODES = MODES + (MUTED,) + tuple(MODE_ALIASES)
#: A session opts in deliberately and wants to hear the work, in full.
SESSION_DEFAULT_MODE = "full"
#: The machine-wide flag makes every agent audible, so it stays conservative.
GLOBAL_DEFAULT_MODE = "marker"

#: `brief` only: where the opening excerpt is cut.
CAP = int(os.environ.get("TALKBACK_HOOK_CHARS", "320"))
# In `brief` mode, a turn shorter than this is an acknowledgement, not a report,
# and narrating a preview of it costs more attention than it returns. `full`
# has no floor: if you asked to hear the session, "done, tests green" is a
# result you want, not noise.
MIN_CHARS = int(os.environ.get("TALKBACK_HOOK_MIN_CHARS", "80"))
#: `full` speaks the whole turn. 0 = no ceiling; set a number to bound a very
#: long one. It is off by default deliberately — a ceiling on `full` turns it
#: back into `brief` at exactly the turns worth hearing in full.
FULL_MAX_CHARS = int(os.environ.get("TALKBACK_FULL_MAX_CHARS", "0"))
#: What a new readback does to one still playing: `interrupt` (newest wins) or
#: `queue` (play them in order, so a long detailed readback is never cut off).
ON_OVERLAP = os.environ.get("TALKBACK_ON_OVERLAP", "interrupt").strip().lower()
#: Talk mode uses the full quality ladder by default: elevenlabs → omnivoice →
#: say. talkback.py descends it on its own when a rung is unusable — no key,
#: quota spent, local server down — so an unattended readback degrades in voice
#: rather than going missing. The ElevenLabs reserve guard still stands, so a
#: chatty session runs the balance down to the reserve and then keeps talking on
#: the next rung.
HOOK_BACKEND = os.environ.get("TALKBACK_HOOK_BACKEND", "elevenlabs")
# A session flag whose session has been silent this long is from a session that
# is gone. Every fire touches the live flag, so this is an idle timeout, not a
# lifetime cap: a twelve-hour session keeps talking.
TTL_HOURS = float(os.environ.get("TALKBACK_SESSION_TTL_HOURS", "24"))
BARGE_IN = (os.environ.get("TALKBACK_BARGE_IN", "1") not in ("0", "false", "no")
            and ON_OVERLAP != "queue")

MARKER_RE = re.compile(r"<!--\s*talkback:\s*(.+?)\s*-->", re.S | re.I)
#: Session ids are uuids. Anything that is not one is not allowed to become a
#: path segment — the key arrives from a hook payload, and `../../` in it would
#: otherwise let the flag file escape the state directory.
SAFE_KEY_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")

SETTINGS = Path.home() / ".claude" / "settings.json"
HOOK_EVENTS = ("Stop", "SessionEnd")


# --------------------------------------------------------------------------
# state paths — functions, not constants, so TALKBACK_HOME is honoured after
# import (the tests set it per-case)
# --------------------------------------------------------------------------

def state_dir() -> Path:
    return Path(os.environ.get("TALKBACK_HOME", Path.home() / ".talkback"))


def sessions_dir() -> Path:
    return state_dir() / "sessions"


def global_flag() -> Path:
    return state_dir() / "hook-enabled"


def speech_pid_file() -> Path:
    return state_dir() / "speaking.pid"


def install_marker() -> Path:
    return state_dir() / "installed-at"


# --------------------------------------------------------------------------
# session identity
# --------------------------------------------------------------------------

def safe_key(key: str | None) -> str | None:
    """Return `key` if it can safely be a filename, else None."""
    if not key:
        return None
    key = key.strip()
    return key if SAFE_KEY_RE.fullmatch(key) else None


def payload_keys(payload: dict) -> list[str]:
    """Every identifier this hook payload could be keyed under.

    `session_id` is the identifier. `transcript_path` carries the same id as its
    filename stem, and is checked too so the gate still resolves if a harness
    ever omits the field — a missing key would make the session silent, which is
    a failure that looks exactly like working correctly.
    """
    keys: list[str] = []
    for candidate in (
        payload.get("session_id"),
        Path(str(payload["transcript_path"])).stem if payload.get("transcript_path") else None,
    ):
        k = safe_key(candidate if isinstance(candidate, str) else None)
        if k and k not in keys:
            keys.append(k)
    return keys


def project_slug(cwd: str) -> str:
    """Claude Code's transcript directory name for a working directory."""
    return re.sub(r"[^A-Za-z0-9]", "-", cwd)


def newest_transcript_session(cwd: str | None = None) -> str | None:
    """Last-resort session id: the newest transcript for this directory."""
    base = Path.home() / ".claude" / "projects" / project_slug(cwd or os.getcwd())
    try:
        files = [p for p in base.glob("*.jsonl") if p.is_file()]
    except OSError:
        return None
    if not files:
        return None
    return safe_key(max(files, key=lambda p: p.stat().st_mtime).stem)


def cli_session_id(explicit: str | None = None) -> str | None:
    """The session id of the Claude Code session running this command."""
    if explicit:
        return safe_key(explicit)
    for var in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_SESSION_ID"):
        k = safe_key(os.environ.get(var))
        if k:
            return k
    return newest_transcript_session()


def session_started_at(session_id: str) -> float | None:
    """When this session's transcript was created — i.e. when it started."""
    base = Path.home() / ".claude" / "projects"
    try:
        for path in base.glob(f"*/{session_id}.jsonl"):
            st = path.stat()
            return getattr(st, "st_birthtime", st.st_mtime)
    except OSError:
        return None
    return None


def registered_after_session_started(session_id: str | None) -> bool:
    """Was the hook registered after this session began?

    Claude Code snapshots its hook registrations at session start, so a hook
    added mid-session does not fire until the next one. Turning talk mode on in
    such a session produces silence that is indistinguishable from the feature
    not working — which is exactly what a default-silent design looks like when
    it breaks. Say so instead.
    """
    if not session_id:
        return False
    try:
        installed = float(install_marker().read_text().strip())
    except (OSError, ValueError):
        return False  # installed before this was recorded — do not guess
    started = session_started_at(session_id)
    return started is not None and installed > started


# --------------------------------------------------------------------------
# flag files
# --------------------------------------------------------------------------

def read_config(path: Path) -> dict | None:
    """Read a flag file. Returns None when it does not exist."""
    try:
        body = path.read_text().strip()
    except OSError:
        return None
    if not body:
        return {}
    if body.lower() in READABLE_MODES:
        return {"mode": body.lower()}  # pre-0.3.0 format: a bare mode word
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def write_config(path: Path, config: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2) + "\n")


def resolve_state(keys: list[str]) -> tuple[dict, str, Path] | None:
    """Is talk mode on for a session with any of these keys?

    Session scope wins over the global flag, so `--off` in a session that opted
    in is honoured even while the machine-wide flag is set.
    """
    for key in keys:
        path = sessions_dir() / key
        config = read_config(path)
        if config is not None:
            config.setdefault("mode", SESSION_DEFAULT_MODE)
            return config, "session", path
    config = read_config(global_flag())
    if config is not None:
        config.setdefault("mode", GLOBAL_DEFAULT_MODE)
        return config, "global", global_flag()
    return None


def normalize_mode(mode: str | None) -> str | None:
    """Canonical mode name, or None if it is not one."""
    if not mode:
        return None
    mode = mode.strip().lower()
    mode = MODE_ALIASES.get(mode, mode)
    return mode if mode in MODES + (MUTED,) else None


def effective_mode(config: dict) -> str:
    return (normalize_mode(os.environ.get("TALKBACK_HOOK_MODE"))
            or normalize_mode(config.get("mode"))
            or SESSION_DEFAULT_MODE)


def effective_backend(config: dict) -> str:
    env = os.environ.get("TALKBACK_HOOK_BACKEND", "").strip()
    if env:
        return env
    backend = str(config.get("backend", "")).strip()
    return backend or HOOK_BACKEND


def effective_output(config: dict) -> str:
    """Which audio output this session's readbacks come out of.

    Per session, not per machine: sessions are driven from different devices and
    land on different speakers. Empty means the host's system output.
    """
    env = os.environ.get("TALKBACK_OUTPUT", "").strip()
    if env:
        return env
    return str(config.get("output", "")).strip()


def prune_stale(now: float | None = None) -> list[str]:
    """Drop flags for sessions that have gone quiet past the idle TTL.

    SessionEnd removes a flag on a clean exit; this covers the sessions that
    never got one — a killed terminal, a crashed harness.
    """
    if TTL_HOURS <= 0:
        return []
    now = time.time() if now is None else now
    cutoff = now - TTL_HOURS * 3600
    dropped = []
    try:
        entries = list(sessions_dir().iterdir())
    except OSError:
        return []
    for path in entries:
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
                dropped.append(path.name)
        except OSError:
            continue
    return dropped


def enabled_sessions() -> list[tuple[str, dict]]:
    try:
        entries = sorted(p for p in sessions_dir().iterdir() if p.is_file())
    except OSError:
        return []
    return [(p.name, read_config(p) or {}) for p in entries]


# --------------------------------------------------------------------------
# speaking
# --------------------------------------------------------------------------

def last_assistant_text(transcript: Path) -> str:
    """Pull the final assistant prose out of a Claude Code JSONL transcript."""
    text = ""
    try:
        with transcript.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if e.get("type") != "assistant":
                    continue
                content = (e.get("message") or {}).get("content")
                if isinstance(content, str):
                    text = content
                elif isinstance(content, list):
                    parts = [
                        c.get("text", "")
                        for c in content
                        if isinstance(c, dict) and c.get("type") == "text"
                    ]
                    joined = "\n".join(p for p in parts if p.strip())
                    if joined.strip():
                        text = joined
    except OSError:
        return ""
    return text


def _cut_at_sentence(body: str, cap: int) -> str:
    if len(body) <= cap:
        return body
    cut = body[:cap]
    for sep in (". ", "! ", "? "):
        i = cut.rfind(sep)
        if i > cap // 3:
            return cut[: i + 1]
    return cut.rsplit(" ", 1)[0] + "..."


def readback(text: str, mode: str = SESSION_DEFAULT_MODE) -> str | None:
    """What to speak for this turn, or None to stay silent.

    `full` is the default because the point of a readback is to be able to walk
    away and come back knowing what happened. A capped excerpt is a preview of
    the answer, not the answer — you would still have to read the screen, which
    is the thing talk mode exists to avoid. What does get dropped is what cannot
    be heard at all (code fences, URLs, deep paths — `talkback.py` handles
    that), not what is merely long.
    """
    m = MARKER_RE.search(text)
    headline = (m.group(1).strip() if m else "")
    body = MARKER_RE.sub("", text).strip()

    if mode == MUTED:
        return None
    if mode == "marker":
        return headline or None
    if mode == "brief":
        if headline:
            return headline
        if len(body) < MIN_CHARS:
            return None
        return _cut_at_sentence(body, CAP)

    # full — the whole turn, led by the marker when the agent wrote one
    if not body:
        return headline or None
    spoken = f"{headline} {body}".strip() if headline else body
    if FULL_MAX_CHARS > 0:
        spoken = _cut_at_sentence(spoken, FULL_MAX_CHARS)
    return spoken or None


def _is_our_speech(pid: int) -> bool:
    """Guard against pid reuse: only kill a process that is still talkback."""
    try:
        out = subprocess.run(
            ["ps", "-o", "command=", "-p", str(pid)],
            capture_output=True, text=True, timeout=3,
        ).stdout
    except Exception:
        return False
    return "talkback.py" in out


def stop_previous_speech() -> None:
    """Cut off audio still playing from an earlier turn.

    In continuous mode turns end faster than a readback plays. Two voices over
    each other is worse than either one, and the newest summary is the one worth
    hearing, so the new utterance interrupts rather than queues.
    """
    if not BARGE_IN:
        return
    pid_file = speech_pid_file()
    try:
        pid = int(pid_file.read_text().strip())
    except (OSError, ValueError):
        return
    if pid > 0 and _is_our_speech(pid):
        try:
            os.killpg(pid, signal.SIGTERM)
        except OSError:
            pass
    pid_file.unlink(missing_ok=True)


def speak_detached(spoken: str, backend: str, output: str = "") -> int | None:
    """Fire the utterance without holding the turn open for the audio."""
    stop_previous_speech()
    cmd = [sys.executable, str(HERE / "talkback.py"), "-b", backend]
    if output:
        cmd += ["-d", output]
    env = {**os.environ, "TALKBACK_ON_OVERLAP": ON_OVERLAP}
    try:
        proc = subprocess.Popen(
            cmd + ["--", spoken],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            env=env,
            start_new_session=True,  # its own process group, so barge-in can kill it
        )
    except Exception:
        return None
    try:
        speech_pid_file().parent.mkdir(parents=True, exist_ok=True)
        speech_pid_file().write_text(str(proc.pid) + "\n")
    except OSError:
        pass
    return proc.pid


# --------------------------------------------------------------------------
# hook registration
# --------------------------------------------------------------------------

def _registered_events(settings: dict) -> set[str]:
    found = set()
    for event, matchers in (settings.get("hooks") or {}).items():
        for matcher in matchers or []:
            for hook in matcher.get("hooks", []) or []:
                if "talkback-hook.py" in str(hook.get("command", "")):
                    found.add(event)
    return found


def install(dry_run: bool = False) -> int:
    """Register the hook for every session, permanently.

    The toggle needs the hook present before a session starts in order to be
    flippable during it, so registration is global and the *flag* is what scopes
    it. A session that never opts in pays one no-op process per turn.
    """
    command = str(HERE / "talkback-hook.py")
    try:
        settings = json.loads(SETTINGS.read_text()) if SETTINGS.exists() else {}
    except (OSError, json.JSONDecodeError) as e:
        print(f"cannot read {SETTINGS}: {e}", file=sys.stderr)
        return 1

    already = _registered_events(settings)
    missing = [e for e in HOOK_EVENTS if e not in already]
    if not missing:
        print(f"talkback hook: already registered for {', '.join(sorted(already))}")
        return 0

    hooks = settings.setdefault("hooks", {})
    for event in missing:
        hooks.setdefault(event, []).append(
            {"hooks": [{"type": "command", "command": command, "timeout": 10}]}
        )

    if dry_run:
        print(f"would add to {SETTINGS}:")
        for event in missing:
            print(f"  {event}: {command}")
        return 0

    backup = SETTINGS.with_suffix(f".json.talkback-bak-{int(time.time())}")
    try:
        if SETTINGS.exists():
            backup.write_text(SETTINGS.read_text())
        SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS.write_text(json.dumps(settings, indent=2) + "\n")
    except OSError as e:
        print(f"cannot write {SETTINGS}: {e}", file=sys.stderr)
        return 1
    try:
        install_marker().parent.mkdir(parents=True, exist_ok=True)
        install_marker().write_text(f"{time.time()}\n")
    except OSError:
        pass
    print(f"talkback hook: registered for {', '.join(missing)}")
    print(f"  backup: {backup}")
    print("  restart Claude Code to pick it up; it stays silent until --on")
    return 0


def uninstall() -> int:
    try:
        settings = json.loads(SETTINGS.read_text()) if SETTINGS.exists() else {}
    except (OSError, json.JSONDecodeError) as e:
        print(f"cannot read {SETTINGS}: {e}", file=sys.stderr)
        return 1
    hooks = settings.get("hooks") or {}
    removed = []
    for event, matchers in list(hooks.items()):
        kept = []
        for matcher in matchers or []:
            inner = [
                h for h in matcher.get("hooks", []) or []
                if "talkback-hook.py" not in str(h.get("command", ""))
            ]
            if len(inner) != len(matcher.get("hooks", []) or []):
                removed.append(event)
            if inner:
                kept.append({**matcher, "hooks": inner})
        if kept:
            hooks[event] = kept
        else:
            hooks.pop(event, None)
    if not removed:
        print("talkback hook: not registered")
        return 0
    backup = SETTINGS.with_suffix(f".json.talkback-bak-{int(time.time())}")
    try:
        backup.write_text(SETTINGS.read_text())
        SETTINGS.write_text(json.dumps(settings, indent=2) + "\n")
    except OSError as e:
        print(f"cannot write {SETTINGS}: {e}", file=sys.stderr)
        return 1
    print(f"talkback hook: unregistered from {', '.join(sorted(set(removed)))}")
    print(f"  backup: {backup}")
    return 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _flag(argv: list[str], name: str) -> bool:
    return name in argv


def _opt(argv: list[str], name: str) -> str | None:
    if name in argv:
        i = argv.index(name)
        if i + 1 < len(argv):
            return argv[i + 1]
    return None


def cmd_on(argv: list[str]) -> int:
    is_global = _flag(argv, "--global")
    positional = [a for a in argv[1:] if not a.startswith("--")]
    # `--session X` / `--backend Y` values are options, not the mode word
    for opt in ("--session", "--backend", "--output"):
        val = _opt(argv, opt)
        if val in positional:
            positional.remove(val)
    raw_mode = (positional[0] if positional
                else (GLOBAL_DEFAULT_MODE if is_global else SESSION_DEFAULT_MODE))
    mode = normalize_mode(raw_mode)
    if mode is None or mode == MUTED:
        print(f"unknown mode {raw_mode!r} — expected one of {', '.join(MODES)}",
              file=sys.stderr)
        return 2

    config = {"mode": mode}
    backend = _opt(argv, "--backend")
    if backend:
        config["backend"] = backend
    output = _opt(argv, "--output")
    if output:
        config["output"] = output
    config["enabled_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")

    if is_global:
        write_config(global_flag(), config)
        print(f"talkback: GLOBAL talk mode ON (mode={mode})")
        print("  every Claude Code session on this machine will speak — including")
        print("  parallel agents. `--off --all` to clear it.")
        return 0

    sid = cli_session_id(_opt(argv, "--session"))
    if not sid:
        print("cannot determine the session id — pass --session <id>", file=sys.stderr)
        print("  (CLAUDE_CODE_SESSION_ID is unset and no transcript matched this cwd)",
              file=sys.stderr)
        return 2
    config["cwd"] = os.getcwd()
    write_config(sessions_dir() / sid, config)
    prune_stale()
    out = effective_output(config)
    print(f"talkback: talk mode ON for session {sid} (mode={mode}, "
          f"backend={effective_backend(config)}, output={out or 'system default'})")
    if mode == "full":
        print("  speaks the whole of every turn — this session only")
    elif mode == "brief":
        print(f"  speaks the opening {CAP} chars of every turn over {MIN_CHARS}")
    else:
        print("  speaks only on turns carrying a <!-- talkback: ... --> marker")
    if registered_after_session_started(sid):
        print("  ⚠ this session started BEFORE the hook was registered, so the")
        print("    harness never loaded it here — nothing will be spoken until you")
        print("    restart Claude Code and run --on again in the new session.")
    others = [k for k, _ in enabled_sessions() if k != sid]
    if others:
        print(f"  note: {len(others)} other session(s) also have talk mode on")
    if read_config(global_flag()) is not None:
        print("  note: the GLOBAL flag is also set — every session speaks. `--off --all`.")
    if not _flag(argv, "--quiet"):
        speak_detached("Talk mode on.", effective_backend(config), effective_output(config))
    return 0


def cmd_off(argv: list[str]) -> int:
    if _flag(argv, "--all"):
        removed = 0
        try:
            for path in sessions_dir().iterdir():
                if path.is_file():
                    path.unlink(missing_ok=True)
                    removed += 1
        except OSError:
            pass
        had_global = global_flag().exists()
        global_flag().unlink(missing_ok=True)
        stop_previous_speech()
        print(f"talkback: OFF everywhere ({removed} session flag(s) cleared"
              f"{', global flag cleared' if had_global else ''})")
        return 0

    sid = cli_session_id(_opt(argv, "--session"))
    if not sid:
        print("cannot determine the session id — pass --session <id>", file=sys.stderr)
        return 2
    flag = sessions_dir() / sid
    global_set = read_config(global_flag()) is not None
    if global_set:
        # Deleting the flag would hand the session back to the global one.
        write_config(flag, {"mode": MUTED, "muted_at": time.strftime("%Y-%m-%dT%H:%M:%S")})
        print(f"talkback: talk mode OFF for session {sid} (muted over the global flag)")
        print("  the GLOBAL flag is still set for other sessions — `--off --all` clears it")
    elif flag.exists():
        flag.unlink(missing_ok=True)
        print(f"talkback: talk mode OFF for session {sid}")
    else:
        print("talkback: talk mode was not on for this session")
    stop_previous_speech()
    return 0


def cmd_status(argv: list[str]) -> int:
    prune_stale()
    sid = cli_session_id(_opt(argv, "--session"))
    state = resolve_state([sid] if sid else [])
    if state is None:
        print("talkback: talk mode OFF for this session")
    elif effective_mode(state[0]) == MUTED:
        print("talkback: talk mode OFF for this session (muted over the global flag)")
    else:
        config, scope, _ = state
        print(f"talkback: talk mode ON for this session via the {scope} flag "
              f"(mode={effective_mode(config)}, backend={effective_backend(config)}, "
              f"output={effective_output(config) or 'system default'})")
    print(f"  session id: {sid or '(unknown)'}")

    others = [(k, c) for k, c in enabled_sessions() if k != sid]
    if others:
        print(f"  other sessions talking ({len(others)}):")
        for key, config in others:
            print(f"    {key}  mode={config.get('mode', SESSION_DEFAULT_MODE)}"
                  f"  cwd={config.get('cwd', '?')}")
    else:
        print("  no other session is talking")
    print(f"  global flag: {'SET' if global_flag().exists() else 'unset'}")
    if registered_after_session_started(sid):
        print("  ⚠ hook registered AFTER this session started — not loaded here;"
              " restart to activate")

    try:
        settings = json.loads(SETTINGS.read_text()) if SETTINGS.exists() else {}
        registered = _registered_events(settings)
    except (OSError, json.JSONDecodeError):
        registered = set()
    if registered:
        print(f"  hook registered for: {', '.join(sorted(registered))}")
    else:
        print(f"  hook NOT registered in {SETTINGS} — run --install")
    return 0


def cmd_sessions() -> int:
    prune_stale()
    rows = enabled_sessions()
    if not rows:
        print("no session has talk mode on")
        return 0
    for key, config in rows:
        print(f"{key}  mode={config.get('mode', SESSION_DEFAULT_MODE)}"
              f"  backend={config.get('backend', HOOK_BACKEND)}"
              f"  output={config.get('output', 'system default')}"
              f"  cwd={config.get('cwd', '?')}")
    return 0


def cli(argv: list[str]) -> int | None:
    if not argv:
        return None
    cmd = argv[0]
    if cmd == "--on":
        return cmd_on(argv)
    if cmd == "--off":
        return cmd_off(argv)
    if cmd == "--status":
        return cmd_status(argv)
    if cmd == "--sessions":
        return cmd_sessions()
    if cmd == "--outputs":
        # One implementation of device enumeration, in talkback.py.
        return subprocess.run([sys.executable, str(HERE / "talkback.py"), "--outputs"]).returncode
    if cmd == "--install":
        return install(dry_run=_flag(argv, "--dry-run"))
    if cmd == "--uninstall":
        return uninstall()
    if cmd in ("-h", "--help"):
        print(__doc__)
        print(USAGE)
        return 0
    return None


# --------------------------------------------------------------------------
# hook entry
# --------------------------------------------------------------------------

def handle_session_end(keys: list[str]) -> int:
    """Talk mode never outlives the session that asked for it."""
    for key in keys:
        (sessions_dir() / key).unlink(missing_ok=True)
    stop_previous_speech()
    prune_stale()
    return 0


def handle_stop(payload: dict, keys: list[str]) -> int:
    state = resolve_state(keys)
    if state is None:
        return 0  # this session did not opt in: silent, no trace
    config, _scope, flag_path = state
    # A muted session is silenced inside readback(), which is the one place that
    # decides what a mode means. An early-out here as well would be a second
    # site enforcing the same rule, and a rule spelled at two sites is a rule a
    # mutation at either site survives.
    mode = effective_mode(config)

    tp = payload.get("transcript_path")
    if not tp:
        return 0
    text = last_assistant_text(Path(str(tp)).expanduser())
    if not text.strip():
        return 0

    spoken = readback(text, mode)
    if not spoken or not spoken.strip():
        return 0

    speak_detached(spoken, effective_backend(config), effective_output(config))
    # Mark the session live, so the idle TTL only ever reaps sessions that ended
    # without a SessionEnd.
    try:
        os.utime(flag_path, None)
    except OSError:
        pass
    return 0


def main() -> int:
    rc = cli(sys.argv[1:])
    if rc is not None:
        return rc

    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    if not isinstance(payload, dict):
        return 0

    keys = payload_keys(payload)
    event = str(payload.get("hook_event_name", "Stop"))

    try:
        if event == "SessionEnd":
            return handle_session_end(keys)
        if not keys:
            return 0  # no identity, no isolation guarantee — stay silent
        return handle_stop(payload, keys)
    except Exception:
        return 0  # a readback is never worth blocking a turn over


if __name__ == "__main__":
    sys.exit(main())

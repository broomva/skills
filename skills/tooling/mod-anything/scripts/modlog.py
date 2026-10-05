#!/usr/bin/env python3
"""modlog — the journal, route record and stall breaker for a mod-anything run.

Every command reads and writes two files in the working folder:

  MODLOG.md      the human-readable journal (append-only)
  .modlog.json   the machine state the breaker and the field-note scaffold read

Commands
  init       --target T --idea I [--done D] [--in-repo]
                                                 start a journal (refuses to overwrite). The
                                                 working folder belongs outside every git repo
                                                 (mktemp -d): the journal may hold private
                                                 detail. --in-repo overrides, on purpose
  log        --text T [--evidence PATH...]       a free journal entry (recon facts, the lab's
                                                 restore path); needs no route
  route      --rung R --name N --reason TEXT [--subgoal S] [--supersedes N]
                                                 record the route for the current (sub)goal;
                                                 R is 1-5 or "passthrough"; --supersedes marks
                                                 an earlier route's reasoning as replaced
  ok         --step TEXT --evidence PATH...      record a verified step; every evidence
                                                 path must exist, or the step is refused
  fail       --sig TEXT [--detail D] [--limit N] record a failure; the Nth repeat of the
                                                 same signature on the same route is a
                                                 STALL (exit 3) with the re-rank checklist
  status                                         print the current route and failure counts
  note       --out PATH [--force]                scaffold a field note from the journal. Each
                                                 journal evidence file becomes a placeholder:
                                                 copy it into the ship tree and cite it there,
                                                 or describe it without a path
  lint-note  PATH [--root DIR]                   check a field note is complete and shippable
                                                 (exit 1 if not). Evidence cited under
                                                 ## Verification must exist inside DIR (default:
                                                 the enclosing skill, else the note's folder):
                                                 absolute, ~/, .. and file:// paths fail (it
                                                 reads backticks, inline links and reference
                                                 definitions there). The Envelope needs
                                                 one Disclosure line: none found | embargoed
                                                 (fails) | cleared YYYY-MM-DD (a real date, not
                                                 in the future). The word "embargoed" anywhere
                                                 in the note fails

Exit codes: 0 ok · 1 lint findings · 2 usage, refused input, or a file or folder it could not
read or write · 3 STALL. Pure stdlib.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as _dt
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

try:  # POSIX file locking; on Windows the journal is used unlocked (one writer at a time)
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None

RUNGS = {
    "1": "data and config",
    "2": "sanctioned API",
    "3": "patch from inside",
    "4": "hooks and wires",
    "5": "reimplement against the original",
    "passthrough": "passthrough (two programs at once)",
}
DEFAULT_LIMIT = 3
STATE = ".modlog.json"
JOURNAL = "MODLOG.md"
TODO = "TODO(mod-anything)"
NONE_HIT = "None hit on this run (the journal recorded no failure)."


NOTE_SECTIONS = (
    "Versions",
    "Route",
    "What it really does",
    "Verification",
    "Gotchas",
    "Envelope",
)

STALL_TEXT = """STALL: "{sig}" has now failed {count} times on route #{route} ({rung}: {name}).

Stop repeating it. Re-rank the routes for THIS sub-goal before the next attempt:
  0. The new route must pass the skill's Rules again. A rung the Rules (or the target's
     terms) excluded stays excluded under a stall: a stall is not a reason to cross them.
  1. Can the original simply be run? As a binary, a container, a library, or through
     the target's own API, instead of rebuilding what it already does.
  2. Is a cheaper rung enough for this sub-goal? (1 data/config, 2 sanctioned API,
     3 patch from inside, 4 hooks and wires, 5 reimplement)
  3. Is the oracle wrong? Check the running target, not your reading of the code.
     For a hang, sample the stuck process (macOS: `sample <pid> 1`) and cite that artifact
     in the new route's reason, rather than a guess.
  4. Otherwise ask the user, with what you know written down.
Record the decision with `modlog.py route ...` (a new route resets this count)."""


class Refused(Exception):
    """Input the journal will not accept (exit 2)."""


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_sig(sig: str) -> str:
    """One failure, one key: Unicode form (NFKC, so macOS's decomposed text and full-width
    letters compare equal), case, invisible format characters, surrounding space and
    trailing punctuation do not make a failure new. Anything else does — the breaker must
    not merge two different failures."""
    s = unicodedata.normalize("NFKC", sig)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Cf")
    s = re.sub(r"\s+", " ", s.strip().casefold())
    return s.rstrip(" .:;!")


def load(d: Path) -> dict:
    p = d / STATE
    if not p.exists():
        raise Refused(f"no journal in {d} — run `modlog.py init` first")
    try:
        state = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        raise Refused(f"{p} is unreadable ({e}); restore it from MODLOG.md or start a new journal")
    if not isinstance(state, dict) or not all(isinstance(state.get(k), str) and state[k].strip()
                                              for k in ("target", "idea")):
        raise Refused(f"{p} is not a modlog journal (no target/idea)")
    problem = _schema_problem(state)
    if problem:
        raise Refused(f"{p} is not a modlog journal ({problem})")
    return state


# The one place the journal's shape is decided: every command reads through load().
_ENTRY_FIELDS = {
    "routes": {"n": int, "rung": str, "name": str, "reason": str},
    "logs": {"text": str, "evidence": list},
    "steps": {"step": str, "evidence": list, "route": int},
    "failures": {"sig": str, "route": int, "count": int},
    "stalls": {"sig": str, "route": int, "count": int},
}


def _schema_problem(state: dict) -> str | None:
    for key, fields in _ENTRY_FIELDS.items():
        entries = state.setdefault(key, [])
        if not isinstance(entries, list):
            return f"{key!r} is not a list"
        for i, e in enumerate(entries, 1):
            if not isinstance(e, dict):
                return f"{key} entry {i} is not an object"
            for f, typ in fields.items():
                if not isinstance(e.get(f), typ) or isinstance(e.get(f), bool):
                    return f"{key} entry {i} has no valid {f!r}"
            if "evidence" in fields and not all(isinstance(x, str) and x for x in e["evidence"]):
                return f"{key} entry {i} has an evidence item that is not a path"
    if not isinstance(state.get("done", ""), str):
        return "'done' is not text"
    n_routes = len(state["routes"])
    for key in ("steps", "failures", "stalls"):
        for i, e in enumerate(state[key], 1):
            if not 1 <= e["route"] <= n_routes:
                return f"{key} entry {i} points at route #{e['route']}, which does not exist"
            if key != "steps" and e["count"] < 1:
                return f"{key} entry {i} has a count below 1"
    for i, r in enumerate(state["routes"], 1):
        if r["n"] != i or r["rung"] not in RUNGS:
            return f"route #{i} is malformed"
        sup = r.get("superseded_by")
        if sup is not None and (not isinstance(sup, int) or isinstance(sup, bool) or not i < sup <= len(state["routes"])):
            return f"route #{i} has an invalid superseded_by {sup!r}"
    if "limit" in state:
        lim = state["limit"]
        if not isinstance(lim, int) or isinstance(lim, bool) or not 1 <= lim <= DEFAULT_LIMIT:
            return f"limit must be an integer from 1 to {DEFAULT_LIMIT}, got {lim!r}"
    return None


def save(d: Path, state: dict) -> None:
    """Atomic: write a temp file and rename it over the state, so a crash or a concurrent
    reader never sees a half-written journal."""
    tmp = d / (STATE + f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, d / STATE)


@contextlib.contextmanager
def locked(d: Path):
    """Serialize read-modify-write commands on one journal, so two `fail` calls running at
    once cannot both read count 2 and both write 3."""
    if fcntl is None or not d.is_dir():
        yield
        return
    try:
        fd = os.open(d, os.O_RDONLY)  # lock the folder itself: no lock file to clutter a mod
    except OSError as e:
        raise Refused(f"cannot open {d} to lock the journal: {e.strerror or e}")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def append(d: Path, text: str) -> None:
    with (d / JOURNAL).open("a", encoding="utf-8") as f:
        f.write(text.rstrip("\n") + "\n\n")


def _enclosing_repo(d: Path) -> Path | None:
    for a in [d.resolve(), *d.resolve().parents]:
        if (a / ".git").exists():
            return a
    return None


def cmd_init(d: Path, target: str, idea: str, done: str | None, in_repo: bool = False) -> dict:
    if not target.strip() or not idea.strip():
        raise Refused("--target and --idea must be non-empty")
    repo = _enclosing_repo(d)
    if repo is not None and not in_repo:
        raise Refused(f"{d} is inside the git repo {repo}. Keep the working folder outside every repo "
                      "(mktemp -d): the journal can hold private detail, and a repo publishes it. "
                      "Pass --in-repo only for a journal you mean to publish")
    if (d / STATE).exists() or (d / JOURNAL).exists():
        raise Refused(f"a journal already exists in {d}; continue it instead of starting over")
    d.mkdir(parents=True, exist_ok=True)
    state = {
        "target": target.strip(),
        "idea": idea.strip(),
        "done": (done or "working in the real target, with evidence").strip(),
        "created": _now(),
        "routes": [],
        "logs": [],
        "steps": [],
        "failures": [],
        "stalls": [],
    }
    save(d, state)
    (d / JOURNAL).write_text(
        f"# MODLOG — {state['target']}\n\n"
        f"- Idea: {state['idea']}\n"
        f"- Done means: {state['done']}\n"
        f"- Started: {state['created']}\n\n"
        "Anything not in this journal is lost at the next context compaction.\n\n",
        encoding="utf-8",
    )
    return state


def cmd_route(d: Path, rung: str, name: str, reason: str, subgoal: str | None,
              supersedes: int | None = None) -> dict:
    state = load(d)
    if supersedes is not None and not 1 <= supersedes <= len(state["routes"]):
        raise Refused(f"--supersedes {supersedes}: no such route (have {len(state['routes'])})")
    if supersedes is not None and state["routes"][supersedes - 1].get("superseded_by"):
        raise Refused(f"route #{supersedes} was already superseded by "
                      f"#{state['routes'][supersedes - 1]['superseded_by']}")
    if rung not in RUNGS:
        raise Refused(f"--rung must be one of {', '.join(RUNGS)}; got {rung!r}")
    if not name.strip() or not reason.strip():
        raise Refused("--name and --reason must be non-empty: a route without a reason is a guess")
    entry = {
        "n": len(state["routes"]) + 1,
        "rung": rung,
        "name": name.strip(),
        "reason": reason.strip(),
        "subgoal": (subgoal or "").strip() or None,
        "at": _now(),
    }
    if supersedes is not None:
        state["routes"][supersedes - 1]["superseded_by"] = entry["n"]
    state["routes"].append(entry)
    save(d, state)
    scope = f" (sub-goal: {entry['subgoal']})" if entry["subgoal"] else ""
    sup = f" · Supersedes route #{supersedes}" if supersedes is not None else ""
    append(d, f"## Route #{entry['n']} — rung {rung} ({RUNGS[rung]}): {entry['name']}{scope}\n\n"
              f"{entry['at']} · Reason: {entry['reason']}{sup}")
    return entry


def cmd_log(d: Path, text: str, evidence: list[str]) -> dict:
    state = load(d)
    if not text.strip():
        raise Refused("--text must be non-empty")
    bad = _bad_evidence(d, evidence)
    if bad:
        raise Refused("bad evidence: " + ", ".join(bad))
    entry = {"text": text.strip(), "evidence": evidence, "at": _now()}
    state.setdefault("logs", []).append(entry)
    save(d, state)
    ev = (" — evidence: " + ", ".join(f"`{e}`" for e in evidence)) if evidence else ""
    append(d, f"- NOTE ({entry['at']}): {entry['text']}{ev}")
    return entry


def _current_route(state: dict) -> dict:
    if not state["routes"]:
        raise Refused("no route recorded yet — pick one with `modlog.py route` before building")
    return state["routes"][-1]


def cmd_ok(d: Path, step: str, evidence: list[str]) -> dict:
    state = load(d)
    route = _current_route(state)
    if not step.strip():
        raise Refused("--step must be non-empty")
    if not evidence:
        raise Refused("--evidence is required: knowledge that is not in an artifact does not exist")
    bad = _bad_evidence(d, evidence)
    if bad:
        raise Refused("bad evidence: " + ", ".join(bad))
    entry = {"step": step.strip(), "evidence": evidence, "route": route["n"], "at": _now()}
    state["steps"].append(entry)
    save(d, state)
    ev = ", ".join(f"`{e}`" for e in evidence)
    append(d, f"- OK ({entry['at']}, route #{route['n']}): {entry['step']} — evidence: {ev}")
    return entry


def _resolve(d: Path, p: str) -> Path:
    q = Path(p).expanduser()
    return q if q.is_absolute() else d / q


def _bad_evidence(d: Path, evidence: list[str]) -> list[str]:
    """Evidence must be an existing regular file that is not the journal itself."""
    journal = {(d / JOURNAL).resolve(), (d / STATE).resolve()}
    bad = []
    for e in evidence:
        p = _resolve(d, e)
        if not p.is_file():
            bad.append(f"{e} (not found or not a file)")
        elif p.resolve() in journal:
            bad.append(f"{e} (the journal cannot be its own evidence)")
    return bad


def cmd_fail(d: Path, sig: str, detail: str | None, limit: int | None) -> tuple[dict, bool]:
    state = load(d)
    stored = int(state.get("limit", DEFAULT_LIMIT))
    if limit is None:
        limit = stored
    elif limit < 1:
        raise Refused("--limit must be at least 1")
    elif limit > stored:
        raise Refused(f"--limit {limit} would raise the stall limit ({stored}); a stall is answered "
                      "by a re-rank, not by more attempts")
    else:
        state["limit"] = limit  # a lower limit, once set, holds for the rest of the journal
    route = _current_route(state)
    key = normalize_sig(sig)
    if not key:
        raise Refused("--sig must be non-empty")
    count = 1 + sum(1 for f in state["failures"] if f["route"] == route["n"] and f["sig"] == key)
    entry = {"sig": key, "text": re.sub(r"\s+", " ", sig.strip()), "detail": (detail or "").strip() or None,
             "route": route["n"], "count": count, "limit": limit, "at": _now()}
    state["failures"].append(entry)
    stalled = count >= limit
    if stalled:
        state["stalls"].append({"sig": key, "route": route["n"], "count": count, "at": entry["at"]})
    save(d, state)
    line = f"- FAIL ({entry['at']}, route #{route['n']}, x{count}): {entry['text']}"
    if entry["detail"]:
        line += f" — {entry['detail']}"
    if stalled:
        line += "\n- STALL: re-rank the routes for this sub-goal; first check whether the original can simply be run."
    append(d, line)
    return entry, stalled


def cmd_status(d: Path) -> str:
    state = load(d)
    out = [f"target: {state['target']}", f"idea:   {state['idea']}"]
    if state["routes"]:
        r = state["routes"][-1]
        out.append(f"route:  #{r['n']} rung {r['rung']} ({RUNGS[r['rung']]}): {r['name']}")
        counts: dict[str, int] = {}
        for f in state["failures"]:
            if f["route"] == r["n"]:
                counts[f["sig"]] = counts.get(f["sig"], 0) + 1
        for sig, c in sorted(counts.items(), key=lambda kv: -kv[1]):
            out.append(f"  x{c}  {sig}")
    else:
        out.append("route:  none yet")
    out.append(f"steps verified: {len(state['steps'])} · stalls: {len(state['stalls'])}")
    return "\n".join(out)


def cmd_note(d: Path, out: Path, force: bool) -> Path:
    state = load(d)
    if out.is_dir():
        raise Refused(f"{out} is a directory; give a file path for the note")
    if out.exists() and not force:
        raise Refused(f"{out} exists; pass --force to overwrite")
    routes = "\n".join(
        f"{r['n']}. Rung {r['rung']} ({RUNGS[r['rung']]}): {r['name']} — {r['reason']}"
        + (f" (sub-goal: {r['subgoal']})" if r.get("subgoal") else "")
        + (f" (superseded by #{r['superseded_by']})" if r.get("superseded_by") else "")
        for r in state["routes"]
    ) or f"{TODO}: no route was recorded"

    # Journal evidence lives in the working folder, which never ships. Each file is a
    # decision the agent makes on purpose: copy it into the ship tree (only if it was made
    # from a fixture you wrote) and cite it there, or describe it without a path.
    verification = "\n".join(
        f"- {s['step']}: " + "; ".join(
            f"{TODO}: {e} is in the working folder; copy it into examples/<slug>/ and cite "
            f"that path, or describe it without a path" for e in s["evidence"])
        for s in state["steps"]
    ) or f"- {TODO}: no verified step was recorded"
    seen: dict[str, str] = {}
    for f in state["failures"]:
        seen.setdefault(f["sig"], f.get("text") or f["sig"])
    # Gotchas are what the run hit. With no recorded failure the honest entry is "None hit";
    # a template that demands an item invites invented ones.
    gotchas = "\n".join(
        f"{i}. {text} → {TODO}: cause → {TODO}: fix" for i, text in enumerate(seen.values(), 1)
    ) or NONE_HIT
    stalls = "".join(
        f"\n- Stall on route #{s['route']}: {s['sig']} (x{s['count']})" for s in state["stalls"]
    )
    # The mod's rung comes from the main routes, not from lab or sub-goal routes.
    main = [r for r in state["routes"] if not r.get("subgoal") and not r.get("superseded_by")]
    pool = main or state["routes"]
    rung = ", ".join(dict.fromkeys(r["rung"] for r in pool)) if pool else "?"
    text = f"""# {state['target']}: {state['idea']}

## Versions

- Target: {TODO}: exact app/firmware/game version
- Platform: {TODO}: OS and version
- Tools: {TODO}: loader, SDK or tool versions

## Route

{routes}{stalls}

## What it really does

{TODO}: what the target actually does, as observed in the running original

## Verification

{verification}

## Gotchas

{gotchas}

## Envelope

- Rung: {rung}
- Terms checked: {TODO}: the target's terms permit this (cite them)
- Bytes shipped: only our own code, assets, patches or converters
- Disclosure: {TODO}: none found | embargoed (what, since YYYY-MM-DD) | cleared YYYY-MM-DD (how)
"""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return out


_HEADING = re.compile(r"^##\s+(.+?)\s*$", re.M)
_GOTCHA = re.compile(r"^\s*\d+\.\s+.+(?:→|->).+(?:→|->).+$", re.S)
# The Envelope's disclosure state line (references/envelope.md). The lint reads this one
# line; the other Disclosure rules are unconditional checks over the Envelope or the note.
_DISCLOSURE = re.compile(r"(?im)^\s*[-*+]?\s*Disclosure:\s*(.*)$")
# Counted in any markup (- Disclosure:, **Disclosure:**, 1. Disclosure:, > Disclosure:).
_DISCLOSURE_LABEL = re.compile(r"(?i)\bdisclosure\b[*_`\s]*:")
_DISCLOSURE_STATE = re.compile(r"(?i)^(none found|embargoed|cleared \d{4}-\d{2}-\d{2})\b")
_EVIDENCE = re.compile(r"`[^`]+`|\[[^\]]+\]\([^)]+\)")
_TICKED = re.compile(r"`([^`]+)`")
_LINK = re.compile(r"\[[^\]]*\]\((?:<([^>]+)>|([^)\s]+))(?:\s+(?:\"[^\"]*\"|'[^']*'|\([^)]*\)))?\)")
_REFDEF = re.compile(r"(?m)^[ \t]*\[[^\]]+\]:[ \t]*(?:<([^>]+)>|(\S+))")
_FILE_EXT = re.compile(
    r"\.(?:png|jpe?g|gif|webp|heic|txt|log|json|jsonl|md|csv|tsv|html?|xml|ya?ml|pdf|"
    r"mp4|mov|mkv|webm|mp3|wav|m4a|ogg|flac|zip|tar|gz|out|err|sh|py|js|ts)$", re.I)


def _evidence_path(tok: str) -> str | None:
    """The file path a cited token points at, or None when it is not a path.

    A path ends in a known file extension (after an optional `:line` suffix), and has no
    glob or shell characters. A token with spaces counts only when its first word already
    contains a `/` (`evidence/run 2.png`), so commands such as `screencapture -x out.png`
    or `sample 4242 1 > evidence/run.txt` are not mistaken for paths. Media types
    (`text/html`), `n/a` and bare domains have no file extension and are skipped."""
    tok = tok.strip()
    if "://" in tok or re.search(r"[*?\[\]<>|&;$]", tok):
        return None
    tok = re.sub(r":\d+(?::\d+)?$", "", tok)
    if not _FILE_EXT.search(tok):
        return None
    if re.search(r"\s", tok):
        first = tok.split()[0]
        if "/" not in first or any(w.startswith("-") for w in tok.split()):
            return None
    return tok


def _items(body: str) -> list[str]:
    """Numbered list items, with wrapped continuation lines joined to their item."""
    items: list[str] = []
    for ln in body.splitlines():
        if re.match(r"^\s*\d+\.\s", ln):
            items.append(ln.strip())
        elif items and ln.strip() and not ln.lstrip().startswith(("#", "-", "*", "|")):
            items[-1] += " " + ln.strip()
    return items


def skill_root(path: Path) -> Path | None:
    """The nearest ancestor of `path` that holds a SKILL.md, if any."""
    for d in path.resolve().parents:
        if (d / "SKILL.md").exists():
            return d
    return None


def _outside(path: str) -> bool:
    """An absolute, home (~/) or .. path: it points outside any tree that ships."""
    return path.startswith(("/", "~/")) or path == "~" or ".." in Path(path).parts


def _citation_problems(ver: str, bases: list[Path], root: Path | None) -> list[str]:
    """Evidence cited in ## Verification must exist. With a root, every cited path must also
    stay inside it: an absolute, ~ or .. path fails whatever its extension and whether or
    not it has spaces, because it points at something that does not ship."""
    problems: list[str] = []
    top = root.resolve() if root is not None else None
    links = [a or b for a, b in _LINK.findall(ver) + _REFDEF.findall(ver)]
    if re.search(r"(?i)file://", ver) and root is not None:
        problems.append("## Verification cites a file:// URL: a local file that does not ship")
    for tok in dict.fromkeys(t.strip() for t in _TICKED.findall(ver) + links):
        if tok.lower().startswith("file://"):
            tok = tok[7:]  # a local file, whatever the scheme says
        rooted = _outside(tok) or tok.startswith("./")  # a path even with spaces, any extension
        path = _evidence_path(tok) or (tok if rooted or ("/" in tok and " " not in tok and "://" not in tok)
                                       else None)
        if path is None:
            continue  # a command, a URL or prose
        if top is not None and _outside(path):
            problems.append(f"## Verification cites a path outside the ship tree (absolute, ~ or ..): {tok}")
            continue
        if _evidence_path(tok) is None:
            continue  # path-shaped, inside the root, but not a file the lint can check
        p = Path(path).expanduser()
        hits = [p] if p.is_absolute() else [(b / p) for b in bases if (b / p).exists()]
        if not (hits and hits[0].exists()):
            problems.append(f"## Verification cites a path that does not exist: {tok}")
        elif top is not None and not any(h.resolve().is_relative_to(top) for h in hits):
            problems.append(f"## Verification cites a path outside {top.name}/, which does not ship: {tok}")
    return problems


def _disclosure_problems(env: str) -> list[str]:
    """The state line: none found | embargoed (fails) | cleared YYYY-MM-DD (a real date, not in
    the future). Unconditional: one Disclosure label in any markup, and no YYYY-MM-DD in the
    Envelope after today. The note-wide "embargoed" check is in lint_note."""
    lines = _DISCLOSURE.findall(env)
    if not lines or not lines[0].strip():
        return ["## Envelope has no 'Disclosure:' line (none found | embargoed ... | cleared YYYY-MM-DD ...)"]
    if len(_DISCLOSURE_LABEL.findall(env)) > 1:
        return ["## Envelope has more than one 'Disclosure:' line; keep one (one finding per note)"]
    today = _dt.date.today().isoformat()
    later = [d for d in re.findall(r"\d{4}-\d{2}-\d{2}", env) if d > today]
    if later:
        return [f"## Envelope names a date that has not arrived ({later[0]}): an agreed date in the "
                "future is still an embargo"]
    value = lines[0].strip()
    if TODO in value:
        return []  # already reported as an unfilled placeholder
    m = _DISCLOSURE_STATE.match(value)
    if not m:
        return [f"Disclosure must start with 'none found', 'embargoed' or 'cleared YYYY-MM-DD': {value[:60]}"]
    state = m.group(1).lower()
    if state.startswith("cleared"):
        try:
            _dt.date.fromisoformat(state.split()[1])
        except ValueError:
            return [f"Disclosure 'cleared' needs a real date: {value[:60]}"]
        return []
    if state == "embargoed" or re.search(r"(?i)\bembargo", value):
        return ["Disclosure is embargoed: nothing describing the flaw ships until the agreed disclosure "
                "date has passed (or the vendor shipped a fix) and the owner signed off; then write "
                "'cleared YYYY-MM-DD ...' (references/envelope.md)"]
    return []


def lint_note(text: str, base: Path | list[Path] | None = None, root: Path | None = None) -> list[str]:
    """Problems that make a field note unusable to the next agent, or unfit to ship. Empty =
    clean.

    With `base` (the note's folder, or a list of folders), every evidence path cited in
    ## Verification must exist under at least one of them; with `root`, it must also stay
    inside `root` (_citation_problems). The Envelope needs one Disclosure line
    (_disclosure_problems). The CLI passes the note's folder and the root, and always sets
    the root."""
    problems: list[str] = []
    headings = [h.strip() for h in _HEADING.findall(text)]
    sections: dict[str, str] = {}
    parts = _HEADING.split(text)
    for i in range(1, len(parts) - 1, 2):
        sections[parts[i].strip()] = parts[i + 1]
    for name in NOTE_SECTIONS:
        if name not in headings:
            problems.append(f"missing section: ## {name}")
        elif headings.count(name) > 1:
            problems.append(f"duplicate section: ## {name} (merge them; the lint cannot tell which one counts)")
    if TODO in text:
        problems.append(f"unfilled placeholders remain ({text.count(TODO)} x {TODO})")
    ver = sections.get("Verification", "")
    if "Verification" in sections and not _EVIDENCE.search(ver):
        problems.append("## Verification cites no evidence (a `path` or a [link](url))")
    if base is not None and "Verification" in sections:
        problems += _citation_problems(ver, base if isinstance(base, list) else [base], root)
    got = sections.get("Gotchas", "")
    if "Gotchas" in sections:
        items = _items(got)
        if not items and not re.match(r"(?i)\s*none hit\b", got.strip()):
            problems.append("## Gotchas has no numbered items (write 'None hit on this run.' if nothing failed)")
        for it in items:
            if not _GOTCHA.match(it):
                problems.append(f"gotcha is not 'symptom → cause → fix': {it[:70]}")
    if "Envelope" in sections:
        problems += _disclosure_problems(sections["Envelope"])
    # Markdown has many ways to nest a second finding under a cleared one; the word is the
    # check. A note that says "embargoed" anywhere does not ship.
    if re.search(r"(?i)\bembargoed\b", text) and not any("embargoed" in p for p in problems):
        problems.append("the note says 'embargoed': nothing describing an embargoed finding ships "
                        "(one finding per note; write 'cleared YYYY-MM-DD' once disclosure clears)")
    route = sections.get("Route", "")
    if "Route" in sections and not re.search(r"(?i)\brung\s*(?:[1-5]\b|passthrough)|passthrough", route):
        problems.append("## Route does not name a rung (1-5 or passthrough)")
    return problems


def _dispatch(ns: argparse.Namespace, d: Path) -> int:
    if ns.cmd == "init":
        cmd_init(d, ns.target, ns.idea, ns.done, ns.in_repo)
        print(f"journal started: {d / JOURNAL}")
    elif ns.cmd == "log":
        cmd_log(d, ns.text, ns.evidence)
        print("noted")
    elif ns.cmd == "route":
        e = cmd_route(d, ns.rung, ns.name, ns.reason, ns.subgoal, ns.supersedes)
        print(f"route #{e['n']}: rung {e['rung']} ({RUNGS[e['rung']]}) — {e['name']}")
    elif ns.cmd == "ok":
        e = cmd_ok(d, ns.step, ns.evidence)
        print(f"ok: {e['step']}")
    elif ns.cmd == "fail":
        e, stalled = cmd_fail(d, ns.sig, ns.detail, ns.limit)
        if stalled:
            r = load(d)["routes"][-1]
            print(STALL_TEXT.format(sig=e["sig"], count=e["count"], route=r["n"],
                                    rung=r["rung"], name=r["name"]))
            return 3
        print(f"fail x{e['count']} (stall at {e['limit']}): {e['sig']}")
    elif ns.cmd == "status":
        print(cmd_status(d))
    elif ns.cmd == "note":
        out = cmd_note(d, Path(ns.out), ns.force)
        print(f"field note scaffolded: {out} — fill every {TODO}, then run lint-note")
    elif ns.cmd == "lint-note":
        path = Path(ns.path)
        if not path.is_file():
            raise Refused(f"no such file: {path}")
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as e:
            raise Refused(f"cannot read {path} as UTF-8 text: {e}")
        root = Path(ns.root) if ns.root else (skill_root(path) or path.parent)
        if not root.is_dir():
            raise Refused(f"--root is not a folder: {root}")
        problems = lint_note(text, base=[path.parent, root], root=root)
        for pr in problems:
            print(f"FAIL {pr}")
        if problems:
            return 1
        print(f"OK {path}: complete field note")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="modlog.py", description=__doc__.split("\n")[0])
    ap.add_argument("--dir", default=".", help="working folder holding MODLOG.md (default: .)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init"); p.add_argument("--target", required=True)
    p.add_argument("--idea", required=True); p.add_argument("--done")
    p.add_argument("--in-repo", action="store_true", help="allow a working folder inside a git repo")
    p = sub.add_parser("log"); p.add_argument("--text", required=True)
    p.add_argument("--evidence", nargs="+", default=[])
    p = sub.add_parser("route"); p.add_argument("--rung", required=True)
    p.add_argument("--name", required=True); p.add_argument("--reason", required=True)
    p.add_argument("--subgoal"); p.add_argument("--supersedes", type=int)
    p = sub.add_parser("ok"); p.add_argument("--step", required=True)
    p.add_argument("--evidence", nargs="+", default=[])
    p = sub.add_parser("fail"); p.add_argument("--sig", required=True)
    p.add_argument("--detail"); p.add_argument("--limit", type=int, default=None)
    sub.add_parser("status")
    p = sub.add_parser("note"); p.add_argument("--out", required=True)
    p.add_argument("--force", action="store_true")
    p = sub.add_parser("lint-note"); p.add_argument("path")
    p.add_argument("--root", help="folder that skill-relative citations resolve from (the tree you will ship)")
    ns = ap.parse_args(argv)
    d = Path(ns.dir)
    try:
        with locked(d):
            return _dispatch(ns, d)
    except Refused as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    except OSError as e:  # an unwritable folder, a full disk: not a lint finding
        print(f"cannot read or write {e.filename or d}: {e.strerror or e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

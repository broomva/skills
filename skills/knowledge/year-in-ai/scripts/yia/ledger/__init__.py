"""The harvest ledger: a text-free, append-only record of every AI turn.

Local transcript stores decay. Claude Code prunes sessions after about 30
days, and a harness migration can drop a whole window, so a retrospective
computed in December from the stores alone cannot cover the year. The ledger
is collected while the year happens instead. A harvest runs periodically,
reads every store it can find, and folds each turn into one row.

A row holds counts, hashes and attribution flags. **It never holds message
text**, so the ledger is safe to keep for years and to back up anywhere. The
hashes let the fold merge the same prompt seen in two stores, and let it spot
scripted prompts that repeat across sessions, without storing what was said.

This module is Python 3.9 compatible on purpose. A launchd job on macOS runs
the system ``/usr/bin/python3``, because Homebrew's Python hangs on privacy
prompts there.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, Iterable, Optional

SCHEMA = "year-in-ai/ledger/v7"
#: Row version written and read by this code. Rows of other versions are ignored.
ROW_VERSION = 7

#: A prompt is what started a turn; a reply is the final assistant message of it.
KINDS = ("prompt", "reply")

#: Who wrote a prompt, as far as the store itself can tell.
#: ``unknown`` means the store records no author; the fold decides.
AUTHORS = ("human", "agent", "unknown")

_WS = re.compile(r"\s+")
_PASTE = re.compile(r"<pasted_content[^>]*>.*?</pasted_content>", re.S)
_FENCE = re.compile(r"```.*?```", re.S)
_PASTE_PLACEHOLDER = re.compile(r"\[Pasted text[^\]]*\]")

#: Text a harness injects into the user role. These are not prompts at all.
HARNESS_INJECTED = (
    "<local-command", "<system-reminder", "<task-notification", "Base directory for this skill",
    "This session is being continued", "Caveat:", "[Request interrupted", "<bash-",
    "<user-prompt-submit", "Set model to", "<<autonomous", "<teammate-message",
    "Stop hook feedback", "<tool_use_error", "API Error", "Unknown skill", "Login successful",
    "<channel source=",
)

#: Openings that mark a prompt as written by a program, not a person.
#: Matched case-insensitively at the very start of the prompt. These are
#: anchored because a person also writes "you are right" mid-sentence.
AUTOMATION_OPENINGS = (
    "[fleet coordinator", "[coordinator", "[sri coordinator", "respond in one", "follow the heartbeat",
    "previous ai response", "[image: ", "**workflow authoring", "you are the ", "you are an ",
    "you are a ", "you are fleet", "# ", "## ", "authentication successful", "resume. a paseo",
    "run the shell command", "act as the ", "delegated task ",
)

#: Phrases that mark a prompt as scripted wherever they appear in its first 200 characters.
AUTOMATION_PHRASES = (
    "execute it to completion", "run_n=", "from the sri coordinator",
)

_COMMAND = re.compile(
    r"<command-name>(?P<name>[^<]*)</command-name>(?:.*?<command-args>(?P<args>.*?)</command-args>)?",
    re.S,
)


def normalize(text: str) -> str:
    return _WS.sub(" ", text.strip().lower())


def text_hash(text: str) -> str:
    """Hash of the whole normalized text, used to merge one prompt seen in two stores.

    The whole text, not a prefix: two long prompts built from one template
    differ only after the template, and must not merge.
    """
    return hashlib.sha1(normalize(text).encode("utf-8")).hexdigest()[:16]


def opaque(value: Optional[str]) -> Optional[str]:
    """A stable, non-reversible handle for an external identifier (session ids, paths)."""
    if value is None:
        return None
    return hashlib.sha1(str(value).encode("utf-8")).hexdigest()[:16]


#: The only values an attribution field may hold. Anything else is stored as
#: ``other``: a store that put free text in one of these fields must not be
#: able to carry it into the ledger.
ATTR_VALUES = {
    "created_by": {"user", "agent", "system"},
    "creation_source": {"web", "mobile", "server", "desktop", "cli", "api"},
    "lineage": {"top", "subagent", "fork"},
    "entrypoint": {"cli", "sdk-cli", "sdk-ts", "sdk-py", "claude-desktop", "claude-vscode", "mcp"},
    "originator": {"Codex Desktop", "codex_exec", "codex_cli_rs", "codex-tui", "T3 Code", "t3code_desktop",
                   "superconductor", "acpx", "codex_sdk_ts", "codex_work_desktop"},
    "source": {"vscode", "cli", "exec"},
    "provider": {"claudeAgent", "codex", "codex_team", "codex_carlos", "codex_carlos_personal_20261029",
                 "gemini-vertex", "antigravity", "antigravity-personal", "antigravity-balanced", "grok",
                 "holon", "cursor", "opencode", "pi"},
}


def ext_str(value: Any) -> Optional[str]:
    """The one boundary for external scalar fields: a string, or ``None``.

    Store metadata is untrusted. A field that should be a string but holds a
    dict, list or number is treated as unknown here, before any reader compares
    it with a set or puts it in a label.
    """
    if isinstance(value, str):
        return value
    if value is None:
        return None
    return "other"


def occurrence_key(*parts: Any) -> str:
    """A reader's identity for one recorded occurrence, from its parts.

    Readers pass either the store's own message id, or, when the store has
    none, ``(session, timestamp, text hash, n)`` where ``n`` counts earlier
    occurrences with the same session, timestamp and text. Content-anchored
    keys stay stable when other records are inserted or a prefix is pruned.
    """
    return "|".join("" if p is None else str(p) for p in parts)


def clean_attr(attr: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """Keep known keys with known values; map unknown values to ``other``; drop unknown keys."""
    out: Dict[str, str] = {}
    for key, value in (attr or {}).items():
        value = ext_str(value)
        if key not in ATTR_VALUES or value is None:
            continue
        out[key] = value if value in ATTR_VALUES[key] else "other"
    return out


def harness_label(prefix: str, value: Optional[str], key: str) -> str:
    """``prefix:value`` when the value is a known enum, ``prefix:other`` when not, ``prefix`` when absent."""
    value = ext_str(value)
    if not value:
        return prefix
    return f"{prefix}:{value if value in ATTR_VALUES[key] else 'other'}"


def prefix_hash(text: str) -> Optional[str]:
    """Hash of the first 45 normalized characters, used to spot scripted prompts.

    A dispatcher that varies only a run number (``RUN_N=154``) defeats an
    exact-text check, but its prompts share an opening.
    """
    norm = normalize(text)
    if len(norm) < 40:
        return None
    return hashlib.sha1(norm[:45].encode("utf-8")).hexdigest()[:16]


#: A single prompt longer than this is a paste, not writing, whatever its markup.
AUTHORED_CAP = 4000


def authored_text(text: str) -> str:
    """What the person wrote: pasted blocks, paste placeholders and code fences removed, capped."""
    stripped = _FENCE.sub("", _PASTE.sub("", _PASTE_PLACEHOLDER.sub("", text))).strip()
    return stripped[:AUTHORED_CAP]


def authored_chars(text: str) -> int:
    return len(authored_text(text))


def unwrap_command(text: str) -> Optional[str]:
    """Turn a harness slash-command wrapper back into what was typed.

    ``<command-name>/autonomous</command-name> ... <command-args>build X</command-args>``
    becomes ``/autonomous build X``. A bare command with no arguments returns
    ``None``: ``/clear`` or ``/mcp`` is a keystroke, not writing.
    """
    if "<command-name>" not in text:
        return text
    match = _COMMAND.search(text)
    if not match:
        return None
    args = (match.group("args") or "").strip()
    if not args:
        return None
    return f"{match.group('name').strip()} {args}"


def is_injected(text: str) -> bool:
    return text.lstrip().startswith(HARNESS_INJECTED)


def has_automation_marker(text: str) -> bool:
    head = text.strip().lower()[:200]
    return head.startswith(AUTOMATION_OPENINGS) or any(p in head for p in AUTOMATION_PHRASES)


class exclusive_lock:
    """An exclusive ``flock`` on ``<directory>/<name>`` for the duration of a ``with`` block.

    Serializes overlapping harvests: two ledger writers would otherwise read
    the same highest sequence, and two archive runs could replace a version
    between another run's classification and its rename.
    """

    def __init__(self, directory, name: str):
        import os as _os
        self.path = _os.path.join(str(directory), name)
        self.handle = None

    def __enter__(self):
        import fcntl
        self.handle = open(self.path, "a")
        fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        import fcntl
        fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        self.handle.close()
        return False


def make_row(
    *,
    src: str,
    harness: str,
    kind: str,
    ts: float,
    text: str,
    session: Optional[str],
    author: str = "unknown",
    turn: Optional[str] = None,
    occurrence: str,
    attr: Optional[Dict[str, Any]] = None,
    authored: Optional[str] = None,
    key: Optional[str] = None,
) -> Dict[str, Any]:
    """Build one ledger row from a turn. The text goes in; only numbers and hashes come out.

    ``session`` and ``turn`` are external or derived identifiers; the session is
    stored as an opaque hash, and ``turn`` is always a row id made here.
    ``harness`` must come from :func:`harness_label` or a fixed literal.
    ``occurrence`` is the reader's identity for this recorded occurrence (see
    :func:`occurrence_key`); the row id is derived from the store and it alone,
    never from content, so two occurrences never share an id and the same
    occurrence harvested twice always does. ``key`` is the store's native
    message id when it has one, kept (hashed) as evidence for copy detection.
    """
    if kind not in KINDS:
        raise ValueError(f"unknown row kind: {kind!r}")
    if author not in AUTHORS:
        raise ValueError(f"unknown author: {author!r}")
    clean = text.strip()
    h = text_hash(clean)
    # ``authored`` is the part of the text the person wrote, when the store keeps
    # it apart (a prompt history stores pastes separately); else it is derived.
    own = authored_text(clean if authored is None else authored)
    words = len(clean.split())
    flags = []
    if kind == "prompt" and has_automation_marker(clean):
        flags.append("marker")
    sess = opaque(session)
    row_id = row_identity(src, kind, occurrence, h)
    return {
        "id": row_id,
        "v": ROW_VERSION,
        "ts": round(ts, 3),
        "src": src,
        "harness": harness,
        "kind": kind,
        "author": author,
        "chars": len(clean),
        "words": words,
        "authored_chars": len(own),
        "authored_words": len(own.split()),
        "h": h,
        "ph": prefix_hash(clean) if kind == "prompt" else None,
        "sess": sess,
        "turn": turn,
        "k": opaque(key),
        "o": opaque(f"{src}|{kind}|{occurrence}"),
        # Harvest order, set by the ledger when the row is written.
        "seq": None,
        "flags": flags,
        "attr": clean_attr(attr),
    }


def row_identity(src: str, kind: str, occurrence: str, revision: str) -> str:
    """Where a row id is made (with :func:`revision_identity`). A test asserts nothing else computes one.

    A row is one *revision* of one occurrence: the occurrence identity plus the
    hash of its text. Harvesting an unchanged message again gives the same id;
    a message edited in place since the last harvest gives a new row for the
    same occurrence (``o``), and the fold keeps the latest revision.
    """
    if not occurrence:
        raise ValueError("a row needs an occurrence identity")
    return hashlib.sha1(f"{src}|{kind}|{occurrence}|{revision}".encode("utf-8")).hexdigest()[:20]


def revision_identity(occurrence_hash: str, revision: str, n: int) -> str:
    """The id of the n-th stored revision of one occurrence (n = 0 is :func:`row_identity`'s row).

    Used by the ledger when an occurrence returns to text it had before
    (A, B, A): the third revision is a new row, ordered by harvest sequence.
    """
    return hashlib.sha1(f"{occurrence_hash}|{revision}|{n}".encode("utf-8")).hexdigest()[:20]


def row_fields() -> Iterable[str]:
    """The complete set of row keys. Tests assert rows carry nothing else."""
    return (
        "id", "v", "ts", "src", "harness", "kind", "author", "chars", "words",
        "authored_chars", "authored_words", "h", "ph", "sess", "turn", "k", "o", "seq", "flags", "attr",
    )

#!/usr/bin/env python3
"""publish_check — a fail-closed filter in front of a person, before a mod is shared.

Run it before anything leaves the machine: a commit to a public repo, a pull request to a shared
knowledge base, a release, a post. It decides what it can decide and hands the rest to a person.

A mod ships source, docs, small data files and screenshots, so only those types may ship
(SHIP_TEXT_EXT, SHIP_TEXT_NAMES and the image types below). Everything else is blocked
until a person looks at it and passes --allow.

BLOCK (exit 1), file by file:
  type      a file type that is not on the ship allowlist (a PDF, a font, an archive, a
            database, audio or video, a file with no extension and no known name)
  binary    third-party program or asset formats, by extension (.asar, .dylib, .framework,
            .node, .jar, ROM and disc images, game archives, app bundles) or by executable
            header (Mach-O, ELF, PE). Ship code, patches and converters, never the target's bytes
  opaque    an allowlisted type whose bytes are not what the type claims: a .txt or .js that
            is not valid UTF-8 (or UTF-16 with a byte-order mark) or holds NUL bytes, an
            image extension on a file that is not that image, and .DS_Store-style junk
  capture   network and device captures by extension (.har, .pcap, .pcapng, .pklg, .btsnoop)
  folder    dependency, cache and VCS folders (.git, node_modules, venv, __pycache__, ...):
            a mod does not ship them, they are not scanned, and --allow cannot clear them.
            Remove them from the tree. Build output (dist/, build/) is scanned like any folder
  symlink   every symbolic link (git commits the target path; archivers follow it)
  large     any file over --max-mb (default 5)
  secret    a well-known credentials file name (.yarnrc.yml, pgpass.conf, credentials.json,
            ...), anything found by gitleaks (`gitleaks dir`, run with its default rules: an
            in-tree config, ignore file or gitleaks:allow comment cannot switch them off) when
            it is installed, and a short built-in list of token shapes (private keys, AWS, GitHub classic and
            fine-grained, Slack, OpenAI-style keys, bearer tokens, JWTs). gitleaks skips binary
            files, so those get the built-in list only. Without gitleaks only the built-in list
            runs, and a REVIEW line says so
  decomp    headers that decompilers write into their output
  userpath  home-directory paths (/Users, /home, /root, C:\\Users in any case, macOS
            per-user temp folders under /var/folders), and ~/... paths that contain this
            machine's login name
  address   a device hardware address (MAC or Bluetooth, aa:bb:cc:dd:ee:ff, with at least
            one hex letter so dates and times do not match); the RFC 7042 documentation range
            00:00:5E:00:53:xx and all-zero or broadcast are allowed
  username  this machine's login name (generic container logins are ignored)
  hostname  this machine's hostname, or a Mac-style one (<name>-MacBook-Pro.local)
  denied    any term from --deny-file (one per line; put a backslash before a term that
            starts with #, which otherwise marks a comment). Case and line wrapping are
            ignored: "Ada Lovelace" also matches "ada\\n  lovelace"

Names are checked like contents: git publishes file and folder names too. Non-text files are
also read for printable text (Latin-1, and UTF-16 at either byte alignment), so a path in an
image's metadata is found. Text is matched as written: nothing is decoded.

--allow GLOB clears only the "is this file shippable at all" findings (type, binary, opaque,
capture, large, symlink) for matching paths and their contents. Content and name findings
still apply, and every allowed path is listed for review. Globs match the path relative to
each scanned folder.

A gitleaks config or ignore file inside the tree is a BLOCK too (kind "gitleaks"): gitleaks
reads <source>/.gitleaksignore whatever flags say, so it would silence a plain gitleaks run.

REVIEW (exit unaffected): images and SVGs (a file whose extension claims an image its bytes
are not is opaque instead), HTML, notebooks, plists and source maps (they often embed encoded
content), every file under an `evidence/` or `fixtures/` folder and every modlog
journal (MODLOG.md, .modlog.json): captured output, recordings and journals can carry
someone's data, device addresses or keys. Also allowed paths, special files (FIFOs, sockets),
and the secrets engine when gitleaks is not installed or was skipped with --no-gitleaks.
gitleaks installed but failing exits 2.

NOT detected, by design: cookies and session values, personal data such as emails and display
names (unless they are in --deny-file), serial numbers, anything encoded (URL-encoding, \\u or
\\/ escapes, base64, compression, encryption), the target's own code copied in as text (an
Electron app's JS, bundled into dist/), and code transcribed from a decompiler without its
header. Logins shorter than 4 characters and hostnames shorter than 6 are not matched. Keep them out at the source
(never copy a browser profile; captures are blocked), put names you know in --deny-file, and
read every REVIEW line. Exit 0 means "nothing this filter recognises", not "nothing private".

Usage:  publish_check.py <path> [<path> ...] [--allow GLOB ...] [--deny-file F] [--max-mb N]
                         [--no-gitleaks] [--json]
        Each path is a folder or a single file (for example the field note, before it is
        copied anywhere public).
Exit 0 clean · 1 findings · 2 usage error or a file it could not read. Stdlib, plus gitleaks
on PATH when available.
"""
from __future__ import annotations

import argparse
import codecs
import fnmatch
import getpass
import json
import os
import re
import shutil
import socket
import stat
import subprocess
import sys
from pathlib import Path

BINARY_EXT = {
    ".asar", ".dylib", ".so", ".dll", ".exe", ".msi", ".dmg", ".pkg", ".app", ".framework",
    ".bundle", ".plugin", ".node", ".jar", ".class", ".ipa", ".apk", ".xapk", ".aab",
    ".iso", ".cso", ".chd", ".xex", ".xbe", ".nsp", ".xci", ".wbfs", ".rvz",
    ".z64", ".n64", ".v64", ".sfc", ".smc", ".nes", ".gba", ".gbc", ".gb", ".nds", ".3ds",
    ".pak", ".wad", ".bsa", ".ba2", ".esm", ".vpk", ".uasset", ".ucas", ".utoc",
    ".rpf", ".fastfile", ".ff", ".bin", ".img", ".fw",
}
# Executable headers: Mach-O (32/64, both byte orders), fat/universal Mach-O, ELF. PE is
# checked by _is_pe, because "MZ" alone also starts ordinary text.
MAGIC = (
    (b"\xfe\xed\xfa\xce", "Mach-O"), (b"\xfe\xed\xfa\xcf", "Mach-O"),
    (b"\xce\xfa\xed\xfe", "Mach-O"), (b"\xcf\xfa\xed\xfe", "Mach-O"),
    (b"\xca\xfe\xba\xbe", "universal Mach-O or Java class"), (b"\x7fELF", "ELF"),
)


def _is_pe(head: bytes) -> bool:
    """An 'MZ' prefix alone is ordinary text ("MZ-1 drum machine"); a PE file also has
    'PE\\0\\0' at the offset stored at 0x3C."""
    if not head.startswith(b"MZ") or len(head) < 0x40:
        return False
    off = int.from_bytes(head[0x3C:0x40], "little")
    return 0 < off < len(head) - 4 and head[off:off + 4] == b"PE\x00\x00"


CAPTURE_EXT = {".har", ".pcap", ".pcapng", ".cap", ".pklg", ".btsnoop", ".saz", ".etl", ".snoop"}
# Dependency, build and VCS folders: never part of a mod, and not scanned (BLOCK "folder").
# Build output (dist/, build/) is the mod's own code, so it is scanned like anything else.
SKIP_DIRS = {".git", ".hg", ".svn", "node_modules", "bower_components", "__pycache__", ".venv",
             "venv", ".tox", ".nox", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".gradle",
             ".parcel-cache", ".turbo", ".eggs"}
# The ship allowlist: what a mod is made of. Text types are read and must decode as text.
SHIP_TEXT_EXT = {
    # docs and data
    ".md", ".markdown", ".txt", ".rst", ".adoc", ".log", ".json", ".jsonl", ".jsonc", ".json5",
    ".csv", ".tsv", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".properties", ".xml",
    ".plist", ".svg", ".html", ".htm", ".sql", ".graphql", ".gql", ".ipynb", ".lock", ".map",
    # code, patches and scripts
    ".py", ".pyi", ".js", ".mjs", ".cjs", ".ts", ".mts", ".cts", ".tsx", ".jsx", ".vue",
    ".svelte", ".css", ".scss", ".sass", ".less", ".sh", ".bash", ".zsh", ".fish", ".ps1",
    ".bat", ".cmd", ".lua", ".rs", ".go", ".swift", ".m", ".mm", ".h", ".hpp", ".hh", ".c",
    ".cc", ".cpp", ".cxx", ".cs", ".java", ".kt", ".kts", ".gradle", ".rb", ".pl", ".php",
    ".r", ".jl", ".scala", ".dart", ".zig", ".nim", ".ex", ".exs", ".erl", ".hs", ".ml",
    ".el", ".vim", ".nix", ".applescript", ".ahk", ".au3", ".glsl", ".hlsl", ".wgsl", ".frag",
    ".vert", ".shader", ".cmake", ".mk", ".patch", ".diff", ".tf", ".proto", ".fbs", ".ld",
    # config a rung-1 mod is made of
    ".gitconfig", ".rc", ".desktop", ".service", ".reg", ".theme", ".keylayout",
    ".itermcolors", ".terminal", ".code-workspace", ".code-snippets", ".sublime-settings",
    ".sublime-keymap", ".lesskey", ".inputrc",
}
SHIP_TEXT_NAMES = re.compile(
    r"(?i)^(?:licen[cs]e|notice|readme|changelog|changes|authors|contributors|copying|"
    r"makefile|justfile|dockerfile|containerfile|procfile|gemfile|rakefile|brewfile|"
    r"\.gitignore|\.gitattributes|\.editorconfig|\.npmignore|\.nvmrc|\.node-version|"
    r"\.python-version|\.tool-versions|\.(?:bash|zsh|vim|input|screen|eslint|babel|prettier|stylelint|swc|editor)rc|\.(?:bash_|z)?profile|"
    r"\.gitconfig)(?:[-.][\w.-]*)?$")
# Not on the list on purpose, so they BLOCK as "type": .env, .netrc, .npmrc, .pypirc, .envrc,
# .yarnrc, .git-credentials, .pgpass. They exist to hold credentials.
JOURNAL_NAMES = {"MODLOG.md", ".modlog.json"}
# Well-known credential files whose extension is otherwise shippable (.yml, .conf, .json).
CREDENTIAL_NAMES = {".yarnrc.yml", "pgpass.conf", "_netrc", "credentials", "credentials.json",
                    ".dockercfg", "service-account.json", "client_secret.json"}

SECRET_PATTERNS = [
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("AWS access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("GitHub fine-grained token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("OpenAI/Anthropic-style key", re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{20,}\b")),
    ("bearer token", re.compile(r"(?i)\bauthorization\b[\"']?\s*[:=]\s*[\"']?bearer\s+[A-Za-z0-9._~+/-]{12,}")),
    ("bearer token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{20,}")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")),
]
# Findings an --allow can clear: they say "this file should not ship", not "this text leaks".
ALLOWABLE = {"type", "binary", "opaque", "capture", "large", "symlink"}
JUNK_NAMES = {".DS_Store": "Finder metadata; delete it", "Thumbs.db": "Windows thumbnail cache; delete it",
              "desktop.ini": "Windows folder settings; delete it"}
DECOMP_MARKERS = [
    re.compile(r"(?i)decompiled (?:with|by)\b"),
    re.compile(r"\bILSpy\b"),
    re.compile(r"(?i)\bjadx\b"),
    re.compile(r"(?i)generated by ghidra"),
    re.compile(r"(?i)\bhex-rays\b"),
    re.compile(r"(?i)\bJD-GUI\b"),
    re.compile(r"(?i)\bdnSpy\b"),
]
USERPATH = re.compile(r"(?:/Users/|/home/)(?!Shared\b)[A-Za-z0-9][A-Za-z0-9._-]*(?:/|\b)"
                      r"|[A-Za-z]:\\\\?(?i:users)\\\\?[A-Za-z0-9._-]+"
                      r"|(?<![\w.-])/root/|/var/folders/[A-Za-z0-9_+-]{2}/[A-Za-z0-9_+-]{8,}")
# A hardware address in either separator style. RFC 7042's documentation range and the
# all-zero and broadcast addresses are fine in fixtures.
DEVICE_ADDR = re.compile(r"(?<![0-9A-Za-z])(?:[0-9A-Fa-f]{2}([:-]))(?:[0-9A-Fa-f]{2}\1){4}[0-9A-Fa-f]{2}(?![0-9A-Za-z])")
DOC_ADDR = re.compile(r"(?i)^00[:-]00[:-]5e[:-]00[:-]53[:-][0-9a-f]{2}$|^(?:00[:-]){5}00$|^(?:ff[:-]){5}ff$")
MAC_HOST = re.compile(r"\b[A-Za-z0-9][A-Za-z0-9-]*-(?:MacBook(?:-Pro|-Air)?|iMac(?:-Pro)?|Mac-mini|Mac-Pro|Mac-Studio)(?:-\d+)?(?:\.local)?\b")
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic", ".tiff", ".bmp"}
# Shown to a person as images. SVG is scanned as text, but can embed a screenshot.
REVIEW_IMAGE_EXT = IMAGE_EXT | {".svg"}
# Text types that commonly embed encoded content (base64 images, inline source maps, plist
# <data>, URL-encoded strings) that this scan does not decode: listed for a person.
ENCODED_EXT = {".html", ".htm", ".ipynb", ".plist", ".map"}
# An image extension must be backed by the image's own header; anything else is opaque.
IMAGE_MAGIC = {".png": (b"\x89PNG",), ".jpg": (b"\xff\xd8\xff",), ".jpeg": (b"\xff\xd8\xff",),
               ".gif": (b"GIF87a", b"GIF89a"), ".bmp": (b"BM",), ".tiff": (b"II*\x00", b"MM\x00*")}


def _is_real_image(ext: str, head: bytes) -> bool:
    """The file's own header backs its image extension."""
    if ext == ".webp":
        return head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    if ext == ".heic":
        return head[4:8] == b"ftyp" and head[8:12] in (b"heic", b"heix", b"mif1", b"msf1", b"hevc")
    return head.startswith(IMAGE_MAGIC.get(ext, (b"\x00\x00impossible",)))
GITLEAKS_CONFIGS = {".gitleaks.toml", ".gitleaksignore", "gitleaks.toml"}
CHUNK = 4 * 1024 * 1024
OVERLAP = 256  # longest pattern we look for, so a match split across chunks is still seen


class Unreadable(Exception):
    """A file that could not be read: the scan cannot vouch for it (exit 2)."""


def local_hostnames() -> set[str]:
    """This machine's names, lowercased, without the .local suffix. Short or generic
    names are dropped: matching 'mac' or 'localhost' would flag ordinary prose."""
    names = {socket.gethostname()}
    try:
        names.add(socket.getfqdn())
    except OSError:
        pass
    out = set()
    for n in names:
        n = n.lower().removesuffix(".local").split(".")[0]
        if len(n) >= 6 and n not in {"localhost", "ip6-localhost"}:
            out.add(n)
    return out


# Logins that are also ordinary words or container defaults; matching them would flag prose.
GENERIC_LOGINS = {"root", "runner", "user", "admin", "node", "vscode", "code", "test", "build",
                  "ubuntu", "debian", "ec2-user", "docker", "app", "dev", "guest", "nobody"}


def local_username() -> str | None:
    try:
        u = getpass.getuser()
    except Exception:  # noqa: BLE001 — no login name is a normal state in containers
        return None
    return u if u and len(u) >= 4 and u.lower() not in GENERIC_LOGINS else None


def _allowed(rel: str, allow: list[str]) -> bool:
    return any(fnmatch.fnmatch(rel, g) for g in allow)


def ship_type(name: str) -> str | None:
    """'text' or 'image' when a file of this name may ship, else None (BLOCK "type")."""
    ext = Path(name).suffix.lower()
    if ext in IMAGE_EXT:
        return "image"
    if ext in SHIP_TEXT_EXT:
        return "text"
    if SHIP_TEXT_NAMES.match(name) and ext not in BINARY_EXT | CAPTURE_EXT:
        return "text"  # LICENSE, Makefile, .gitignore, README-ja ...
    return None


def _codec(head: bytes) -> str:
    """The text codec a text file must decode with: UTF-16 when it starts with a byte-order
    mark, else UTF-8 (a UTF-8 byte-order mark is accepted)."""
    if head.startswith(b"\xff\xfe"):
        return "utf-16-le"
    if head.startswith(b"\xfe\xff"):
        return "utf-16-be"
    return "utf-8-sig"


def _nfkc(t: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKC", t)


# In a binary file, values sit packed against each other ("githubghp_..."), so a leading word
# boundary never matches there. The strings pass uses the same patterns without it.
# Every word boundary is dropped there, except for the generic "sk-" shape: unanchored, it
# would match ordinary text such as "risk-assessment-for-..." in an image's metadata.
LOOSE_SECRET_PATTERNS = [(label, rx if label.startswith("OpenAI") else re.compile(rx.pattern.replace(r"\b", ""), rx.flags))
                         for label, rx in SECRET_PATTERNS]


def _text_findings(rel: str, text: str, hosts: set[str], user: str | None, deny: list[str],
                   loose: bool = False) -> list[dict]:
    out: list[dict] = []
    for label, rx in (LOOSE_SECRET_PATTERNS if loose else SECRET_PATTERNS):
        if rx.search(text):
            out.append({"kind": "secret", "path": rel, "detail": label})
    for rx in DECOMP_MARKERS:
        m = rx.search(text)
        if m:
            out.append({"kind": "decomp", "path": rel, "detail": f"marker {m.group(0)!r}"})
            break
    # Text is matched as written. Encoded content (URL-encoding, escapes, base64) is not decoded;
    # the file types that usually carry it are listed for a person instead (ENCODED_EXT).
    m = USERPATH.search(text)
    if m:
        out.append({"kind": "userpath", "path": rel, "detail": m.group(0)})
    m = next((m for m in DEVICE_ADDR.finditer(text)
              if re.search(r"[A-Fa-f]", m.group(0)) and not DOC_ADDR.match(m.group(0))), None)
    if m:
        out.append({"kind": "address", "path": rel, "detail": f"hardware address {m.group(0)}"})
    low = _nfkc(text).lower()
    if user:
        ul = user.lower()
        m = re.search(r"~/[^\s'\"`)]*" + re.escape(ul), low)
        if m:
            out.append({"kind": "userpath", "path": rel, "detail": m.group(0)})
        elif re.search(r"(?<![a-z0-9])" + re.escape(ul) + r"(?![a-z0-9])", low):
            out.append({"kind": "username", "path": rel, "detail": user})
    m = MAC_HOST.search(text)
    hit = m.group(0) if m else next((h for h in sorted(hosts) if h in low), None)
    if hit:
        out.append({"kind": "hostname", "path": rel, "detail": hit})
    # Deny terms match across line wraps and repeated spaces ("Ada\n  Lovelace").
    flat = re.sub(r"\s+", " ", low)
    for term in deny:
        t = re.sub(r"\s+", " ", _nfkc(term).lower())
        if t in flat:
            out.append({"kind": "denied", "path": rel, "detail": term})
    return out


def _strings_findings(rel: str, data: bytes, hosts: set[str], user: str | None,
                      deny: list[str]) -> list[dict]:
    """Text patterns over a binary file's printable runs, the way `strings` reads a database
    or an image's metadata: Latin-1, and UTF-16LE at both byte alignments (which also covers
    UTF-16BE ASCII text, one byte over)."""
    out: list[dict] = []
    for text in (data.decode("latin-1"), data.decode("utf-16-le", "ignore"),
                 data[1:].decode("utf-16-le", "ignore")):
        out.extend(_text_findings(rel, text, hosts, user, deny, loose=True))
    return out


def _text_file_findings(f, head: bytes, rel: str, hosts: set[str], user: str | None,
                        deny: list[str]) -> tuple[list[dict], bool]:
    """Findings for a file read as text from `head` on, and whether it decoded as text."""
    decoder = codecs.getincrementaldecoder(_codec(head))("strict")
    out: list[dict] = []
    data, tail = head, ""
    try:
        while True:
            text = decoder.decode(data, final=not data)
            if "\x00" in text:
                return out, False
            out.extend(_text_findings(rel, tail + text, hosts, user, deny))
            if not data:
                return out, True
            tail = (tail + text)[-OVERLAP:]
            data = f.read(CHUNK)
    except UnicodeDecodeError:
        return out, False


def _scan_file(p: Path, rel: str, max_mb: float, hosts: set[str], user: str | None,
               deny: list[str]) -> list[dict]:
    out: list[dict] = []
    ext = p.suffix.lower()
    kind = ship_type(p.name)
    if ext in BINARY_EXT:
        out.append({"kind": "binary", "path": rel, "detail": f"{ext} file"})
    elif ext in CAPTURE_EXT:
        out.append({"kind": "capture", "path": rel, "detail": f"{ext} capture: sessions, cookies, keys"})
    elif p.name.lower() in CREDENTIAL_NAMES:
        out.append({"kind": "secret", "path": rel, "detail": "a well-known credentials file name"})
    elif kind is None and p.name not in JUNK_NAMES:
        what = f"{ext} file" if ext else "file with no extension"
        out.append({"kind": "type", "path": rel,
                    "detail": f"{what} is not on the ship allowlist; --allow it after looking"})
    seen: dict[tuple[str, str], dict] = {}
    try:
        size = p.stat().st_size
        if size > max_mb * 1024 * 1024:
            out.append({"kind": "large", "path": rel, "detail": f"{size / 1048576:.1f} MB > {max_mb} MB"})
        with p.open("rb") as f:
            head = f.read(CHUNK)
            label = next((lb for magic, lb in MAGIC if head.startswith(magic)), None) or (
                "PE" if _is_pe(head) else None)
            if label and ext not in BINARY_EXT:
                out.append({"kind": "binary", "path": rel, "detail": f"{label} header"})
            if kind == "image" and not label and not _is_real_image(ext, head):
                out.append({"kind": "opaque", "path": rel,
                            "detail": "an image extension on a file that is not that image"})
            as_text = kind == "text" and not label
            if as_text:
                # A text type must really be text: strict decoding, no NUL bytes. Anything
                # else (a PDF renamed .txt, compressed data after a text header) is opaque.
                findings, as_text = _text_file_findings(f, head, rel, hosts, user, deny)
                if as_text:
                    for fnd in findings:
                        seen.setdefault((fnd["kind"], fnd["detail"]), fnd)
                else:
                    out.append({"kind": "opaque", "path": rel,
                                "detail": "not plain text (invalid UTF-8 or NUL bytes); --allow it after looking"})
            if not as_text:
                # Images, blocked types, binaries and opaque files: read the printable runs.
                f.seek(0)
                data, tail = f.read(CHUNK), b""
                while data:
                    for fnd in _strings_findings(rel, tail + data, hosts, user, deny):
                        seen.setdefault((fnd["kind"], fnd["detail"]), fnd)
                    tail = data[-OVERLAP:]
                    data = f.read(CHUNK)
    except OSError as e:
        raise Unreadable(f"{rel}: {e.strerror or e}") from e
    out.extend(seen.values())
    return out


def _allowed_path(rel: str, allow: list[str]) -> bool:
    """True when `rel` or any folder above it matches an --allow glob."""
    parts = Path(rel).parts
    return any(_allowed(str(Path(*parts[:k])), allow) for k in range(1, len(parts) + 1))


def _files(root: Path):
    """(relative path, path) for every file the scan enters: SKIP_DIRS are not entered."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            p = Path(dirpath) / name
            yield p.relative_to(root), p


def review_images(root: Path) -> list[str]:
    """Every image a person should look at before sharing (relative paths, sorted). An
    --allow never removes an image from this list: allowing a file is not looking at it."""
    return sorted(str(rel) for rel, _ in _files(root) if rel.suffix.lower() in REVIEW_IMAGE_EXT)


def _extra_kind(rel: Path) -> str | None:
    """'journal', 'evidence', 'fixtures' or 'encoded' for a file a person must read."""
    if rel.name in JOURNAL_NAMES:
        return "journal"
    if rel.suffix.lower() in ENCODED_EXT:
        return "encoded"
    folder = next((f for f in ("evidence", "fixtures") if f in rel.parts[:-1]), None)
    return folder if folder and rel.suffix.lower() not in REVIEW_IMAGE_EXT else None


def review_extra(root: Path) -> list[tuple[str, str]]:
    """(kind, path) pairs a person must read: journals, captured output and fixtures, which
    can carry someone's data, device addresses or keys."""
    return sorted((k, str(rel)) for rel, _ in _files(root) for k in [_extra_kind(rel)] if k)


def special_files(root: Path) -> list[str]:
    """FIFOs, sockets and devices: never read (reading a FIFO hangs), so a person knows."""
    out = []
    for rel, p in _files(root):
        try:
            if not p.is_symlink() and not stat.S_ISREG(p.lstat().st_mode):
                out.append(str(rel))
        except OSError:
            continue
    return sorted(out)


def _name_findings(name: str, hosts: set[str], user: str | None, deny: list[str]) -> list[dict]:
    """File and directory names are published too: run the text patterns over one name."""
    out = []
    for f in _text_findings(name, name, hosts, user, deny):
        if f["kind"] in {"userpath", "username", "hostname", "denied", "secret", "address"}:
            out.append({"kind": f["kind"], "path": name, "detail": f"in the name: {f['detail']}"})
    return out


def _walk_findings(root: Path, max_mb: float, hosts: set[str], user: str | None,
                   deny: list[str], allow: list[str]) -> list[dict]:
    """Every finding for every path under root, before --allow is applied. A bundle folder
    (Foo.app) is one finding and is not entered, unless it is --allow'ed: then its contents
    are scanned like anything else."""
    findings: list[dict] = [dict(f, path=".") for f in _name_findings(root.resolve().name, hosts, user, deny)]
    if root.suffix.lower() in BINARY_EXT:
        findings.append({"kind": "binary", "path": ".", "detail": f"the folder itself is a {root.suffix} bundle"})
    def _unreadable(e: OSError) -> None:
        raise Unreadable(f"{e.filename}: {e.strerror or e}")

    for dirpath, dirnames, filenames in os.walk(root, onerror=_unreadable):
        base = Path(dirpath)
        for d in sorted(d for d in dirnames if d in SKIP_DIRS):
            findings.append({"kind": "folder", "path": str((base / d).relative_to(root)),
                             "detail": "dependency, cache or VCS folder: not part of a mod and not scanned; remove it"})
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for d in list(dirnames):
            dp = base / d
            rel = str(dp.relative_to(root))
            findings.extend(dict(f, path=rel) for f in _name_findings(d, hosts, user, deny))
            if dp.is_symlink():
                dirnames.remove(d)
                findings.extend(_symlink_findings(dp, rel, hosts, user, deny))
            elif Path(d).suffix.lower() in BINARY_EXT:
                findings.append({"kind": "binary", "path": rel, "detail": f"{Path(d).suffix} bundle"})
                if not _allowed_path(rel, allow):
                    dirnames.remove(d)
        for name in sorted(filenames):
            p = base / name
            rel = str(p.relative_to(root))
            findings.extend(dict(f, path=rel) for f in _name_findings(name, hosts, user, deny))
            if p.is_symlink():
                findings.extend(_symlink_findings(p, rel, hosts, user, deny))
                continue
            if name in GITLEAKS_CONFIGS:
                # A gitleaks config or ignore file would silence a plain gitleaks run on the
                # shared tree (gitleaks reads <source>/.gitleaksignore whatever flags say).
                findings.append({"kind": "gitleaks", "path": rel,
                                 "detail": "gitleaks config or ignore file: remove it before sharing a mod"})
            if name in JUNK_NAMES:
                # Blocked as a file (allowable), but its content is still read below:
                # .DS_Store records folder and file names.
                findings.append({"kind": "opaque", "path": rel, "detail": JUNK_NAMES[name]})
            try:
                mode = p.lstat().st_mode
            except OSError as e:
                raise Unreadable(f"{rel}: {e.strerror or e}") from e
            if not stat.S_ISREG(mode):
                continue  # FIFOs, sockets, devices: nothing to ship, and reading a FIFO hangs
            findings.extend(_scan_file(p, rel, max_mb, hosts, user, deny))
    return findings


def gitleaks_findings(root: Path) -> tuple[list[dict], str | None]:
    """Secrets found by gitleaks, a maintained ruleset, and None; or ([], why) when gitleaks
    is not installed. Installed but failing raises Unreadable (exit 2): a broken engine must
    not read as a pass. The secret itself is never printed, only the rule."""
    exe = shutil.which("gitleaks")
    if not exe:
        return [], "gitleaks is not installed"
    import tempfile
    with tempfile.TemporaryDirectory(prefix="publish-check-gl.") as tmp:
        # Force gitleaks' default rules: a .gitleaks.toml, a .gitleaksignore or a
        # gitleaks:allow comment inside the scanned tree must not switch them off.
        cfg = Path(tmp) / "default.toml"
        cfg.write_text("[extend]\nuseDefault = true\n", encoding="utf-8")
        try:
            r = subprocess.run([exe, "dir", str(root), "--no-banner", "--exit-code", "0",
                                "--config", str(cfg), "--gitleaks-ignore-path", tmp,
                                "--ignore-gitleaks-allow", "--report-format", "json",
                                "--report-path", "-"],
                               capture_output=True, text=True, timeout=300)
            data = json.loads(r.stdout or "[]")
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as e:
            raise Unreadable(f"gitleaks is installed but failed ({e}); fix it or pass --no-gitleaks") from e
    if r.returncode != 0:
        raise Unreadable(f"gitleaks is installed but exited {r.returncode}: {r.stderr.strip()[:200]}")
    out = []
    for leak in data or []:
        f = Path(leak.get("File", ""))
        try:
            rel = str((f if f.is_absolute() else Path.cwd() / f).resolve().relative_to(root.resolve()))
        except ValueError:
            rel = str(f)
        out.append({"kind": "secret", "path": rel,
                    "detail": f"gitleaks {leak.get('RuleID', '?')} at line {leak.get('StartLine', '?')}"})
    return out, None


def scan(root: Path, allow: list[str] | None = None, max_mb: float = 5.0,
         hostnames: set[str] | None = None, username: str | None = "",
         deny: list[str] | None = None, use_gitleaks: bool = False) -> list[dict]:
    """Findings for `root`, after --allow. `hostnames`/`username` default to this machine's
    (pass an empty set / None to disable in tests). Raises Unreadable for a file it could
    not read. The CLI also runs gitleaks; pass use_gitleaks=True to do the same here."""
    return scan_report(root, allow, max_mb, hostnames, username, deny, use_gitleaks)["findings"]


def scan_report(root: Path, allow: list[str] | None = None, max_mb: float = 5.0,
                hostnames: set[str] | None = None, username: str | None = "",
                deny: list[str] | None = None, use_gitleaks: bool = True) -> dict:
    """The whole report: findings after --allow, the allowed paths, and the secrets engine."""
    allow = allow or []
    deny = [t for t in (deny or []) if t.strip()]
    hosts = local_hostnames() if hostnames is None else {h.lower() for h in hostnames}
    user = local_username() if username == "" else username
    if not root.is_dir():
        raise FileNotFoundError(root)
    raw = _walk_findings(root, max_mb, hosts, user, deny, allow)
    engine = "PARTIAL: gitleaks was not run (--no-gitleaks); built-in token shapes only"
    if use_gitleaks:
        leaks, why = gitleaks_findings(root)
        raw.extend(leaks)
        engine = "gitleaks plus built-in token shapes" if why is None else f"PARTIAL: {why}; built-in token shapes only"
    findings, allowed = [], set()
    seen = set()
    for f in raw:
        key = (f["kind"], f["path"], f["detail"])
        if key in seen:
            continue
        seen.add(key)
        if f["kind"] in ALLOWABLE and f["path"] != "." and _allowed_path(f["path"], allow):
            allowed.add(f["path"])
            continue
        findings.append(f)
    return {"findings": findings, "allowed": sorted(allowed), "secrets_engine": engine}


def _symlink_findings(p: Path, rel: str, hosts: set[str], user: str | None, deny: list[str]) -> list[dict]:
    """A symlink is one allowable finding, plus a finding for anything its target path leaks.
    Git commits the target path as the file's content, so those are content findings that
    --allow cannot clear."""
    target = os.readlink(p)
    out = [{"kind": "symlink", "path": rel, "detail": f"-> {target}"}]
    for f in _text_findings(rel, target, hosts, user, deny):
        out.append({"kind": f["kind"], "path": rel, "detail": f"in the link target: {f['detail']}"})
    return out


def _report_for(path: Path, allow: list[str], max_mb: float, deny: list[str],
                use_gitleaks: bool) -> dict:
    """scan_report for a folder, or for one file scanned on its own (in a temporary folder,
    reported under its real path)."""
    if path.is_dir():
        rep = scan_report(path, allow, max_mb, deny=deny, use_gitleaks=use_gitleaks)
        rep["review"] = review_images(path)
        rep["extra"] = review_extra(path)
        rep["skipped"] = special_files(path)
        rep["label"] = str(path)
        return rep
    import tempfile
    if path.is_symlink():
        hosts, user = local_hostnames(), local_username()
        return {"findings": _symlink_findings(path, path.name, hosts, user, deny), "allowed": [],
                "secrets_engine": "not needed for a link", "review": [], "extra": [], "skipped": [],
                "label": str(path.parent)}
    with tempfile.TemporaryDirectory(prefix="publish-check-file.") as tmp:
        try:
            shutil.copyfile(path, Path(tmp) / path.name)
        except OSError as e:
            raise Unreadable(f"{path}: {e.strerror or e}") from e
        rep = scan_report(Path(tmp), allow, max_mb, deny=deny, use_gitleaks=use_gitleaks)
        rep["findings"] = [f for f in rep["findings"] if f["path"] != "."]
        rep["review"] = review_images(Path(tmp))
        rep["extra"] = review_extra(Path(tmp))
        kind = _extra_kind(path)
        if kind:
            rep["extra"].append((kind, path.name))
        rep["skipped"] = []
    rep["label"] = str(path.parent)
    return rep


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="publish_check.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", help="folders or single files to check")
    ap.add_argument("--allow", action="append", default=[],
                    help="glob (relative to each scanned folder): clears type/binary/opaque/capture/large/"
                         "symlink findings for matching paths after you looked; content and name findings "
                         "still apply. Say why in the field note")
    ap.add_argument("--deny-file", help="file with one private term per line that must not appear")
    ap.add_argument("--max-mb", type=float, default=5.0)
    ap.add_argument("--no-gitleaks", action="store_true", help="skip gitleaks even when installed (reported as PARTIAL)")
    ap.add_argument("--json", action="store_true")
    ns = ap.parse_args(argv)
    if not (ns.max_mb > 0 and ns.max_mb != float("inf")):
        print(f"--max-mb must be a positive number, got {ns.max_mb}", file=sys.stderr)
        return 2
    roots = [Path(x) for x in ns.paths]
    for r in roots:
        if not (r.is_dir() or r.is_file()):
            print(f"not a folder or file: {r}", file=sys.stderr)
            return 2
    deny: list[str] = []
    if ns.deny_file:
        try:
            deny = [ln.strip().removeprefix("\\") for ln in Path(ns.deny_file).read_text(encoding="utf-8").splitlines()
                    if ln.strip() and not ln.lstrip().startswith("#")]  # "\\#term" denies a term starting with #
        except (OSError, UnicodeDecodeError) as e:
            print(f"cannot read --deny-file: {e}", file=sys.stderr)
            return 2
    reports = []
    try:
        for r in roots:
            reports.append(_report_for(r, ns.allow, ns.max_mb, deny, not ns.no_gitleaks))
    except Unreadable as e:
        print(f"cannot read {e} — nothing is reported clean that was not read", file=sys.stderr)
        return 2
    total = sum(len(rep["findings"]) for rep in reports)
    if ns.json:
        print(json.dumps([{"path": str(r), **{k: v for k, v in rep.items() if k != "label"}}
                          for r, rep in zip(roots, reports)], indent=2))
        return 1 if total else 0
    single = len(roots) == 1 and roots[0].is_dir()
    for r, rep in zip(roots, reports):
        def where(rel: str, r: Path = r) -> str:
            if r.is_file():
                return str(r)
            if single:
                return rel
            return str(r) if rel == "." else str(r / rel)
        for f in rep["findings"]:
            print(f"BLOCK {f['kind']:8} {where(f['path'])}  ({f['detail']})")
        for i in rep["review"]:
            print(f"REVIEW image    {where(i)}  (look at it: screenshots can show private content)")
        for kind, x in rep["extra"]:
            why = {"journal": "a run journal: ship it only if every entry is fit to publish",
                   "encoded": "can embed encoded content this scan does not decode: open it and check"
                   }.get(kind, "captured output or fixture: check it holds no one's data, device "
                               "addresses, serials or keys")
            print(f"REVIEW {kind:8} {where(x)}  ({why})")
        for a in rep["allowed"]:
            print(f"REVIEW allowed  {where(a)}  (--allow cleared it as a file; its content, or a link's target, "
                  f"was still scanned)")
        for sk in rep["skipped"]:
            print(f"REVIEW special  {where(sk)}  (FIFO, socket or device: not read, does not ship)")
        if rep["secrets_engine"].startswith("PARTIAL"):
            prefix = "" if single else f"{r}: "
            print(f"REVIEW secrets  {prefix}{rep['secrets_engine']} — install gitleaks for a maintained ruleset")
    print(f"{total} finding(s)" if total else
          "OK: nothing this filter recognises (it cannot see cookies, sessions or personal data "
          "not in --deny-file); read every REVIEW line before sharing")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())

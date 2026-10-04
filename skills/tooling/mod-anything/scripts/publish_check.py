#!/usr/bin/env python3
"""publish_check — a fail-closed filter in front of a person, before a mod is shared.

Run it before anything leaves the machine: a commit to a public repo, a pull request to a shared
knowledge base, a release, a post. It decides what it can decide and hands the rest to a person.

BLOCK (exit 1), file by file:
  binary    third-party program or asset formats, by extension (.asar, .dylib, .framework,
            .node, .jar, ROM and disc images, game archives, app bundles) or by executable
            header (Mach-O, ELF, PE). Ship code, patches and converters, never the target's bytes
  opaque    any other non-text file that is not an image (a database, an archive, a
            profile's log, .DS_Store): this scan cannot read it, so it fails closed
  capture   network and device captures by extension (.har, .pcap, .pcapng, .pklg, .btsnoop)
  symlink   every symbolic link (git commits the target path; archivers follow it)
  large     any file over --max-mb (default 5)
  secret    found by gitleaks (`gitleaks dir`, run with its default rules: an in-tree config,
            ignore file or gitleaks:allow comment cannot switch them off) when it is installed,
            plus a short built-in list of token shapes (private keys, AWS, GitHub classic and
            fine-grained, Slack, OpenAI-style keys, bearer tokens, JWTs). gitleaks skips binary
            files, so those get the built-in list only. Without gitleaks only the built-in list
            runs, and a REVIEW line says so
  decomp    headers that decompilers write into their output
  userpath  home-directory paths, and ~/... paths that contain this machine's login name
  username  this machine's login name (generic container logins are ignored)
  hostname  this machine's hostname, or a Mac-style one (<name>-MacBook-Pro.local)
  denied    any term from --deny-file (one per line; put a backslash before a term that
            starts with #, which otherwise marks a comment)

Names are checked like contents: git publishes file and folder names too. Non-text files are
also read for printable text, so a path in an image's metadata is found.

--allow GLOB clears only the "is this file shippable at all" findings (binary, opaque,
capture, large, symlink) for matching paths and their contents. Content and name findings
still apply, and every allowed path is listed for review.

REVIEW (exit unaffected): images (and a file whose extension claims an image its bytes are
not is opaque instead), every file under an `evidence/` folder (captured output can carry
someone's data), allowed paths, skipped folders (node_modules, .git, virtualenvs), special
files, any gitleaks config inside the scanned tree, and the secrets engine whenever gitleaks
did not run (missing, failed, or --no-gitleaks).

NOT detected, by design: cookies and session values, personal data such as emails and display
names, and code transcribed from a decompiler without its header. Keep them out at the source
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
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache", ".pytest_cache"}

SECRET_PATTERNS = [
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("AWS access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("GitHub fine-grained token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("OpenAI/Anthropic-style key", re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{20,}\b")),
    ("bearer token", re.compile(r"(?i)\bauthorization\b[\"']?\s*[:=]\s*[\"']?bearer\s+[A-Za-z0-9._~+/-]{12,}")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")),
]
# Findings an --allow can clear: they say "this file should not ship", not "this text leaks".
ALLOWABLE = {"binary", "opaque", "capture", "large", "symlink"}
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
USERPATH = re.compile(r"(?:/Users/|/home/)(?!Shared\b)[A-Za-z0-9][A-Za-z0-9._-]*(?:/|\b)|[A-Za-z]:\\\\?Users\\\\?[A-Za-z0-9._-]+")
MAC_HOST = re.compile(r"\b[A-Za-z0-9][A-Za-z0-9-]*-(?:MacBook(?:-Pro|-Air)?|iMac(?:-Pro)?|Mac-mini|Mac-Pro|Mac-Studio)(?:-\d+)?(?:\.local)?\b")
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic", ".tiff", ".bmp"}
# An image extension must be backed by the image's own header; anything else is opaque.
IMAGE_MAGIC = {".png": (b"\x89PNG",), ".jpg": (b"\xff\xd8\xff",), ".jpeg": (b"\xff\xd8\xff",),
               ".gif": (b"GIF87a", b"GIF89a"), ".webp": (b"RIFF",), ".bmp": (b"BM",)}
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


def _codec(head: bytes) -> str | None:
    """The text codec for a file, decided once from its first bytes; None for binary."""
    if head.startswith(b"\xff\xfe"):
        return "utf-16-le"
    if head.startswith(b"\xfe\xff"):
        return "utf-16-be"
    if b"\x00" in head[:8192]:
        return None
    return "utf-8"


def _nfkc(t: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKC", t)


# In a binary file, values sit packed against each other ("githubghp_..."), so a leading word
# boundary never matches there. The strings pass uses the same patterns without it.
LOOSE_SECRET_PATTERNS = [(label, re.compile(rx.pattern.replace(r"\b", "", 1), rx.flags))
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
    m = USERPATH.search(text)
    if m:
        out.append({"kind": "userpath", "path": rel, "detail": m.group(0)})
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
    for term in deny:
        if _nfkc(term).lower() in low:
            out.append({"kind": "denied", "path": rel, "detail": term})
    return out


def _strings_findings(rel: str, data: bytes, hosts: set[str], user: str | None,
                      deny: list[str]) -> list[dict]:
    """Text patterns over a binary file's printable runs (latin-1 and UTF-16LE), the way
    `strings` reads a database or a log that starts with a NUL."""
    out: list[dict] = []
    for text in (data.decode("latin-1"), data.decode("utf-16-le", "ignore")):
        out.extend(_text_findings(rel, text, hosts, user, deny, loose=True))
    return out


def _scan_file(p: Path, rel: str, max_mb: float, hosts: set[str], user: str | None,
               deny: list[str]) -> list[dict]:
    out: list[dict] = []
    ext = p.suffix.lower()
    if ext in BINARY_EXT:
        out.append({"kind": "binary", "path": rel, "detail": f"{ext} file"})
    if ext in CAPTURE_EXT:
        out.append({"kind": "capture", "path": rel, "detail": f"{ext} capture: sessions, cookies, keys"})
    seen: dict[tuple[str, str], dict] = {}
    try:
        size = p.stat().st_size
        if size > max_mb * 1024 * 1024:
            out.append({"kind": "large", "path": rel, "detail": f"{size / 1048576:.1f} MB > {max_mb} MB"})
        with p.open("rb") as f:
            head = f.read(CHUNK)
            codec = _codec(head)
            label = next((lb for magic, lb in MAGIC if head.startswith(magic)), None) or (
                "PE" if _is_pe(head) else None)
            if label and ext not in BINARY_EXT:
                out.append({"kind": "binary", "path": rel, "detail": f"{label} header"})
            if codec is None:
                # Not text. A real image is listed for a person to look at; anything else is
                # opaque to this scan and fails closed. Either way, read its printable runs.
                real_image = ext in IMAGE_EXT and (ext not in IMAGE_MAGIC or head.startswith(IMAGE_MAGIC[ext]))
                if not real_image and ext not in BINARY_EXT and ext not in CAPTURE_EXT and not label:
                    detail = ("an image extension on a file that is not that image"
                              if ext in IMAGE_EXT else "non-text file this scan cannot read; --allow it after looking")
                    out.append({"kind": "opaque", "path": rel, "detail": detail})
                data, tail = head, b""
                while data:
                    for fnd in _strings_findings(rel, tail + data, hosts, user, deny):
                        seen.setdefault((fnd["kind"], fnd["detail"]), fnd)
                    tail = data[-OVERLAP:]
                    data = f.read(CHUNK)
            else:
                data, tail = head, b""
                while data:
                    text = (tail + data).decode(codec, "ignore")
                    for fnd in _text_findings(rel, text, hosts, user, deny):
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


def review_images(root: Path) -> list[str]:
    """Every image a person should look at before sharing (relative paths, sorted). An
    --allow never removes an image from this list: allowing a file is not looking at it."""
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            p = Path(dirpath) / name
            if p.suffix.lower() in IMAGE_EXT:
                out.append(str(p.relative_to(root)))
    return sorted(out)


def review_extra(root: Path) -> list[tuple[str, str]]:
    """(kind, path) pairs a person must look at: captured evidence, and gitleaks config or
    ignore files inside the tree (they would change what a plain gitleaks run reports)."""
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            rel = Path(dirpath, name).relative_to(root)
            if "evidence" in rel.parts[:-1] and rel.suffix.lower() not in IMAGE_EXT:
                out.append(("evidence", str(rel)))
            if name in GITLEAKS_CONFIGS:
                out.append(("gitleaks", str(rel)))
    return sorted(out)


def skipped_dirs(root: Path) -> list[str]:
    """Directories the scan does not enter, and special files it does not read, so a person
    knows what was not scanned."""
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        for d in dirnames:
            if d in SKIP_DIRS:
                out.append(str((Path(dirpath) / d).relative_to(root)))
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            p = Path(dirpath) / name
            try:
                if not p.is_symlink() and not stat.S_ISREG(p.lstat().st_mode):
                    out.append(str(p.relative_to(root)))
            except OSError:
                continue
    return sorted(out)


def _name_findings(name: str, hosts: set[str], user: str | None, deny: list[str]) -> list[dict]:
    """File and directory names are published too: run the text patterns over one name."""
    out = []
    for f in _text_findings(name, name, hosts, user, deny):
        if f["kind"] in {"userpath", "username", "hostname", "denied", "secret"}:
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
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        base = Path(dirpath)
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
    is not installed or did not run. The secret itself is never printed, only the rule."""
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
            return [], f"gitleaks did not run ({e})"
    if r.returncode != 0:
        return [], f"gitleaks exited {r.returncode}"
    out = []
    for leak in data or []:
        f = Path(leak.get("File", ""))
        try:
            rel = str((f if f.is_absolute() else Path.cwd() / f).resolve().relative_to(root.resolve()))
        except ValueError:
            rel = str(f)
        if any(part in SKIP_DIRS for part in Path(rel).parts):
            continue
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
        engine = f"gitleaks plus built-in token shapes" if why is None else f"PARTIAL: {why}; built-in token shapes only"
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
        rep["skipped"] = skipped_dirs(path)
        rep["label"] = str(path)
        return rep
    import tempfile
    with tempfile.TemporaryDirectory(prefix="publish-check-file.") as tmp:
        shutil.copy2(path, Path(tmp) / path.name)
        rep = scan_report(Path(tmp), allow, max_mb, deny=deny, use_gitleaks=use_gitleaks)
        rep["findings"] = [f for f in rep["findings"] if f["path"] != "."]
        rep["review"] = review_images(Path(tmp))
        rep["extra"] = review_extra(Path(tmp))
        rep["skipped"] = []
    rep["label"] = str(path.parent)
    return rep


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="publish_check.py", description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="+", help="folders or single files to check")
    ap.add_argument("--allow", action="append", default=[],
                    help="glob (relative to a folder): clears binary/opaque/capture/large/symlink findings "
                         "for matching paths; content and name findings still apply. Say why in the field note")
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
            msg = ("captured output: check it holds no one's data" if kind == "evidence"
                   else "gitleaks config in the tree: it would change a plain gitleaks run (this scan ignores it)")
            print(f"REVIEW {kind:8} {where(x)}  ({msg})")
        for a in rep["allowed"]:
            print(f"REVIEW allowed  {where(a)}  (--allow cleared it as a file; its content was still scanned)")
        for sk in rep["skipped"]:
            print(f"REVIEW skipped  {where(sk)}  (not scanned)")
        if rep["secrets_engine"].startswith("PARTIAL"):
            prefix = "" if single else f"{r}: "
            print(f"REVIEW secrets  {prefix}{rep['secrets_engine']} — install gitleaks for a maintained ruleset")
    print(f"{total} finding(s)" if total else
          "OK: nothing this filter recognises; read every REVIEW line before sharing")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())

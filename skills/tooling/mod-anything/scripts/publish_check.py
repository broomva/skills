#!/usr/bin/env python3
"""publish_check — refuse to share a mod that carries what it must not.

Scans a mod's folder before anything leaves the machine: a commit to a public repo,
a pull request to a shared knowledge base, a release, a post. Finds:

  binary    third-party program or asset formats: by extension (.asar, .dylib, .framework,
            .node, .jar, ROM and disc images, game archives, app bundles) or by content
            (Mach-O, ELF, PE headers). Ship code, patches and converters, never the
            target's bytes
  opaque    any other non-text file that is not an image (a database, an archive, a
            profile's log): the scan cannot read it, so it fails closed until --allow'ed
  capture   network and device captures (.har, .pcap, .pcapng, .pklg, .btsnoop, ...): they
            carry sessions, cookies and link keys
  symlink   every symbolic link: git commits a link's target path as the file's content,
            and an archiver that follows links ships whatever it points at
  large     any file over --max-mb (default 5), which is rarely our own source
  secret    credentials: private-key blocks, AWS/GitHub/Slack/OpenAI-style tokens, bearer
            tokens, JWTs, Cookie/Set-Cookie headers
  decomp    headers that decompilers and disassemblers write into their output
  userpath  home-directory paths: /Users/<name>/, /home/<name>/, C:\\Users\\<name>\\, and
            ~/... paths that contain this machine's login name
  username  this machine's login name anywhere in text (names shorter than 4 are skipped)
  hostname  this machine's hostname, or a Mac-style one (<name>-MacBook-Pro.local)
  denied    any term from --deny-file (one per line): private names, project slugs,
            anything you know must not leave, which no pattern can guess

File and directory NAMES are checked with the same text patterns as contents: git publishes
names too.

It also prints REVIEW lines, which do not change the exit code: every image (a screenshot can
show private content that no text scan sees), every directory it skipped (node_modules, .git,
virtualenvs), and every special file (FIFO, socket) it did not read.

A pass means "nothing this filter recognises", not "nothing private". It is a filter in front
of a person reading every REVIEW line, never a substitute for that reading.

Usage:  publish_check.py <dir> [--allow GLOB ...] [--deny-file F] [--max-mb N] [--json]
Exit 0 clean · 1 findings · 2 usage error or a file it could not read (nothing is
reported clean that was not read). Pure stdlib.

What it cannot see: whether code was *transcribed* from a decompiler without its header,
whether an asset was redrawn too closely, or whether the target's terms allow sharing at all.
Those stay with the human review this gate precedes.
"""
from __future__ import annotations

import argparse
import fnmatch
import getpass
import json
import os
import re
import socket
import stat
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
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("OpenAI/Anthropic-style key", re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{20,}\b")),
    ("bearer token", re.compile(r"(?i)\bauthorization\b[\"']?\s*[:=]\s*[\"']?bearer\s+[A-Za-z0-9._~+/-]{12,}")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")),
    ("cookie header", re.compile(r"(?im)^\s*[\"']?(?:set-)?cookie[\"']?\s*[:=]\s*[\"']?[^\s\"']+=[^\s\"';]{6,}")),
]
DECOMP_MARKERS = [
    re.compile(r"(?i)decompiled (?:with|by)\b"),
    re.compile(r"\bILSpy\b"),
    re.compile(r"(?i)\bjadx\b"),
    re.compile(r"(?i)generated by ghidra"),
    re.compile(r"(?i)\bhex-rays\b"),
    re.compile(r"(?i)\bJD-GUI\b"),
    re.compile(r"(?i)\bdnSpy\b"),
]
USERPATH = re.compile(r"(?:/Users/|/home/)(?!Shared\b)[A-Za-z0-9._-]+/|[A-Za-z]:\\\\?Users\\\\?[A-Za-z0-9._-]+")
MAC_HOST = re.compile(r"\b[A-Za-z0-9][A-Za-z0-9-]*-(?:MacBook(?:-Pro|-Air)?|iMac(?:-Pro)?|Mac-mini|Mac-Pro|Mac-Studio)(?:-\d+)?(?:\.local)?\b")
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic", ".tiff", ".bmp"}
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


def _text_findings(rel: str, text: str, hosts: set[str], user: str | None, deny: list[str]) -> list[dict]:
    out: list[dict] = []
    for label, rx in SECRET_PATTERNS:
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
        out.extend(_text_findings(rel, text, hosts, user, deny))
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
                # Not text. Images are listed for a person to look at; anything else is
                # opaque to this scan and fails closed. Either way, read its printable runs.
                if ext not in IMAGE_EXT and ext not in BINARY_EXT and ext not in CAPTURE_EXT and not label:
                    out.append({"kind": "opaque", "path": rel,
                                "detail": "non-text file this scan cannot read; --allow it after looking"})
                data = head
                while data:
                    for fnd in _strings_findings(rel, data, hosts, user, deny):
                        seen.setdefault((fnd["kind"], fnd["detail"]), fnd)
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


def review_images(root: Path, allow: list[str] | None = None) -> list[str]:
    """Every image a person should look at before sharing (relative paths, sorted)."""
    allow = allow or []
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            p = Path(dirpath) / name
            rel = str(p.relative_to(root))
            if p.suffix.lower() in IMAGE_EXT and not _allowed(rel, allow):
                out.append(rel)
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


def _name_findings(rel: str, hosts: set[str], user: str | None, deny: list[str]) -> list[dict]:
    """File and directory names are published too: run the text patterns over the path."""
    out = []
    for f in _text_findings(rel, rel, hosts, user, deny):
        if f["kind"] in {"userpath", "username", "hostname", "denied", "secret"}:
            out.append({"kind": f["kind"], "path": rel, "detail": f"in the name: {f['detail']}"})
    return out


def scan(root: Path, allow: list[str] | None = None, max_mb: float = 5.0,
         hostnames: set[str] | None = None, username: str | None = "",
         deny: list[str] | None = None) -> list[dict]:
    """Findings for `root`. `hostnames`/`username` default to this machine's (pass an empty
    set / None to disable in tests). Raises Unreadable for a file it could not read."""
    allow = allow or []
    deny = [t for t in (deny or []) if t.strip()]
    hosts = local_hostnames() if hostnames is None else {h.lower() for h in hostnames}
    user = local_username() if username == "" else username
    findings: list[dict] = []
    if not root.is_dir():
        raise FileNotFoundError(root)
    if root.suffix.lower() in BINARY_EXT:
        findings.append({"kind": "binary", "path": ".", "detail": f"the folder itself is a {root.suffix} bundle"})
        return findings
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        base = Path(dirpath)
        for d in list(dirnames):
            dp = base / d
            rel = str(dp.relative_to(root))
            if not _allowed(rel, allow):
                findings.extend(dict(f, path=rel) for f in _name_findings(d, hosts, user, deny))
            if dp.is_symlink():
                dirnames.remove(d)
                if not _allowed(rel, allow):
                    findings.append(_symlink_finding(dp, rel, hosts, user, deny))
                continue
            if Path(d).suffix.lower() in BINARY_EXT:
                if not _allowed(rel, allow):
                    findings.append({"kind": "binary", "path": rel, "detail": f"{Path(d).suffix} bundle"})
                dirnames.remove(d)
        for name in sorted(filenames):
            p = base / name
            rel = str(p.relative_to(root))
            if _allowed(rel, allow):
                continue
            findings.extend(dict(f, path=rel) for f in _name_findings(name, hosts, user, deny))
            if p.is_symlink():
                findings.append(_symlink_finding(p, rel, hosts, user, deny))
                continue
            try:
                mode = p.lstat().st_mode
            except OSError as e:
                raise Unreadable(f"{rel}: {e.strerror or e}") from e
            if not stat.S_ISREG(mode):
                continue  # FIFOs, sockets, devices: nothing to ship, and reading a FIFO hangs
            findings.extend(_scan_file(p, rel, max_mb, hosts, user, deny))
    return findings


def _symlink_finding(p: Path, rel: str, hosts: set[str], user: str | None, deny: list[str]) -> dict:
    target = os.readlink(p)
    extra = _text_findings(rel, target, hosts, user, deny)
    detail = f"-> {target}"
    if extra:
        detail += " (target path also leaks: " + ", ".join(sorted({f["kind"] for f in extra})) + ")"
    return {"kind": "symlink", "path": rel, "detail": detail}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="publish_check.py", description=__doc__.split("\n")[0])
    ap.add_argument("dir")
    ap.add_argument("--allow", action="append", default=[],
                    help="glob (relative to dir) to exempt, e.g. 'assets/own/*.png'; say why in the field note")
    ap.add_argument("--deny-file", help="file with one private term per line that must not appear")
    ap.add_argument("--max-mb", type=float, default=5.0)
    ap.add_argument("--json", action="store_true")
    ns = ap.parse_args(argv)
    root = Path(ns.dir)
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2
    deny: list[str] = []
    if ns.deny_file:
        try:
            deny = [ln.strip().removeprefix("\\") for ln in Path(ns.deny_file).read_text(encoding="utf-8").splitlines()
                    if ln.strip() and not ln.lstrip().startswith("#")]  # write "\\#term" to deny a term starting with #
        except (OSError, UnicodeDecodeError) as e:
            print(f"cannot read --deny-file: {e}", file=sys.stderr)
            return 2
    try:
        findings = scan(root, ns.allow, ns.max_mb, deny=deny)
    except Unreadable as e:
        print(f"cannot read {e} — nothing is reported clean that was not read", file=sys.stderr)
        return 2
    review = review_images(root, ns.allow)
    skipped = skipped_dirs(root)
    if ns.json:
        print(json.dumps({"dir": str(root), "findings": findings, "review": review,
                          "skipped": skipped}, indent=2))
    else:
        for f in findings:
            print(f"BLOCK {f['kind']:8} {f['path']}  ({f['detail']})")
        for r in review:
            print(f"REVIEW image    {r}  (look at it: screenshots can show private content)")
        for s in skipped:
            print(f"REVIEW skipped  {s}  (not scanned)")
        print(f"{len(findings)} finding(s) in {root}" if findings else
              f"OK {root}: nothing this filter recognises; read every REVIEW line before sharing")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())

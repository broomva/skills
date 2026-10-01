"""Context keys: the one vocabulary System 1 and System 2 share.

System 2 (ctx_s2.py) indexes every candidate item under keys; System 1
(ctx_s1.py) builds keys from a hook event and looks them up. Both call the
functions here, so an item and an event that name the same thing produce the
same key string. A key is `<channel>:<value>`:

    p:<path>      a path, repo-relative (`skills/orchestration/ctx-core/SKILL.md`),
                  or `~/...` for a file outside every repo
    d:<dir>       a directory of such a path, at least two segments deep
    f:<a>/<b>     the last two segments of a path (catches a partial citation)
    b:<branch>    a git branch
    pr:<repo>#<n> a pull request, by the GitHub repo's name
    t:<ticket>    a ticket id (`t:bro-2674`)
    w:<term>      a word of text

The cache and the snapshot never care what a key means: E1 replays HMAC-hashed
keys through the same lookup. Only this module knows how a key is made.

Stdlib only, cheap to import on the hook path: os, re, zlib. shlex is imported
inside the Bash helpers, which run only on the post-bash stage.
"""

from __future__ import annotations

import os
import re
import zlib

TYPE_CHECKING = False
if TYPE_CHECKING:
    from typing import Dict, Iterable, List, Optional, Sequence, Tuple

CHANNELS = ("p", "d", "f", "b", "pr", "t", "w")
#: Query-side channels. `s` holds search words from a shell command: its keys
#: are `w:` keys (items have only words), weighted apart.
QUERY_CHANNELS = CHANNELS + ("s",)

#: Cache layout, shared by the writer (ctx_s2) and the reader (ctx_s1).
POSTING_BUCKETS = 4096
ITEMS_PER_FILE = 32
CACHE_LINK = "rank-current"
CACHE_PREFIX = "rank-"


def bucket(key: str) -> str:
    """The posting file a key lives in: crc32, so the hook imports no hashlib."""
    return "%03x" % (zlib.crc32(key.encode("utf-8")) & (POSTING_BUCKETS - 1))


def item_file(idx: int) -> str:
    return "%05d" % (idx // ITEMS_PER_FILE)


# --------------------------------------------------------------------------
# Words

#: English function words plus words that appear in almost every prompt or
#: document here and so carry no signal.
STOPWORDS = frozenset("""
a about above after again against all also am an and any are as at be because been before being
below between both but by can could did do does doing done down during each else etc few for from
further get gets got had has have having he her here hers him his how i if in into is it its itself
just let lets like make made many may me might more most much must my need no nor not now of off on
once one only or other our ours out over own per please same she should so some such than that the
their them then there these they this those through to too under until up upon us use used using very
via want was we were what when where which while who whom why will with would yes yet you your yours
ok okay thing things way also still really sure well now new see look show tell think know go going
file files code work working run running make let's i'm it's don't can't that's there's what's
""".split())

_WORD_RE = re.compile(r"[a-z0-9][a-z0-9_]*")
TICKET_RE = re.compile(r"(?<![A-Za-z0-9])([A-Z]{2,6})-(\d{1,6})(?![A-Za-z0-9])")
PR_REF_RE = re.compile(r"(?<![\w/.-])([A-Za-z][\w.-]{1,40})#(\d{1,6})\b")
PR_URL_RE = re.compile(r"github\.com/[\w.-]+/([\w.-]+)/pull/(\d{1,6})")
BRANCH_RE = re.compile(r"(?<![\w/.-])((?:feat|fix|docs|chore|ci|research|refactor|test|kg|checkit|perf|build)"
                       r"/[A-Za-z0-9][\w./-]{0,80})")
#: A path-shaped token: two or more segments, the last one a file or a dir.
PATH_RE = re.compile(r"(?:~/|/)?(?:[\w@.+-]+/)+[\w@.+-]*")
_EXT_RE = re.compile(r"\.[A-Za-z][A-Za-z0-9]{0,7}$")
_DOMAIN_RE = re.compile(r"^[\w-]+(\.[\w-]+)*\.(com|org|io|ai|dev|net|tech|app|co|sh|so|xyz|me)$", re.I)
#: Top-level directories a two-segment citation may start with and still be a path.
_TOP_DIRS = frozenset(("docs", "scripts", "skills", "research", "src", "tests", "core", "apps", "packages",
                       "roles", "evals", "crates", "lib", "bin", "tools", "ops", "schemas", "references",
                       ".github", ".claude", ".control", "web", "app", "engine"))


def stem(w: str) -> str:
    """A crude, deterministic plural strip: `hooks` and `hook` share a key."""
    if len(w) > 4 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def terms(text: str, cap: int = 0) -> List[str]:
    """Content words of `text`, in order, repeats kept (term frequency matters).
    Lowercased, stemmed, stopwords and numbers dropped, 3 to 31 characters: a
    run of 32 is what ctx-core's guard treats as a token, and a token is never
    a key."""
    out: List[str] = []
    for m in _WORD_RE.finditer(text.lower()):
        w = m.group(0).strip("_")
        if len(w) < 3 or len(w) > 31 or w in STOPWORDS or w.isdigit():
            continue
        out.append(stem(w))
        if cap and len(out) >= cap:
            break
    return out


def tickets(text: str) -> List[str]:
    return ["%s-%s" % (a.lower(), b) for a, b in TICKET_RE.findall(text)]


def pr_refs(text: str) -> List[str]:
    """`repo#n` and GitHub PR URLs, as `repo#n` with the repo's bare name."""
    out = []
    for repo, n in PR_URL_RE.findall(text):
        out.append("%s#%s" % (repo.lower(), n))
    for repo, n in PR_REF_RE.findall(text):
        out.append("%s#%s" % (repo.rsplit("/", 1)[-1].lower(), n))
    return out


def branches(text: str) -> List[str]:
    """Branch names a text cites (`feat/x`, `docs/some-spec`). A match whose last
    segment has a file extension is a path (`docs/specs/x.html`), not a branch."""
    out = []
    for b in BRANCH_RE.findall(text):
        b = b.rstrip(".,;:)")
        if not _EXT_RE.search(b.rsplit("/", 1)[-1]):
            out.append(b)
    return out


# --------------------------------------------------------------------------
# Paths

def home() -> str:
    return os.environ.get("HOME") or os.path.expanduser("~")


def norm_cited(raw: str, roots: Sequence[Tuple[str, str]]) -> Optional[str]:
    """A path as a document cites it, normalised to the key form, or None.

    `roots` is [(absolute repo root, name)], longest first. A citation under a
    repo root becomes repo-relative; one under HOME becomes `~/...`; a relative
    one is kept as written. At least two segments are required: `ctx.py` alone
    names nothing in particular."""
    p = raw.strip().strip("`'\"()[]{}<>,;:").rstrip(".")
    if not p or "://" in p or len(p) > 240:
        return None
    h = home()
    if p.startswith("~/"):
        p = h + p[1:]
    if p.startswith("/"):
        for root, _ in roots:
            if p == root or p.startswith(root + "/"):
                p = p[len(root) + 1:]
                break
        else:
            if p.startswith(h + "/"):
                p = "~" + p[len(h):]
            else:
                return None
    while p.startswith("./"):
        p = p[2:]
    p = p.rstrip("/")
    parts = p.split("/")
    if len(parts) < 2 or ".." in parts or any(not s or s.isdigit() for s in parts):
        return None
    if _DOMAIN_RE.match(parts[0]) or all(len(s) <= 1 for s in parts):
        return None  # github.com/x/y is a URL fragment; a/b/c is a placeholder
    if len(parts) == 2 and not _EXT_RE.search(parts[-1]) and BRANCH_RE.fullmatch(p):
        return None  # feat/x is a branch, keyed as b:; docs/specs/x.html is a path
    # A file (the last segment has an extension) or a deep enough directory;
    # "push/pull" and "branch-merge/crdt" are prose, not paths.
    if not _EXT_RE.search(parts[-1]) and not (parts[0] == "~" or len(parts) >= 3 or parts[0] in _TOP_DIRS):
        return None
    return p


def cited_paths(text: str, roots: Sequence[Tuple[str, str]], cap: int = 400) -> List[str]:
    out, seen = [], set()
    for m in PATH_RE.finditer(text):
        p = norm_cited(m.group(0), roots)
        if p and p not in seen:
            seen.add(p)
            out.append(p)
            if len(out) >= cap:
                break
    return out


def path_keys(rel: str) -> List[str]:
    """p:, d: and f: keys for one normalised path. A directory citation (no
    extension on its last segment) is also a d: key."""
    if not rel:
        return []
    rel = rel.lower()
    parts = rel.split("/")
    keys = ["p:" + rel]
    if len(parts) >= 2:
        keys.append("f:" + "/".join(parts[-2:]))
    start = 2 if not parts[0] == "~" else 3
    for i in range(start, len(parts)):
        keys.append("d:" + "/".join(parts[:i]))
    if "." not in parts[-1] and len(parts) >= start:
        keys.append("d:" + rel)
    return keys


def rel_to_repo(abs_path: str, toplevel: Optional[str]) -> Optional[str]:
    """An absolute path as a key path: relative to its repo's top level when it
    is inside it, `~/...` when under HOME, else None."""
    if not abs_path or not abs_path.startswith("/"):
        return None
    p = os.path.normpath(abs_path)
    if toplevel and (p == toplevel or p.startswith(toplevel.rstrip("/") + "/")):
        rel = p[len(toplevel.rstrip("/")) + 1:]
        return rel or None
    h = home()
    if p.startswith(h + "/"):
        return "~" + p[len(h):]
    return None


def memory_key(abs_path: str) -> Optional[str]:
    """A memory file (`~/.claude/projects/<p>/memory/<f>.md`) is keyed by name."""
    m = re.search(r"/\.claude/projects/[^/]+/memory/([\w.-]+\.md)$", abs_path or "")
    return ("m:" + m.group(1).lower()) if m else None


# --------------------------------------------------------------------------
# Bash: what a command reads, and whether it pushed or merged

_READERS = frozenset(("cat", "head", "tail", "less", "more", "bat", "sed", "awk", "rg", "grep",
                      "wc", "nl", "view", "jq", "yq", "diff", "cut", "sort", "uniq"))
_PATTERN_FIRST = frozenset(("sed", "awk", "rg", "grep", "jq", "yq"))
#: Options whose next token is a value, not a file.
_VALUE_OPTS = {
    "head": ("-n", "-c"), "tail": ("-n", "-c"), "sed": ("-e", "-f"), "awk": ("-f", "-v", "-F"),
    "grep": ("-e", "-f", "-m", "-A", "-B", "-C"), "cut": ("-d", "-f", "-c"), "sort": ("-k", "-t"),
    "rg": ("-e", "-f", "-m", "-A", "-B", "-C", "-g", "--glob", "-t", "-T", "--type"),
}


def _split_unquoted(cmd: str) -> List[str]:
    """Split a command line on && || ; | and newlines outside quotes."""
    parts, cur, quote, i = [], [], None, 0
    while i < len(cmd):
        c = cmd[i]
        if quote:
            if c == "\\" and quote == '"' and i + 1 < len(cmd):
                cur.append(cmd[i:i + 2])
                i += 2
                continue
            if c == quote:
                quote = None
            cur.append(c)
        elif c in "'\"":
            quote = c
            cur.append(c)
        elif c == "\\" and i + 1 < len(cmd):
            cur.append(cmd[i:i + 2])
            i += 2
            continue
        elif c in ";|&\n":
            parts.append("".join(cur))
            cur = []
            while i + 1 < len(cmd) and cmd[i + 1] in "|&":
                i += 1
        else:
            cur.append(c)
        i += 1
    parts.append("".join(cur))
    return parts


def _segments(cmd: str) -> List[List[str]]:
    import shlex

    cmd = cmd.split("<<", 1)[0]
    out = []
    for seg in _split_unquoted(cmd):
        try:
            toks = shlex.split(seg, comments=True)
        except ValueError:
            continue
        while toks and ("=" in toks[0] and not toks[0].startswith("-")):
            toks = toks[1:]  # VAR=value prefixes
        while toks and toks[0] in ("sudo", "env", "time", "timeout", "nice", "command", "exec", "do", "then"):
            toks = toks[1:]
            if toks and toks[0].isdigit():
                toks = toks[1:]
        if toks:
            out.append(toks)
    return out


def bash_read_targets(cmd: str, cwd: Optional[str] = None, cap: int = 6) -> List[str]:
    """Absolute paths a shell command reads with a plain reader (`cat f`,
    `sed -n 1,9p f`, `rg x f`), resolved against cwd as `cd` moves it. Heredocs
    are dropped and a segment shlex cannot split is skipped: this under-counts
    on purpose."""
    out: List[str] = []
    for toks in _segments(cmd or ""):
        prog = os.path.basename(toks[0])
        if prog == "cd" and len(toks) > 1 and not any(c in toks[1] for c in "*?$`"):
            d = os.path.expanduser(toks[1])
            cwd = os.path.normpath(d if d.startswith("/") else os.path.join(cwd or "/", d))
            continue
        if prog not in _READERS:
            continue
        # The first operand of these is a script or a pattern, not a file.
        skip_first = prog in _PATTERN_FIRST and not any(t in ("-e", "-f", "--regexp") for t in toks[1:])
        value_opts = _VALUE_OPTS.get(prog, ())
        args, skip_value = [], False
        for a in toks[1:]:
            if skip_value:
                skip_value = False
                continue
            if a in value_opts:
                skip_value = True
                continue
            if a.startswith("-"):
                continue
            args.append(a)
        if skip_first and args:
            args = args[1:]
        for a in args:
            if "/" not in a and "." not in a:
                continue
            if any(c in a for c in "*?$`"):
                continue
            p = os.path.expanduser(a)
            if not p.startswith("/"):
                if not cwd:
                    continue
                p = os.path.join(cwd, p)
            out.append(os.path.normpath(p))
            if len(out) >= cap:
                return out
    return out


_SEARCHERS = frozenset(("grep", "egrep", "rg", "ag", "ack"))
_NAME_OPTS = frozenset(("-name", "-iname", "-path", "-ipath", "-regex"))


def bash_search_terms(cmd: str, cap: int = 40) -> List[str]:
    """Words of what a shell command searches for: a grep/rg pattern, a find
    `-name`, a `kg load|search` query. The agent's retrieval intent, stated."""
    words: List[str] = []
    for toks in _segments(cmd or ""):
        prog = os.path.basename(toks[0])
        pats: List[str] = []
        if prog in _SEARCHERS:
            i, first = 1, None
            while i < len(toks):
                t = toks[i]
                if t in ("-e", "--regexp") and i + 1 < len(toks):
                    pats.append(toks[i + 1])
                    i += 2
                    continue
                if t in _VALUE_OPTS.get(prog, ()) or t in _VALUE_OPTS.get("rg", ()):
                    i += 2
                    continue
                if not t.startswith("-") and first is None:
                    first = t
                i += 1
            if not pats and first:
                pats.append(first)
        elif prog == "find":
            pats += [toks[i + 1] for i in range(len(toks) - 1) if toks[i] in _NAME_OPTS]
        elif prog in ("kg", "kg.py") and toks[1:2] and toks[1] in ("load", "search", "query"):
            pats += [t for t in toks[2:] if not t.startswith("-")]
        for pat in pats:
            words += terms(re.sub(r"[\\^$.*+?()\[\]{}|]", " ", pat))
    seen, out = set(), []
    for w in words:
        if w not in seen:
            seen.add(w)
            out.append(w)
            if len(out) >= cap:
                break
    return out


#: Per `gh pr` subcommand, the options that take a value, so a number after one
#: is not the PR's (`--interval 10`). Short flags differ by subcommand: `-s` is
#: `--squash` to merge, `-a` is `--approve` to review; both take no value.
_GH_LONG_VALUES = frozenset(("--body", "--body-file", "--title", "--base", "--head", "--label", "--reviewer",
                             "--assignee", "--milestone", "--project", "--template", "--json", "--jq",
                             "--interval", "--subject", "--match-head-commit", "--author-email", "--add-label",
                             "--remove-label", "--add-reviewer", "--remove-reviewer", "--add-assignee",
                             "--remove-assignee", "--add-project", "--remove-project", "--color"))
_GH_SHORT_VALUES = {
    "create": frozenset(("-t", "-b", "-F", "-B", "-H", "-l", "-r", "-a", "-m", "-p", "-T")),
    "edit": frozenset(("-t", "-b", "-F", "-B", "-m")),
    "merge": frozenset(("-b", "-F", "-t", "-A")),
    "review": frozenset(("-b", "-F")),
    "comment": frozenset(("-b", "-F")),
    "view": frozenset(("-q", "-t")),
    "checks": frozenset(("-i", "-q", "-t")),
    "diff": frozenset(),
    "ready": frozenset(),
}


def bash_actions(cmd: str) -> List[Tuple[str, Optional[str], Optional[str]]]:
    """[(action, pr number or None, repo or None)] for `git push`, and `gh pr
    create|merge|view|checks|diff [n]`. The repo is the one `-R/--repo` or a PR
    URL names (bare name, lower case); None means the session's own. Only these
    actions key the post-bash stage."""
    acts: List[Tuple[str, Optional[str], Optional[str]]] = []
    for toks in _segments(cmd or ""):
        prog = os.path.basename(toks[0])
        if prog == "git":
            rest = [t for t in toks[1:] if not t.startswith("-")]
            # `git -C dir push`: skip an option's value
            i = 1
            while i < len(toks) and toks[i].startswith("-"):
                i += 2 if toks[i] in ("-C", "-c") else 1
            if i < len(toks) and toks[i] == "push":
                acts.append(("push", None, None))
            elif rest[:1] == ["push"]:
                acts.append(("push", None, None))
        elif prog == "gh" and len(toks) >= 3 and toks[1] == "pr" and toks[2] in (
                "create", "merge", "view", "checks", "diff", "ready", "edit", "comment", "review"):
            repo, num, args = None, None, toks[3:]
            takes_value = _GH_LONG_VALUES | _GH_SHORT_VALUES.get(toks[2], frozenset())
            j = 0
            while j < len(args):
                t = args[j]
                if t in ("-R", "--repo") and j + 1 < len(args):
                    repo = args[j + 1]
                elif t.startswith("--repo="):
                    repo = t.split("=", 1)[1]
                elif t.startswith("-R") and len(t) > 2 and not t.startswith("--"):
                    repo = t[2:]
                elif t in takes_value:
                    j += 1  # its value is not the PR number (`--interval 10`)
                elif num is None and t.lstrip("#").isdigit():
                    num = t.lstrip("#")
                j += 2 if t in ("-R", "--repo") else 1
            m = next((PR_URL_RE.search(t) for t in args if PR_URL_RE.search(t)), None)
            if m is not None:
                num, repo = m.group(2), m.group(1)
            repo = repo.rstrip("/").rsplit("/", 1)[-1].lower() if repo else None
            acts.append(("pr-" + toks[2], num, repo or None))
    return acts


def repo_name(git_common_dir: Optional[str]) -> Optional[str]:
    """The GitHub repo name of a checkout's `origin` remote, read from the git
    config file (no process): `git@github.com:broomva/skills.git` -> `skills`."""
    if not git_common_dir:
        return None
    try:
        with open(os.path.join(git_common_dir, "config"), encoding="utf-8") as fh:
            text = fh.read(65536)
    except (OSError, UnicodeDecodeError):
        return None
    m = re.search(r'\[remote "origin"\][^\[]*?url\s*=\s*(\S+)', text)
    if not m:
        return None
    name = m.group(1).rstrip("/").rsplit("/", 1)[-1].rsplit(":", 1)[-1]
    return name[:-4].lower() if name.endswith(".git") else name.lower()


# --------------------------------------------------------------------------
# Text for one event or item, as keys

def text_keys(text: str, cap_terms: int = 0, words: bool = True) -> Dict[str, List[str]]:
    """Keys a free text names: tickets, PR refs, branches and (unless
    `words` is false) words."""
    return {
        "t": ["t:" + t for t in tickets(text)],
        "pr": ["pr:" + r for r in pr_refs(text)],
        "b": ["b:" + b.lower() for b in branches(text)],
        "w": ["w:" + w for w in terms(text, cap_terms)] if words else [],
    }


def add_path(keys: Dict[str, List[str]], rel: Optional[str]) -> None:
    for k in path_keys(rel or ""):
        keys.setdefault(k.split(":", 1)[0], []).append(k)


def empty_keys() -> Dict[str, List[str]]:
    return {c: [] for c in QUERY_CHANNELS}


def unique(seq: Iterable[str]) -> List[str]:
    seen, out = set(), []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out

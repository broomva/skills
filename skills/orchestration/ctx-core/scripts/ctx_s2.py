#!/usr/bin/env python3
"""ctx System 2: the offline cache builder behind the System 1 gate.

    ctx-s1 build [--scope ID] [--no-network] [--ranker bm25] [--json]

Not meant for a synchronous hook path, and nothing here registers it on one:
a tick, a SessionStart async hook or a person runs it, and it can take
seconds. It reads the scope's candidate items, indexes each under the keys it
touches or cites (ctx_keys), ranks them with a pluggable ranker, and writes
one cache per scope:

    ~/.local/state/ctx/<scope>/rank-<build-id>/
        meta.json                     build id, ranker, counts, exclusions, digest
        postings/<bucket>.json        key -> [[item index, score, type code], ...]
        items/<n>.json                item index -> {id, type, claim, source, ...}
    ~/.local/state/ctx/<scope>/rank-current -> rank-<build-id>

The build is written under a temporary name, renamed, and then `rank-current`
is swapped by one atomic rename of a symlink. A reader resolves the link once
and reads only from that build, so it never mixes two builds. The previous
build is kept; older ones are removed.

What an item is (one factual line each, never a bare pointer; the ablations
showed pointer lists are not read):

    spec     docs/specs, docs/plans: the title and the first sentence of the lede
    adr      docs/adrs: the same, as a decision record
    entity   research/entities/**: the entity's core_claim
    memory   a memory rule: its description, quoted (memory files of type `user`
             are facts about a person and are not indexed)
    pr       open and recently updated PRs of the scope's repos whose branch is in
             the repo (no fork PRs): repo#n, state, title (quoted)
             and an as-of date and time; keyed by the files the PR changes
    session  live board rows: branch, cwd and last event, with an as-of time
             (System 1 stops offering session and PR claims once the cache is
             older than 6 h and 24 h)

Exclusions, applied at the source, before anything is indexed:
  - any path under `crm/`, any key naming one, the words of such a path, and a
    PR that touches `crm/` at all;
  - any claim or source that fails ctx-core's guard (credential-shaped text),
    and any word of 32 characters or more;
  - person, persona and org entities: facts about people (and orgs: clients,
    offers, who works where) wait on the personal context engine's bridge rule
    (PCE OQ6; spec workspace#840 §6.4);
  - fork PRs (a public repo takes PR titles from anyone);
  - anything outside the scope: only the scope's repos, their memory dirs and
    their PRs are read, so sri (Stimulus) builds its own cache from its own repo.

The ranker is an interface (`Ranker`): `fit(items)` then `postings()`, a map
from key to scored items. BM25 is the v1 ranker and the default. An ontology
ranker (Kinetic PPR + Jev, spec §6.1) plugs in by returning the same map; the
E1 replay (ctx_s1_eval.py) scores any ranker on the same snapshot, and
nothing but BM25 may be the default until it beats BM25 there (spec §6.6).
"""

from __future__ import annotations

import html as html_mod
import json
import math
import os
import re
import shutil
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import ctx  # noqa: E402
import ctx_keys as K  # noqa: E402

TYPE_CHECKING = False
if TYPE_CHECKING:
    from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

SCHEMA = 1
ITEM_TYPES = ("spec", "adr", "entity", "memory", "pr", "session")
CLAIM_MAX = 220
#: A key held by more than this share of items names nothing in particular.
MAX_DF_SHARE = 0.20
#: Scored items kept per key.
POSTINGS_TOP = 32
#: PRs: open ones, plus any updated within this many days.
PR_RECENT_DAYS = 14
PR_LIMIT = 80
GH_TIMEOUT_S = 25
#: Text read from a document for its word keys.
BODY_CHARS = 2400
#: Person and persona entities are facts about people (spec §6.4: they wait on
#: the personal context engine's bridge rule, PCE OQ6). Org entities are too, at
#: one remove: clients, recruiters, offers, who works where. They wait with them.
EXCLUDED_ENTITY_TYPES = ("person", "persona", "org")
#: Builds kept besides the current one.
KEEP_PREVIOUS = 1


# --------------------------------------------------------------------------
# Items

def make_item(iid: str, itype: str, claim: str, source: str, created: float,
              keys: Dict[str, List[str]], obj: List[str], as_of: Optional[str] = None) -> Dict[str, Any]:
    return {"id": iid, "type": itype, "claim": claim, "source": source, "created": created,
            "as_of": as_of, "keys": keys, "obj": obj}


def _clip_sentence(text: str, cap: int = CLAIM_MAX) -> str:
    t = ctx._flat(re.sub(r"\s+", " ", text)).strip()
    m = re.match(r"(.{20,}?[.!?])(\s|$)", t)
    if m and len(m.group(1)) <= cap:
        t = m.group(1)
    if len(t) > cap:
        cut = t[: cap - 1].rsplit(" ", 1)[0]
        t = cut + "…"
    return t


def _date_of(name: str) -> Optional[float]:
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", name)
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        return None
    return float(ctx._days_from_civil(y, mo, d) * 86400)


def _item_keys(roots: Sequence[Tuple[str, str]], cited_text: str, word_text: str,
               extra_paths: Iterable[str] = ()) -> Dict[str, List[str]]:
    keys = K.text_keys(cited_text, words=False)
    # A crm/ path's words (a client's name in a file name) never become keys.
    keys["w"] = ["w:" + w for w in K.terms(_CRM_PATH.sub(" ", word_text))]
    for p in list(K.cited_paths(cited_text, roots)) + list(extra_paths):
        if "crm/" in ("/" + p.lower()):
            continue
        K.add_path(keys, p)
    return keys


# --------------------------------------------------------------------------
# Sources

_CRM_PATH = re.compile(r"(?<![\w-])(?:[\w@.+~-]+/)*crm/[\w@.+/-]*", re.I)
_META_LINE = re.compile(r"^[\w][\w ./-]{0,24}:\s")
_WIKILINK = re.compile(r"\[\[([^\]\n]{1,120})\]\]")
_HTML_DROP = re.compile(r"<(script|style|svg|nav)\b[^>]*>.*?</\1>", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")


def _html_text(s: str) -> str:
    return html_mod.unescape(_TAG.sub(" ", _HTML_DROP.sub(" ", s)))


def _frontmatter(text: str) -> Dict[str, str]:
    """Top-level `key: value` lines of a YAML front matter block (in a leading
    `---` block, or inside an HTML comment); lists are joined with spaces."""
    m = re.search(r"(?:^|<!--\s*)---\s*\n(.*?)\n---", text[:12000], re.S)
    if not m:
        return {}
    out: Dict[str, str] = {}
    last = None
    for line in m.group(1).splitlines():
        km = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if km:
            last = km.group(1)
            out[last] = km.group(2).strip().strip("\"'")
        elif last and re.match(r"^\s+-\s+", line):
            out[last] = (out.get(last, "") + " " + line.strip()[2:].strip("\"'")).strip()
        elif last and re.match(r"^\s+\w[\w-]*:\s*", line):
            sub = re.match(r"^\s+(\w[\w-]*):\s*(.*)$", line)
            out[last + "." + sub.group(1)] = sub.group(2).strip().strip("\"'")
    return out


def doc_item(path: Path, repo_root: str, roots, itype: str) -> Optional[Dict[str, Any]]:
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")[:400000]
    except OSError:
        return None
    rel = os.path.relpath(str(path), repo_root)
    fm = _frontmatter(raw)
    if path.suffix.lower() in (".html", ".htm"):
        tm = re.search(r"<title[^>]*>(.*?)</title>", raw, re.S | re.I)
        title = html_mod.unescape(_TAG.sub("", tm.group(1))).strip() if tm else ""
        dm = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', raw, re.I)
        lm = re.search(r'class="(?:lede|dek|subtitle|summary|abstract)"[^>]*>(.*?)</(?:p|div)>', raw, re.S | re.I)
        body = _html_text(raw)
        heads = " ".join(_html_text(h) for h in re.findall(r"<h[1-3][^>]*>(.*?)</h[1-3]>", raw, re.S | re.I))
        if dm:
            lede = html_mod.unescape(dm.group(1))
        elif lm:
            lede = _html_text(lm.group(1))
        else:
            after = raw.split("</h1>", 1)[-1]
            lede = ""
            for pm in re.finditer(r"<p[^>]*>(.*?)</p>", after, re.S | re.I):
                cand = re.sub(r"\s+", " ", _html_text(pm.group(1))).strip()
                # Skip byline and metadata paragraphs ("Author: ...", "Status: draft").
                if len(cand) >= 60 and not _META_LINE.match(cand):
                    lede = cand
                    break
    else:
        hm = re.search(r"^#\s+(.+)$", raw, re.M)
        title = fm.get("title") or (hm.group(1).strip() if hm else path.stem)
        body = re.sub(r"^---.*?\n---\n", "", raw, count=1, flags=re.S)
        heads = " ".join(re.findall(r"^#{1,3}\s+(.+)$", body, re.M))
        paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip() and not p.strip().startswith(("#", "---", "```", "|"))]
        lede = re.sub(r"^>\s*", "", paras[0], flags=re.M) if paras else ""
    title = ctx._flat(fm.get("title") or title).strip() or path.stem
    lede_s = _clip_sentence(lede, CLAIM_MAX) if lede else ""
    claim = _clip_sentence("%s: %s" % (title, lede_s) if lede_s and lede_s not in title else title, CLAIM_MAX)
    created = _date_of(path.name) or path.stat().st_mtime
    words = " ".join([title, lede, heads, fm.get("tags", ""), fm.get("slug", ""), body[:BODY_CHARS]])
    cited = " ".join([body[:200000], " ".join(v for v in fm.values())])
    keys = _item_keys(roots, cited, words)
    return make_item("%s:%s" % (itype, rel), itype, claim, rel, created, keys, ["o:" + rel.lower()])


def entity_item(path: Path, repo_root: str, roots) -> Tuple[Optional[Dict[str, Any]], str]:
    rel = os.path.relpath(str(path), repo_root)
    parts = rel.split("/")
    etype = parts[2] if len(parts) > 3 else ""
    if etype in EXCLUDED_ENTITY_TYPES:
        return None, "person"
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")[:200000]
    except OSError:
        return None, "unreadable"
    fm = _frontmatter(raw)
    if fm.get("type", "").lower() in EXCLUDED_ENTITY_TYPES:
        return None, "person"
    claim = fm.get("core_claim", "").strip()
    if not claim:
        return None, "no-claim"
    slug = rel[len("research/entities/"):-3] if rel.startswith("research/entities/") else path.stem
    body = re.sub(r"^---.*?\n---\n", "", raw, count=1, flags=re.S)
    created = _date_of(fm.get("created", "")) or path.stat().st_mtime
    words = " ".join([fm.get("title", ""), claim, fm.get("tags", ""), slug.replace("-", " "), body[:BODY_CHARS]])
    keys = _item_keys(roots, raw, words)
    obj = ["o:" + rel.lower(), "kg:" + slug.lower(), "kg:" + slug.rsplit("/", 1)[-1].lower()]
    it = make_item("entity:" + slug, "entity", _clip_sentence(claim, CLAIM_MAX), rel, created, keys, obj)
    it["wikilinks"] = sorted({w.strip().lower().split("|")[0] for w in _WIKILINK.findall(raw)})[:200]
    return it, ""


def memory_item(path: Path, roots) -> Tuple[Optional[Dict[str, Any]], str]:
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")[:100000]
    except OSError:
        return None, "unreadable"
    fm = _frontmatter(raw)
    mtype = (fm.get("metadata.type") or fm.get("type") or "").lower()
    if mtype == "user":
        return None, "person"
    desc = fm.get("description", "").strip()
    if not desc:
        return None, "no-claim"
    name = fm.get("name") or path.stem
    body = re.sub(r"^---.*?\n---\n", "", raw, count=1, flags=re.S)
    src = "~" + str(path)[len(K.home()):] if str(path).startswith(K.home() + "/") else str(path)
    try:
        created = path.stat().st_birthtime  # type: ignore[attr-defined]
    except AttributeError:
        created = path.stat().st_mtime
    claim = 'Memory rule %s records: "%s"' % (name, _clip_sentence(desc, CLAIM_MAX - 30 - len(name)))
    words = " ".join([name.replace("-", " "), desc, body[:BODY_CHARS]])
    keys = _item_keys(roots, body, words)
    return make_item("memory:" + path.name, "memory", claim, src, created, keys,
                     ["m:" + path.name.lower()]), ""


def gh_prs(repo_root: str, slug: str, now: float, runner=None) -> Optional[List[Dict[str, Any]]]:
    """Open PRs, and PRs updated in the last PR_RECENT_DAYS days, via gh. System 2
    only: a network call. Returns None when gh fails, which the build counts
    (`pr-fetch-failed`) rather than reading as "no PRs"."""
    import subprocess

    fields = "number,title,state,headRefName,files,updatedAt,createdAt,isCrossRepository"
    argv = ["gh", "pr", "list", "--repo", slug, "--state", "all", "--limit", str(PR_LIMIT), "--json", fields]
    try:
        if runner is not None:
            out = runner(argv)
        else:
            out = subprocess.run(argv, capture_output=True, text=True, timeout=GH_TIMEOUT_S,
                                 cwd=repo_root).stdout
        rows = json.loads(out)
    except Exception:
        return None
    if not isinstance(rows, list):
        return None
    keep = []
    cut = now - PR_RECENT_DAYS * 86400
    for r in rows:
        try:
            upd = ctx.parse_ts(r["updatedAt"][:19] + ".000Z")
        except Exception:
            continue
        if r.get("state") == "OPEN" or upd >= cut:
            keep.append(r)
    return keep


def pr_item(r: Dict[str, Any], name: str, now: float) -> Tuple[Optional[Dict[str, Any]], str]:
    """(item, "") or (None, why): a PR from a fork (anyone's), or one that
    touches crm/ at all, is not indexed (its title would be the claim)."""
    if r.get("isCrossRepository") is not False:
        return None, "untrusted-author"
    paths = [f.get("path") for f in (r.get("files") or []) if isinstance(f, dict) and isinstance(f.get("path"), str)]
    if any("crm/" in "/" + p.lower() for p in paths) or "crm" in K.terms(str(r.get("title") or "")):
        return None, "crm"
    n = int(r["number"])
    state = str(r.get("state") or "?").lower()
    title = ctx._flat(r.get("title") or "")
    asof = time.strftime("%Y-%m-%d %H:%MZ", time.gmtime(now))
    claim = '%s#%d (%s as of %s): "%s"' % (name, n, state, asof, _clip_sentence(title, 150))
    keys = K.text_keys(title)
    keys["pr"].append("pr:%s#%d" % (name, n))
    br = (r.get("headRefName") or "").lower()
    if br:
        keys["b"].append("b:" + br)
    keys["w"] += ["w:" + w for w in K.terms(br.replace("/", " ").replace("-", " "))]
    for p in paths[:300]:
        K.add_path(keys, p)
    try:
        created = ctx.parse_ts(r["createdAt"][:19] + ".000Z")
    except Exception:
        created = now
    return make_item("pr:%s#%d" % (name, n), "pr", claim, "%s#%d" % (name, n), created, keys,
                     ["o:pr:%s#%d" % (name, n)], as_of=asof), ""


def session_items(scope, now: float) -> List[Dict[str, Any]]:
    try:
        board, _ = ctx.read_board(scope, fold_cap=None)
    except Exception:
        return []
    out = []
    for r in board.get("sessions", {}).values():
        if not ctx.is_live(r, now):
            continue
        sid = str(r.get("session_id") or "")
        br = (r.get("branch") or "").lower()
        if not sid or not br or br.startswith("detached@"):
            continue
        asof = time.strftime("%Y-%m-%d %H:%MZ", time.gmtime(now))
        claim = "Session %s is live on branch %s in %s; last event %s ago as of %s." % (
            sid[:8], ctx._clip(r.get("branch"), 80), ctx._tilde(r.get("cwd")),
            ctx._age(now - ctx.parse_ts(r["last_ts"])), asof)
        keys = K.empty_keys()
        keys["b"].append("b:" + br)
        for p in (r.get("claims") or [])[:100]:  # phase 2 writes path claims; phase 1 has none
            if isinstance(p, str):
                K.add_path(keys, p)
        out.append(make_item("session:" + sid[:8], "session", claim, "ctx board", ctx.parse_ts(r["last_ts"]),
                             keys, ["o:session:" + sid[:8]], as_of=asof))
    return out


def scope_roots(scope_id: str) -> List[Tuple[str, str]]:
    """[(absolute repo root, GitHub repo name)] for a scope, longest root first."""
    text = ctx.config_path().read_text(encoding="utf-8")
    roots = []
    for raw in ctx.parse_scopes(text).get(scope_id, []):
        p = os.path.realpath(os.path.expanduser(raw))
        if os.path.basename(p) == ".git":
            p = os.path.dirname(p)
        if not os.path.isdir(p):
            continue
        name = K.repo_name(ctx._entry_common_dir(p)) or os.path.basename(p).lower()
        roots.append((p, name))
    roots.sort(key=lambda r: -len(r[0]))
    return roots


def memory_dirs(roots: Sequence[Tuple[str, str]]) -> List[Path]:
    base = Path(K.home()) / ".claude" / "projects"
    out = []
    for root, _ in roots:
        d = base / re.sub(r"[^A-Za-z0-9]", "-", root) / "memory"
        if d.is_dir():
            out.append(d)
    return out


def github_slug(root: str) -> Optional[str]:
    try:
        with open(os.path.join(ctx._entry_common_dir(root), "config"), encoding="utf-8") as fh:
            text = fh.read(65536)
    except OSError:
        return None
    m = re.search(r'\[remote "origin"\][^\[]*?url\s*=\s*\S*github\.com[:/]([\w.-]+/[\w.-]+?)(?:\.git)?\s', text)
    return m.group(1) if m else None


def gather(scope, network: bool = True, now: Optional[float] = None,
           gh_runner=None) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Every candidate item of a scope, and a count of what was excluded, by reason."""
    now = time.time() if now is None else now
    roots = scope_roots(scope.id)
    items: List[Dict[str, Any]] = []
    excluded: Counter = Counter()

    def admit(it: Optional[Dict[str, Any]], why: str = "", root: str = "", path: Optional[Path] = None) -> None:
        if it is None:
            if why:
                excluded[why] += 1
            return
        low = "/" + (it["source"] or "").lower()
        if "/crm/" in low or low.startswith("/crm/"):
            excluded["crm"] += 1
            return
        if not ctx.guard_ok(it["claim"]) or not ctx.guard_ok(it["source"]):
            excluded["secret-shaped"] += 1
            return
        it["root"] = root  # the repo it came from
        if path is not None:
            try:
                it["mtime"] = path.stat().st_mtime  # E1 flags hits on items edited after the event
            except OSError:
                pass
        items.append(it)

    for root, name in roots:
        base = Path(root)
        for sub, itype in (("docs/specs", "spec"), ("docs/plans", "spec"), ("docs/adrs", "adr")):
            d = base / sub
            if not d.is_dir():
                continue
            for p in sorted(d.iterdir()):
                if p.suffix.lower() in (".html", ".htm", ".md") and p.is_file():
                    admit(doc_item(p, root, roots, itype), "unreadable", name, p)
        ents = base / "research" / "entities"
        if ents.is_dir():
            for p in sorted(ents.rglob("*.md")):
                if p.name.startswith("_") or "/crm/" in str(p):
                    continue
                it, why = entity_item(p, root, roots)
                admit(it, why, name, p)
        if network:
            slug = github_slug(root)
            if slug:
                rows = gh_prs(root, slug, now, gh_runner)
                if rows is None:
                    excluded["pr-fetch-failed"] += 1
                for r in rows or []:
                    it, why = pr_item(r, name, now)
                    admit(it, why, name)
    for d in memory_dirs(roots):
        for p in sorted(d.glob("*.md")):
            if p.name.upper() == "MEMORY.MD":
                continue
            it, why = memory_item(p, roots)
            admit(it, why, "memory", p)
    for it in session_items(scope, now):
        admit(it, "", "board")
    # One id, one item: the first root (longest) wins a duplicate.
    seen, uniq = set(), []
    for it in items:
        if it["id"] not in seen:
            seen.add(it["id"])
            uniq.append(it)
        else:
            excluded["duplicate"] += 1
    uniq.sort(key=lambda it: it["id"])
    link_items(uniq)
    return uniq, dict(excluded)


def link_items(items: List[Dict[str, Any]]) -> None:
    """item["links"]: indices of the items an item links to, by an entity
    wikilink ([[slug]] or [[type/slug]]) or by citing another item's file. The
    graph a traversal ranker walks; BM25 does not read it."""
    by_obj: Dict[str, int] = {}
    for idx, it in enumerate(items):
        for ob in it.get("obj") or []:
            by_obj.setdefault(ob, idx)
    for idx, it in enumerate(items):
        out = set()
        for w in it.pop("wikilinks", []) or []:
            j = by_obj.get("kg:" + w)
            if j is not None:
                out.add(j)
        for k in (it.get("keys") or {}).get("p", []):
            j = by_obj.get("o:" + k[2:])
            if j is not None:
                out.add(j)
        out.discard(idx)
        it["links"] = sorted(out)


# --------------------------------------------------------------------------
# Rankers

class Ranker:
    """The seam. `fit` sees every item's keys; `postings` returns, per key, the
    items it ranks for that key with a non-negative score, best first. System 1
    sums a candidate's scores over the event's keys (times a per-channel weight)
    and compares the sum with the stage's floor."""

    name = "base"
    version = 0
    params: Dict[str, Any] = {}

    def fit(self, items: Sequence[Dict[str, Any]]) -> None:
        raise NotImplementedError

    def postings(self) -> Dict[str, List[Tuple[int, float]]]:
        raise NotImplementedError


def key_counts(item: Dict[str, Any]) -> Dict[str, Dict[str, int]]:
    """{channel: {key: tf}}; accepts lists (tf by repetition) or ready counts."""
    out = {}
    for ch, ks in (item.get("keys") or {}).items():
        out[ch] = dict(ks) if isinstance(ks, dict) else dict(Counter(ks))
    return out


class BM25Ranker(Ranker):
    """Okapi BM25 per channel: each channel (paths, dirs, words, ...) is a field
    with its own length normalisation, and a key's score for an item is its BM25
    term weight in that field. Scores are additive across keys, so System 1 can
    sum them for a multi-key event without the corpus at hand."""

    name = "bm25"
    version = 1

    def __init__(self, k1: float = 1.2, b: float = 0.75, top: int = POSTINGS_TOP,
                 max_df_share: float = MAX_DF_SHARE, field_b: Optional[Dict[str, float]] = None):
        # Path fields barely vary in length meaningfully; words do.
        self.k1, self.b, self.top, self.max_df_share = k1, b, top, max_df_share
        self.field_b = dict({"p": 0.3, "d": 0.5, "f": 0.3, "b": 0.0, "pr": 0.0, "t": 0.3}, **(field_b or {}))
        self.params = {"k1": k1, "b": b, "top": top, "max_df_share": max_df_share, "field_b": self.field_b}
        self._post: Dict[str, List[Tuple[int, float]]] = {}

    def fit(self, items: Sequence[Dict[str, Any]]) -> None:
        n = len(items)
        counts = [key_counts(it) for it in items]
        post: Dict[str, List[Tuple[int, float]]] = {}
        for ch in K.CHANNELS:
            # An item may carry its field lengths ("L"): a pruned snapshot item
            # keeps them, so BM25's length normalisation matches the live build.
            lens = [int((it.get("L") or {}).get(ch, sum(c.get(ch, {}).values())))
                    for it, c in zip(items, counts)]
            nz = [x for x in lens if x]
            avg = (sum(nz) / len(nz)) if nz else 1.0
            df: Counter = Counter()
            for c in counts:
                df.update(c.get(ch, {}).keys())
            b = self.field_b.get(ch, self.b)
            limit = max(3, int(self.max_df_share * n))
            for idx, c in enumerate(counts):
                for key, tf in c.get(ch, {}).items():
                    d = df[key]
                    if d > limit:
                        continue
                    idf = math.log(1.0 + (n - d + 0.5) / (d + 0.5))
                    norm = tf * (self.k1 + 1) / (tf + self.k1 * (1 - b + b * lens[idx] / avg))
                    post.setdefault(key, []).append((idx, idf * norm))
        for key, lst in post.items():
            lst.sort(key=lambda x: (-x[1], x[0]))
            del lst[self.top:]
        self._post = post

    def postings(self) -> Dict[str, List[Tuple[int, float]]]:
        return self._post


RANKERS = {"bm25": BM25Ranker}


def get_ranker(name: str, **params) -> Ranker:
    if name == "ppr":
        import ctx_s2_ppr  # the ontology-shaped prototype: an eval arm, never the default

        return ctx_s2_ppr.PPRRanker(**params)
    return RANKERS[name](**params)


# --------------------------------------------------------------------------
# The cache: sharded, written under a temporary name, swapped atomically

def _dump(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _write(path: Path, data: bytes) -> None:
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view):]
    finally:
        os.close(fd)


def write_cache(store: Path, items: Sequence[Dict[str, Any]], ranker: Ranker,
                extra_meta: Optional[Dict[str, Any]] = None, now: Optional[float] = None) -> Path:
    """Write one build and make it current. Returns the build directory."""
    import hashlib

    now = time.time() if now is None else now
    types = sorted({it["type"] for it in items} | set(ITEM_TYPES))
    tcode = {t: i for i, t in enumerate(types)}
    post = ranker.postings()
    buckets: Dict[str, Dict[str, List[List[Any]]]] = {}
    for key in sorted(post):
        buckets.setdefault(K.bucket(key), {})[key] = [
            [idx, round(score, 5), tcode[items[idx]["type"]]] for idx, score in post[key]]
    files: Dict[str, Dict[str, Any]] = {}
    for idx, it in enumerate(items):
        rec = {k: it[k] for k in ("id", "type", "claim", "source", "as_of", "obj", "created") if k in it}
        rec["len"] = len(it.get("claim") or "")
        files.setdefault(K.item_file(idx), {})[str(idx)] = rec
    digest = hashlib.sha256()
    for name in sorted(buckets):
        digest.update(name.encode() + _dump(buckets[name]))
    for name in sorted(files):
        digest.update(name.encode() + _dump(files[name]))
    build_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now)) + "-" + digest.hexdigest()[:10]
    store.mkdir(parents=True, exist_ok=True, mode=0o700)
    final = store / (K.CACHE_PREFIX + build_id)
    tmp = store / (".%s%s.%d.tmp" % (K.CACHE_PREFIX, build_id, os.getpid()))
    (tmp / "postings").mkdir(parents=True, mode=0o700)
    (tmp / "items").mkdir(mode=0o700)
    try:
        for name, obj in buckets.items():
            _write(tmp / "postings" / (name + ".json"), _dump(obj))
        for name, obj in files.items():
            _write(tmp / "items" / (name + ".json"), _dump(obj))
        meta = {"schema": SCHEMA, "build_id": build_id, "built_at": ctx.now_ts(now),
                "ranker": {"name": ranker.name, "version": ranker.version, "params": ranker.params},
                "items": len(items), "keys": len(post), "types": types,
                "by_type": dict(Counter(it["type"] for it in items)), "digest": digest.hexdigest()}
        meta.update(extra_meta or {})
        _write(tmp / "meta.json", _dump(meta))
        if final.exists():
            shutil.rmtree(str(tmp))
        else:
            os.rename(str(tmp), str(final))
    except BaseException:
        shutil.rmtree(str(tmp), ignore_errors=True)
        raise
    _swap_link(store, final.name)
    _gc(store, final.name)
    return final


def _swap_link(store: Path, target: str) -> None:
    """Point rank-current at a complete build: a new symlink, renamed over."""
    link_tmp = store / (".%s.%d.tmp" % (K.CACHE_LINK, os.getpid()))
    try:
        os.unlink(str(link_tmp))
    except FileNotFoundError:
        pass
    os.symlink(target, str(link_tmp))
    os.replace(str(link_tmp), str(store / K.CACHE_LINK))


_BUILD_RE = re.compile(r"^rank-\d{8}T\d{6}Z-[0-9a-f]{10}$")


def _gc(store: Path, current: str) -> None:
    """Remove builds older than the KEEP_PREVIOUS before the current one. Only
    real directories named like a build are touched; a symlink never is."""
    builds = sorted(p.name for p in store.iterdir()
                    if _BUILD_RE.match(p.name) and p.is_dir() and not p.is_symlink())
    keep = set(builds[-(KEEP_PREVIOUS + 1):]) | {current}
    for name in builds:
        if name not in keep:
            shutil.rmtree(str(store / name), ignore_errors=True)
    for p in store.iterdir():  # temp dirs of a build that died more than an hour ago
        if p.name.startswith(".rank-") and p.name.endswith(".tmp") and p.is_dir() and not p.is_symlink():
            try:
                if time.time() - p.stat().st_mtime > 3600:
                    shutil.rmtree(str(p), ignore_errors=True)
            except OSError:
                pass


def gc_sessions(store: Path, days: float = 7.0) -> int:
    """Drop System 1 per-session state untouched for `days`, each session
    under its own lock, as a hook takes it: a session's lock is touched on
    every use (ctx_s1.open_state), and state and lock are removed only while
    this process holds the lock and both are still old, so a session resumed
    after a week does not lose its state or its lock to housekeeping (a hook
    that opened the lock just before the unlink sees the inode change and
    abstains). Returns the files removed."""
    import fcntl

    d = store / "s1-sessions"
    if not d.is_dir():
        return 0
    cut = time.time() - days * 86400
    n = 0
    stems = sorted({p.name[:-len(p.suffix)] for p in d.iterdir() if p.suffix in (".json", ".lock")})
    for stem in stems:
        state, lock = d / (stem + ".json"), d / (stem + ".lock")
        try:
            if any(p.exists() and (p.is_symlink() or p.stat().st_mtime >= cut) for p in (state, lock)):
                continue
            fd = os.open(str(lock), os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        except OSError:
            continue
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if os.fstat(fd).st_mtime >= cut or (state.exists() and state.stat().st_mtime >= cut):
                continue  # used since we looked
            for p in (state, lock):
                if p.exists():
                    p.unlink()
                    n += 1
        except OSError:
            pass
        finally:
            os.close(fd)
    for p in d.glob(".*.tmp"):  # a state write killed before its rename
        try:
            if p.is_file() and not p.is_symlink() and p.stat().st_mtime < cut:
                p.unlink()
                n += 1
        except OSError:
            pass
    return n


def build(scope, network: bool = True, ranker_name: str = "bm25", now: Optional[float] = None,
          gh_runner=None) -> Dict[str, Any]:
    t0 = time.monotonic()
    items, excluded = gather(scope, network=network, now=now, gh_runner=gh_runner)
    ranker = get_ranker(ranker_name)
    ranker.fit(items)
    final = write_cache(scope.store, items, ranker, {"scope": scope.id, "excluded": excluded,
                                                     "network": network}, now=now)
    gc_sessions(scope.store)
    meta = json.loads((final / "meta.json").read_text())
    meta["seconds"] = round(time.monotonic() - t0, 2)
    return meta


# --------------------------------------------------------------------------
# CLI (dispatched from ctx_s1_cli.py: `ctx-s1 build ...`)

def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="ctx-s1")
    ap.add_argument("-C", dest="cwd", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="index the scope's items and write the System 1 cache")
    b.add_argument("--scope", help="scope id (default: the scope of the current directory)")
    b.add_argument("--no-network", action="store_true", help="skip PRs (gh)")
    b.add_argument("--ranker", default="bm25", choices=["bm25", "ppr"])
    b.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    cwd = os.path.abspath(args.cwd or os.getcwd())
    if args.scope:
        if not ctx.SCOPE_ID_RE.match(args.scope):
            print("invalid scope id", file=sys.stderr)
            return 2
        scope = ctx.Scope(id=args.scope, store=ctx.state_root() / args.scope, where=None)
        try:
            known = ctx.parse_scopes(ctx.config_path().read_text(encoding="utf-8"))
        except (OSError, ctx.ConfigError) as exc:
            print("scopes.yaml: %s" % exc, file=sys.stderr)
            return 1
        if args.scope not in known:
            print("scope %s is not in %s" % (args.scope, ctx.config_path()), file=sys.stderr)
            return 1
    else:
        scope = ctx.resolve_scope(cwd)
        if scope is None:
            return 0  # an unscoped repo is a silent no-op, as everywhere in ctx
    if args.ranker != "bm25" and not os.environ.get("CTX_S2_ALLOW_EVAL_RANKER"):
        print("only bm25 may build the live cache (spec §6.6); other rankers are E1 arms",
              file=sys.stderr)
        return 2
    meta = build(scope, network=not args.no_network, ranker_name=args.ranker)
    if args.json:
        print(json.dumps(meta, indent=2, sort_keys=True))
    else:
        print("scope %s: %d items, %d keys, ranker %s v%d, build %s (%.1fs)" % (
            meta["scope"], meta["items"], meta["keys"], meta["ranker"]["name"], meta["ranker"]["version"],
            meta["build_id"], meta["seconds"]))
        print("  by type: " + ", ".join("%s %d" % kv for kv in sorted(meta["by_type"].items())))
        if meta.get("excluded"):
            print("  excluded: " + ", ".join("%s %d" % kv for kv in sorted(meta["excluded"].items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())

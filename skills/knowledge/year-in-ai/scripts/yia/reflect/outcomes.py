"""The outcome join: what each episode led to. Code only, every source optional.

Sources, each reported as available or absent with a reason, never silently:

* ``harness``  pull requests the harness itself linked to the session, with
  their merge state (T3 keeps a snapshot); needs nothing outside the stores.
* ``github``   merged pull requests the owner authored in the window, listed
  with ``gh`` (one search per month; only the owner's own PR list is fetched,
  no session text is sent anywhere). Falls back to ``git``.
* ``git``      merged pull requests found in local repositories' first-parent
  history (``(#123)`` squash subjects and merge commits), when ``gh`` is absent.
* ``linear``   ticket states from an optional JSON export (``--linear-json``,
  a list of ``{"identifier", "state", "title"}``). Without it tickets are
  linked by mention only.
* ``kg``       knowledge-graph entities (markdown with ``created:`` front
  matter) that cite an episode's ticket or URL, or were created during the
  episode and are named in it.

An episode links to a merged PR when it mentions the PR's URL, the harness
recorded it as merged, its branch is the PR's head branch, or one of its
tickets is in the PR's title or branch and the merge is within three weeks.
"""

from __future__ import annotations

import collections
import datetime as _dt
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from ..ledger.sources import SourceReport, list_files, present, read_text
from . import tickets_in

GENERIC_BRANCHES = {"main", "master", "dev", "develop", "trunk", "HEAD", "staging", "production", "release"}
#: How long after an episode a PR merge still counts as its outcome.
MERGE_WINDOW_DAYS = 21
_URL = re.compile(r"https?://[^\s)\]>\"'`]+")

Runner = Callable[[List[str]], Tuple[bool, str]]


def run(cmd: List[str], timeout: float = 120.0) -> Tuple[bool, str]:
    """Run a command; ``(ok, stdout or the reason it failed)``."""
    if not shutil.which(cmd[0]):
        return False, f"{cmd[0]} not found"
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"{cmd[0]} failed: {exc}"
    if done.returncode != 0:
        return False, (done.stderr or done.stdout or f"exit {done.returncode}").strip().splitlines()[-1][:200]
    return True, done.stdout


def _day(iso: Optional[str]) -> Optional[_dt.date]:
    if not iso:
        return None
    try:
        return _dt.date.fromisoformat(iso[:10])
    except ValueError:
        return None


def _months(year: int):
    for m in range(1, 13):
        start = _dt.date(year, m, 1)
        end = _dt.date(year + (m == 12), m % 12 + 1, 1) - _dt.timedelta(days=1)
        yield start.isoformat(), end.isoformat()


_GH_QUERY = """query($q: String!, $after: String) {
  search(query: $q, type: ISSUE, first: 100, after: $after) {
    pageInfo { hasNextPage endCursor }
    nodes { ... on PullRequest { url number title mergedAt headRefName repository { nameWithOwner } } }
  }
}"""


def github_prs(year: int, runner: Runner = run) -> Tuple[dict, List[dict]]:
    """Merged PRs authored by the ``gh`` user in ``year``, one search per month."""
    ok, why = runner(["gh", "auth", "status"])
    if not ok:
        return {"available": False, "reason": f"gh unavailable: {why}"}, []
    prs: List[dict] = []
    for start, end in _months(year):
        after = None
        while True:
            cmd = ["gh", "api", "graphql", "-f", f"query={_GH_QUERY}",
                   "-f", f"q=is:pr author:@me is:merged merged:{start}..{end}"]
            if after:
                cmd += ["-f", f"after={after}"]
            ok, out = runner(cmd)
            if not ok:
                return {"available": False, "reason": f"gh search failed: {out}"}, []
            try:
                data = json.loads(out)["data"]["search"]
            except (ValueError, KeyError, TypeError):
                return {"available": False, "reason": "gh returned an unexpected shape"}, []
            for node in data.get("nodes") or []:
                if node and node.get("url"):
                    prs.append({"url": node["url"], "number": node.get("number"), "title": node.get("title") or "",
                                "merged_at": node.get("mergedAt"), "branch": node.get("headRefName"),
                                "repo": (node.get("repository") or {}).get("nameWithOwner"), "via_source": "github"})
            if not data["pageInfo"]["hasNextPage"]:
                break
            after = data["pageInfo"]["endCursor"]
    return {"available": True, "reason": None, "count": len(prs)}, prs


_SQUASH = re.compile(r"\(#([0-9]+)\)\s*$")
_MERGE = re.compile(r"^Merge pull request #([0-9]+) from [^/\s]+/(\S+)")


def git_prs(repo_dirs: List[str], year: int, runner: Runner = run) -> Tuple[dict, List[dict]]:
    """Merged PRs from local first-parent history, for repositories that still exist here."""
    found, _blocked = present(repo_dirs, "dir")
    if not found:
        return {"available": False, "reason": "no local repository from the episodes exists on this machine"}, []
    prs: List[dict] = []
    for repo in found:
        ok, remote = runner(["git", "-C", str(repo), "remote", "get-url", "origin"])
        slug = None
        if ok:
            match = re.search(r"github\.com[:/]([\w.-]+/[\w.-]+?)(?:\.git)?\s*$", remote)
            slug = match.group(1) if match else None
        ok, out = runner(["git", "-C", str(repo), "log", "--first-parent", f"--since={year}-01-01",
                          f"--until={year + 1}-01-01", "--format=%cI%x1f%s"])
        if not ok or not slug:
            continue
        for line in out.splitlines():
            when, _, subject = line.partition("\x1f")
            squash, merge = _SQUASH.search(subject), _MERGE.match(subject)
            number = (squash or merge).group(1) if (squash or merge) else None
            if number:
                prs.append({"url": f"https://github.com/{slug}/pull/{number}", "number": int(number),
                            "title": subject, "merged_at": when, "branch": merge.group(2) if merge else None,
                            "repo": slug, "via_source": "git"})
    return {"available": bool(prs), "reason": None if prs else "no merged PRs in local history",
            "count": len(prs)}, prs


def linear_states(path: Optional[str]) -> Tuple[dict, Dict[str, dict]]:
    if not path:
        return {"available": False, "reason": "no Linear export given (--linear-json); tickets linked by mention only"}, {}
    report = SourceReport("linear", True)
    found, _ = present([Path(path).expanduser()], "file")
    body = read_text(found[0], report) if found else None
    if body is None:
        return {"available": False, "reason": f"Linear export {path} not readable"}, {}
    try:
        data = json.loads(body)
    except ValueError:
        return {"available": False, "reason": f"Linear export {path} is not JSON"}, {}
    out = {i["identifier"]: {"state": i.get("state"), "title": i.get("title")}
           for i in data if isinstance(i, dict) and isinstance(i.get("identifier"), str)}
    return {"available": True, "reason": None, "count": len(out)}, out


def kg_entities(root: Optional[str]) -> Tuple[dict, List[dict]]:
    if not root:
        return {"available": False, "reason": "no knowledge-graph directory given (--kg or config kg_entities)"}, []
    found, blocked = present([Path(root).expanduser()], "dir")
    if not found:
        why = "not accessible" if blocked else "does not exist"
        return {"available": False, "reason": f"knowledge-graph directory {root} {why}"}, []
    report = SourceReport("kg", True, root=str(found[0]))
    entities = []
    for path in list_files(found[0], report):
        if path.suffix != ".md" or path.name.startswith("_"):
            continue
        body = read_text(path, report)
        if body is None:
            continue
        created = re.search(r"^created:\s*\"?(\d{4}-\d{2}-\d{2})", body, re.M)
        entities.append({
            "slug": path.stem, "type": path.parent.name, "created": created.group(1) if created else None,
            "tickets": sorted(tickets_in(body)), "urls": sorted({u.rstrip(".,;") for u in _URL.findall(body)}),
        })
    status = {"available": True, "reason": report.reason if report.skipped else None, "count": len(entities)}
    return status, entities


_REMOTE = re.compile(r"github\.com[:/]([\w.-]+/[\w.-]+?)(?:\.git)?\s*$")


def remote_slug(directory: Optional[str], runner: "Runner" = None) -> Optional[str]:
    """``owner/name`` of the git remote ``origin`` of ``directory``, or None when it cannot be known."""
    if not directory:
        return None
    found, _blocked = present([directory], "dir")
    if not found:
        return None
    ok, remote = (runner or run)(["git", "-C", str(found[0]), "remote", "get-url", "origin"])
    match = _REMOTE.search(remote) if ok else None
    return match.group(1).lower() if match else None


def _same_repo(episode: dict, pr: dict, repo_of) -> bool:
    """Is ``pr`` from the repository the episode ran in? Only an exact ``owner/name``
    match of the episode directory's git remote counts; unknown counts as no.
    A directory or path component that merely shares the repository's name is
    not identity."""
    want = (pr.get("repo") or "").lower()
    return bool(want) and repo_of(episode.get("cwd")) == want


def _within(merged_at: Optional[str], first: str, last: str, before: int = 1) -> bool:
    merged, start, end = _day(merged_at), _day(first), _day(last)
    if not (merged and start and end):
        return False
    return start - _dt.timedelta(days=before) <= merged <= end + _dt.timedelta(days=MERGE_WINDOW_DAYS)


def join(episodes: List[dict], sources: Dict[str, dict], prs: List[dict], tickets_state: Dict[str, dict],
         entities: List[dict], repo_of=None) -> dict:
    """Link every episode to its outcomes. ``sources`` is reported as given.

    ``repo_of(cwd)`` gives a directory's ``owner/name`` (default: its git remote,
    cached per directory).
    """
    if repo_of is None:
        cache: Dict[Optional[str], Optional[str]] = {}

        def repo_of(cwd):
            if cwd not in cache:
                cache[cwd] = remote_slug(cwd)
            return cache[cwd]
    index = {p["url"]: p for p in prs}
    by_branch: Dict[str, List[dict]] = collections.defaultdict(list)
    by_ticket: Dict[str, List[dict]] = collections.defaultdict(list)
    for p in prs:
        if p.get("branch") and p["branch"] not in GENERIC_BRANCHES:
            by_branch[p["branch"]].append(p)
        named = tickets_in(p.get("title") or "") | tickets_in((p.get("branch") or "").upper())
        for t in named:
            by_ticket[t].append(p)
    ent_by_ticket: Dict[str, List[dict]] = collections.defaultdict(list)
    ent_by_url: Dict[str, List[dict]] = collections.defaultdict(list)
    for ent in entities:
        for t in ent["tickets"]:
            ent_by_ticket[t].append(ent)
        for u in ent["urls"]:
            ent_by_url[u].append(ent)

    out: Dict[str, dict] = {}
    for e in episodes:
        links: Dict[str, dict] = {}

        def link(p: dict, via: str) -> None:
            entry = links.setdefault(p["url"], {"url": p["url"], "title": p.get("title"),
                                                "merged_at": p.get("merged_at"), "via": []})
            if via not in entry["via"]:
                entry["via"].append(via)

        for url in e["prs"]:
            if url in index:
                link(index[url], "mention")
        for url, info in (e.get("harness_prs") or {}).items():
            if (info or {}).get("state") == "merged":
                link(index.get(url) or {"url": url, "title": (info or {}).get("title")}, "harness")
        branch = e.get("branch")
        if branch and branch not in GENERIC_BRANCHES:
            for p in by_branch.get(branch, []):
                if _within(p.get("merged_at"), e["first"], e["last"]):
                    # A branch name is the session's own outcome only in its own
                    # repository; elsewhere the same name is a coincidence.
                    link(p, "branch" if _same_repo(e, p, repo_of) else "branch-name")
        for t in e["tickets"]:
            for p in by_ticket.get(t, []):
                if _within(p.get("merged_at"), e["first"], e["last"], before=2):
                    link(p, "ticket")
        shipped = {t: sorted(p["url"] for p in by_ticket.get(t, []) if p["url"] in links) for t in e["tickets"]}
        tickets = [{"id": t, "merged_prs": shipped[t], "state": (tickets_state.get(t) or {}).get("state")}
                   for t in e["tickets"]]

        text = "\n".join([p["text"] for p in e["prompts"]] + [r["text"] for r in e["replies"]])
        urls = {u.rstrip(".,;") for u in _URL.findall(text)}
        days = set(e["days"])
        kg: Dict[str, dict] = {}
        for t in e["tickets"]:
            for ent in ent_by_ticket.get(t, []):
                kg.setdefault(ent["slug"], {"slug": ent["slug"], "type": ent["type"], "via": "ticket"})
        for u in urls:
            for ent in ent_by_url.get(u, []):
                kg.setdefault(ent["slug"], {"slug": ent["slug"], "type": ent["type"], "via": "url"})
        for ent in entities:
            if ent["created"] in days and ent["slug"] in text and ent["slug"] not in kg:
                kg[ent["slug"]] = {"slug": ent["slug"], "type": ent["type"], "via": "created"}
        out[e["id"]] = {"merged_prs": sorted(links.values(), key=lambda x: x["url"]), "tickets": tickets,
                        "kg": sorted(kg.values(), key=lambda x: x["slug"])}
    return {"sources": sources, "episodes": out}


def repo_dirs(episodes: List[dict]) -> List[str]:
    """Local repository roots worth asking ``git`` about: episode directories, worktree suffixes removed."""
    roots = set()
    for e in episodes:
        cwd = e.get("cwd")
        if not cwd:
            continue
        cwd = re.sub(r"/\.(claude|codex|conductor)/worktrees/.*$", "", cwd)
        roots.add(cwd)
    return sorted(roots)

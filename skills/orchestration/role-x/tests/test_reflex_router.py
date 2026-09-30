"""Tests for role-x's reflex mode (ROLE_X_OUTPUT=reflex, scripts/reflex_router.py).

What is pinned here, one section each:
  * the catalog parses, every entry cites a source, covers P1-P20 and every
    evaluated skill, and a skill's phrases are still in that skill's description;
  * each state predicate, positive and negative, on real git repos and a ctx board;
  * prompt routing, a positive and a near-miss per catalog entry;
  * the hook budget: one git call, one board read, the board's log never opened,
    output inside max_lines / max_chars;
  * fail-open: any error prints nothing and exits 0;
  * mutation: deleting a predicate, or making it always false, fails its scenario.
"""
from __future__ import annotations

import builtins
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_DIR / "scripts"
ROUTER_PY = SCRIPTS / "reflex_router.py"
ROLE_X_PY = SCRIPTS / "role-x.py"
HOOK = SCRIPTS / "role-x-intake-hook.sh"
CATALOG = SKILL_DIR / "references" / "reflexes.yaml"
CTX_PY = SKILL_DIR.parent / "ctx-core" / "scripts" / "ctx.py"
#: The monorepo root when these tests run from broomva/skills; None in an install.
REPO = SKILL_DIR.parents[2] if (SKILL_DIR.parents[2] / "skills").is_dir() else None


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


rr = load_module(ROUTER_PY, "reflex_router_under_test")
CAT = rr.load_catalog(CATALOG)
BY_ID = {r.id: r for r in CAT.reflexes}


def all_routed(mod, cat):
    """The catalog with every entry routed: for tests of predicates and routing
    mechanics, independent of which entries currently clear the M3 gate."""
    import dataclasses
    return dataclasses.replace(cat, reflexes=tuple(dataclasses.replace(r, status="routed")
                                                   for r in cat.reflexes))


CAT_ALL = all_routed(rr, CAT)


@pytest.fixture(autouse=True)
def _hermetic_git(monkeypatch):
    # The operator's global git config (hooks, lfs) must not reach these repos.
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for k, v in (("GIT_AUTHOR_NAME", "t"), ("GIT_AUTHOR_EMAIL", "t@example.com"),
                 ("GIT_COMMITTER_NAME", "t"), ("GIT_COMMITTER_EMAIL", "t@example.com")):
        monkeypatch.setenv(k, v)


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True,
                          text=True).stdout.strip()


def commit(ws: Path, name: str, text: str = "x\n") -> None:
    (ws / name).write_text(text, encoding="utf-8")
    git(ws, "add", name)
    git(ws, "commit", "-qm", f"add {name}")


@pytest.fixture
def repo(tmp_path) -> Path:
    """A workspace on main with a bare origin, pushed."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    ws = tmp_path / "ws"
    subprocess.run(["git", "init", "-q", "-b", "main", str(ws)], check=True)
    commit(ws, "README.md", "# ws\n")
    git(ws, "remote", "add", "origin", str(origin))
    git(ws, "push", "-q", "-u", "origin", "main")
    return ws


def pushed_feature(ws: Path, branch: str = "feat/x") -> None:
    git(ws, "switch", "-q", "-c", branch)
    commit(ws, "f.txt")
    git(ws, "push", "-q", "-u", "origin", branch)


def fired_ids(prompt: str, state, cat=None) -> list[str]:
    return [f.reflex.id for f in rr.route(prompt, state, cat or CAT)]


def fired(prompt: str, state, cat=None) -> dict[str, str]:
    return {f.reflex.id: f.via for f in rr.route(prompt, state, cat or CAT)}


NEUTRAL = "ok, what is next?"


def no_board():
    return None


# ------------------------------------------------------------------ catalog

SOURCE_RE = re.compile(
    r"AGENTS\.md §P\d+|memory: \S+\.md|skills/[\w/-]+/SKILL\.md|roles/_meta\.md")


def test_catalog_parses_with_the_documented_budget():
    raw = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))
    assert raw["version"] == 1
    assert CAT.max_lines == 3
    assert CAT.max_chars <= 600  # ~150 tokens at 4 chars a token
    assert len(CAT.reflexes) == len(raw["reflexes"])


def test_every_entry_cites_a_source():
    for r in CAT.reflexes:
        assert SOURCE_RE.search(r.source), f"{r.id}: source {r.source!r} names no known form"


def test_every_primitive_p1_to_p20_has_a_reflex():
    covered = {r.primitive for r in CAT.reflexes if r.primitive}
    assert {f"P{i}" for i in range(1, 21)} <= covered


def test_every_line_names_a_command_and_is_not_an_order():
    orders = re.compile(r"^(always|never|you|do |don't|must|use |run |make sure)|\byou (must|should)\b",
                        re.IGNORECASE)
    for r in CAT.reflexes:
        assert "`" in r.line, f"{r.id}: the line names no command"
        assert not orders.search(r.line), f"{r.id}: the line reads as an order: {r.line!r}"
        assert len(r.line) <= rr.LINE_MAX_CHARS


def test_every_state_predicate_is_used_and_every_used_one_exists():
    used = {n for r in CAT.reflexes for c in r.clauses for n in c.state}
    assert used == set(rr.STATE_PREDICATES)


def _skills_with_evals() -> dict[str, Path]:
    return {p.parent.parent.name: p.parent.parent
            for p in sorted(REPO.glob("skills/*/*/evals/prompts.json"))}


@pytest.mark.skipif(REPO is None, reason="needs the broomva/skills monorepo")
def test_one_line_per_skill_with_evals():
    have = {r.skill for r in CAT.reflexes if r.skill}
    missing = set(_skills_with_evals()) - have
    assert not missing, f"skills with evals/prompts.json but no catalog line: {sorted(missing)}"


def _trigger_text(skill_md: Path) -> str:
    fm = yaml.safe_load(skill_md.read_text(encoding="utf-8").split("---", 2)[1])
    text = " ".join(str(fm.get(k) or "") for k in ("description", "when_to_use"))
    return " ".join(text.lower().split())


@pytest.mark.skipif(REPO is None, reason="needs the broomva/skills monorepo")
def test_skill_phrases_are_still_in_that_skills_description():
    for r in CAT.reflexes:
        if not r.skill:
            continue
        text = _trigger_text(REPO / r.skill_source)
        for phrase in r.phrases:
            assert phrase.lower() in text, f"{r.id}: {phrase!r} is not in {r.skill_source}"


#: A valid entry, then each bad catalog breaks exactly one thing about it.
OK = "id: p9.a, kind: primitive, status: routed, line: 'x `y`', source: s, signature: [{tool: Bash, argv_prefix: [y]}]"
BAD_CATALOGS = {
    "no source": "- {id: p9.a, kind: primitive, status: judgment, line: 'x `y`', when: [{prompt: [a]}]}",
    "unknown predicate": "- {" + OK + ", when: [{state: [nope]}]}",
    "bad regex": "- {" + OK + ", when: [{prompt: ['(']}]}",
    "empty clause": "- {" + OK + ", when: [{}]}",
    "unknown clause key": "- {" + OK + ", when: [{words: [a]}]}",
    "duplicate id": "- {" + OK + ", when: [{prompt: [a]}]}\n- {" + OK + ", when: [{prompt: [b]}]}",
    "skill without source": "- {" + OK + ", skill: k, when: [{prompt: [a]}]}",
    "routed without signature": "- {id: p9.a, kind: primitive, status: routed, line: 'x `y`', source: s, "
                                "when: [{prompt: [a]}]}",
    "bad kind": "- {" + OK.replace("kind: primitive", "kind: lens") + ", when: [{prompt: [a]}]}",
    "bad status": "- {" + OK.replace("status: routed", "status: maybe") + ", when: [{prompt: [a]}]}",
    "bad id": "- {" + OK.replace("id: p9.a", "id: P9_a") + ", when: [{prompt: [a]}]}",
    "bad signature": "- {" + OK.replace("tool: Bash", "tool: Curl") + ", when: [{prompt: [a]}]}",
}


def test_the_bad_catalog_base_entry_is_itself_valid(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("version: 1\nmax_lines: 3\nmax_chars: 600\nreflexes:\n  - {" + OK
                 + ", when: [{prompt: [a]}]}\n", encoding="utf-8")
    assert rr.load_catalog(p).reflexes[0].id == "p9.a"


@pytest.mark.parametrize("case", sorted(BAD_CATALOGS))
def test_a_bad_catalog_is_refused_whole(tmp_path, case):
    p = tmp_path / "c.yaml"
    p.write_text("version: 1\nmax_lines: 3\nmax_chars: 600\nreflexes:\n"
                 + "\n".join("  " + ln for ln in BAD_CATALOGS[case].splitlines()), encoding="utf-8")
    with pytest.raises(rr.CatalogError):
        rr.load_catalog(p)


# --------------------------------------------------------- state predicates


def test_just_pushed_positive(repo):
    pushed_feature(repo)
    ok, fact = rr.STATE_PREDICATES["branch_pushed_recently"](rr.State(cwd=repo, ctx_loader=no_board))
    assert ok and "`feat/x` was pushed 0 min ago" in fact


def test_just_pushed_negative_when_not_pushed(repo):
    pushed_feature(repo)
    commit(repo, "g.txt")  # ahead of upstream by one
    assert not rr.STATE_PREDICATES["branch_pushed_recently"](rr.State(cwd=repo, ctx_loader=no_board))[0]


def test_just_pushed_negative_when_the_push_is_old(repo):
    pushed_feature(repo)
    later = time.time() + rr.PUSH_RECENT_S + 60
    assert not rr.STATE_PREDICATES["branch_pushed_recently"](rr.State(cwd=repo, now=later, ctx_loader=no_board))[0]


def test_just_pushed_negative_when_the_last_update_was_a_fetch(repo):
    pushed_feature(repo)
    git(repo, "update-ref", "-m", "rewind", "refs/remotes/origin/feat/x", "HEAD~1")
    git(repo, "update-ref", "-m", "fetch: fast-forward", "refs/remotes/origin/feat/x", "HEAD")
    assert not rr.STATE_PREDICATES["branch_pushed_recently"](rr.State(cwd=repo, ctx_loader=no_board))[0]


def test_just_pushed_negative_on_main(repo):
    commit(repo, "m.txt")
    git(repo, "push", "-q", "origin", "main")
    assert not rr.STATE_PREDICATES["branch_pushed_recently"](rr.State(cwd=repo, ctx_loader=no_board))[0]


def test_just_pushed_positive_from_a_linked_worktree(repo, tmp_path):
    wt = tmp_path / "wt"
    git(repo, "worktree", "add", "-q", "-b", "feat/wt", str(wt))
    commit(wt, "w.txt")
    git(wt, "push", "-q", "-u", "origin", "feat/wt")
    assert rr.STATE_PREDICATES["branch_pushed_recently"](rr.State(cwd=wt, ctx_loader=no_board))[0]


def test_on_protected_branch(repo):
    assert rr.STATE_PREDICATES["on_default_branch"](rr.State(cwd=repo))[0]
    git(repo, "switch", "-q", "-c", "feat/y")
    assert not rr.STATE_PREDICATES["on_default_branch"](rr.State(cwd=repo))[0]
    git(repo, "switch", "-q", "--detach", "HEAD")
    assert not rr.STATE_PREDICATES["on_default_branch"](rr.State(cwd=repo))[0]


def test_on_protected_branch_negative_outside_git(tmp_path):
    assert not rr.STATE_PREDICATES["on_default_branch"](rr.State(cwd=tmp_path))[0]


def test_staged_on_protected(repo):
    (repo / "README.md").write_text("# changed\n", encoding="utf-8")
    assert not rr.STATE_PREDICATES["staged_on_default_branch"](rr.State(cwd=repo))[0]  # unstaged only
    git(repo, "add", "README.md")
    ok, fact = rr.STATE_PREDICATES["staged_on_default_branch"](rr.State(cwd=repo))
    assert ok and "`main` has 1 staged change" in fact
    git(repo, "switch", "-q", "-c", "feat/z")  # the staged change travels with the switch
    assert not rr.STATE_PREDICATES["staged_on_default_branch"](rr.State(cwd=repo))[0]


# live_peer_here, against ctx's own is_live / parse_ts with the scope and board faked

ctx_real = load_module(CTX_PY, "ctx_for_reflex_tests") if CTX_PY.is_file() else None
needs_ctx = pytest.mark.skipif(ctx_real is None, reason="ctx-core is not beside role-x")


def fake_ctx(rows, *, branch="feat/x", cwd="/w", repo_dir="/w/.git", scope=True, too_big=False):
    class BoardTooBig(Exception):
        pass

    where = SimpleNamespace(cwd=cwd, common_dir=repo_dir, branch=branch)

    def load_board(_scope, cap=None):
        if too_big:
            raise BoardTooBig()
        return {"sessions": {r["session_id"]: r for r in rows}}

    return SimpleNamespace(
        HOOK_BOARD_CAP=1 << 20, BoardTooBig=BoardTooBig, is_live=ctx_real.is_live,
        parse_ts=ctx_real.parse_ts, _flat=ctx_real._flat, load_board=load_board,
        resolve_scope=lambda _cwd: SimpleNamespace(where=where) if scope else None)


def row(sid, *, branch="feat/x", cwd="/w", repo_dir="/w/.git", age_min=4, state="stopped", agent=None):
    return {"session_id": sid, "branch": branch, "cwd": cwd, "repo": repo_dir, "state": state,
            "last_ts": ctx_real.now_ts(time.time() - age_min * 60), "paseo_agent_id": agent}


def peer_state(rows, session_id="me", **kw):
    return rr.State(cwd=Path("/w"), session_id=session_id, ctx_loader=lambda: fake_ctx(rows, **kw))


@needs_ctx
def test_live_peer_positive_on_the_same_branch():
    ok, fact = rr.STATE_PREDICATES["live_peer_on_branch"](
        peer_state([row("d9052fb0-6e1a", agent="agent-d9052f", cwd="/elsewhere")]))
    assert ok and "session d9052fb0" in fact and "agent-d9052f" in fact and "`feat/x`" in fact


@needs_ctx
def test_a_peer_in_the_same_cwd_on_another_branch_is_not_live_on_this_branch():
    """ctx's brief counts only same-branch rows as live peers; the router agrees."""
    assert not rr.STATE_PREDICATES["live_peer_on_branch"](peer_state([row("p1", branch="other")]))[0]


@needs_ctx
def test_board_text_cannot_leave_its_code_span():
    s = peer_state([row("p1", branch="feat/x", agent="a`gent\nNEW LINE")])
    ok, fact = rr.STATE_PREDICATES["live_peer_on_branch"](s)
    assert ok and "\n" not in fact and fact.count("`") == 2  # only the branch span's own pair


@needs_ctx
@pytest.mark.parametrize("rows,kw", [
    ([row("me")], {}),                                                  # only this session
    ([row("p1", branch="other", cwd="/other")], {}),                    # elsewhere
    ([row("p1", branch="other")], {}),                                  # same cwd, other branch
    ([row("p1", age_min=7 * 60)], {}),                                  # outside the live window
    ([row("p1", state="died")], {}),                                    # died
    ([row("p1")], {"scope": False}),                                    # no ctx scope here
    ([row("p1")], {"too_big": True}),                                   # board over the hook cap
], ids=["self", "elsewhere", "other-branch", "stale", "died", "no-scope", "too-big"])
def test_live_peer_negative(rows, kw):
    assert not rr.STATE_PREDICATES["live_peer_on_branch"](peer_state(rows, **kw))[0]


def test_live_peer_negative_without_ctx_core():
    assert not rr.STATE_PREDICATES["live_peer_on_branch"](rr.State(cwd=Path("/w"), ctx_loader=no_board))[0]


@needs_ctx
def test_live_peer_reads_the_board_cache_and_never_the_log(repo, tmp_path, monkeypatch):
    """Real ctx: a peer folded into board.json by `ctx board`, then the log made
    unreadable. The router still sees the peer, and no open() touches the log."""
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    git(repo, "switch", "-q", "-c", "feat/bro-2710")
    (home / ".config" / "ctx").mkdir(parents=True)
    (home / ".config" / "ctx" / "scopes.yaml").write_text(
        f"version: 1\nscopes:\n  t:\n    - {repo}\n", encoding="utf-8")
    store = home / ".local" / "state" / "ctx" / "t"
    store.mkdir(parents=True)
    base = {"v": 1, "session_id": "d9052fb0-6e1a-4b2c-9d3e-5f6a7b8c9d0e", "cwd": os.path.realpath(repo),
            "repo": os.path.realpath(repo / ".git"), "branch": "feat/bro-2710"}
    events = [{**base, "type": "session.start", "ts": ctx_real.now_ts(time.time() - 600), "payload": {}},
              {**base, "type": "session.stop", "ts": ctx_real.now_ts(time.time() - 180), "payload": {}}]
    (store / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
    subprocess.run([sys.executable, "-I", str(CTX_PY), "-C", str(repo), "board", "--json"],
                   check=True, capture_output=True, env={**os.environ, "HOME": str(home)})
    assert (store / "board.json").is_file()
    (store / "events.jsonl").chmod(0)
    opened: list[str] = []
    real_open, real_io_open = builtins.open, io.open

    def spy(file, *a, **k):
        opened.append(str(file))
        return real_open(file, *a, **k)

    def io_spy(file, *a, **k):
        opened.append(str(file))
        return real_io_open(file, *a, **k)

    monkeypatch.setattr(builtins, "open", spy)
    monkeypatch.setattr(io, "open", io_spy)
    try:
        ok, fact = rr.STATE_PREDICATES["live_peer_on_branch"](rr.State(cwd=repo, session_id="me"))
    finally:
        (store / "events.jsonl").chmod(0o600)
    assert ok and "session d9052fb0" in fact
    assert not [p for p in opened if p.endswith("events.jsonl")]


# --------------------------------------- state predicates through the router


def test_a_push_alone_fires_p9_watch(repo):
    pushed_feature(repo)
    assert fired(NEUTRAL, rr.State(cwd=repo, ctx_loader=no_board)).get("p9.watch-after-push") == "state"
    git(repo, "switch", "-q", "main")
    assert "p9.watch-after-push" not in fired(NEUTRAL, rr.State(cwd=repo, ctx_loader=no_board))


def test_branch_first_on_main_with_change_work(repo):
    s = rr.State(cwd=repo, ctx_loader=no_board)
    assert fired("fix the recieve typo in README.md and commit it", s)["p10.branch-first"] == "state+prompt"
    assert "p10.branch-first" not in fired("what does the README say?", rr.State(cwd=repo, ctx_loader=no_board))
    assert "p10.branch-first" not in fired("what did the build agent change?", rr.State(cwd=repo, ctx_loader=no_board))
    git(repo, "switch", "-q", "-c", "feat/y")
    assert "p10.branch-first" not in fired("fix the recieve typo in README.md and commit it",
                                       rr.State(cwd=repo, ctx_loader=no_board))


def test_branch_first_on_staged_main_whatever_the_prompt(repo):
    (repo / "README.md").write_text("# changed\n", encoding="utf-8")
    git(repo, "add", "README.md")
    assert fired(NEUTRAL, rr.State(cwd=repo, ctx_loader=no_board))["p10.branch-first"] == "state"


@needs_ctx
def test_a_live_peer_fires_only_with_a_git_op_prompt():
    """The ctx brief already names live peers at SessionStart (spec §5.2 defers the
    coordination line to it), so the router speaks only at the moment of risk."""
    def on(branch, peers=True):
        rows = [row("p1", branch=branch)] if peers else []
        s = rr.State(cwd=Path("/w"), session_id="me", ctx_loader=lambda: fake_ctx(rows, branch=branch))
        s._git = rr.GitState("ok", branch=branch)
        return s

    for branch in ("feat/x", "main"):
        assert "ctx.live-peer-before-git-op" not in fired(NEUTRAL, on(branch), CAT_ALL)
        assert fired("pull origin/main into it", on(branch), CAT_ALL)["ctx.live-peer-before-git-op"] == "state+prompt"
        assert "ctx.live-peer-before-git-op" not in fired("pull origin/main into it", on(branch, peers=False), CAT_ALL)
    # Listed until its sealed M3 clears the bar: the real catalog never injects it.
    assert not BY_ID["ctx.live-peer-before-git-op"].routed
    assert "ctx.live-peer-before-git-op" not in fired("pull origin/main into it", on("main"))


def test_state_facts_lead_the_line(repo):
    pushed_feature(repo)
    text, _ = rr.run(NEUTRAL, repo, catalog=CAT, state=rr.State(cwd=repo, ctx_loader=no_board))
    assert "- `feat/x` was pushed 0 min ago. After a push" in text


# ------------------------------------------------------------- prompt routing

#: One or more prompts each entry must fire on, and near-misses it must not, all
#: routed on a clean feature branch with no board, so only the prompt decides.
EXAMPLES: dict[str, tuple[list[str], list[str]]] = {
    "p9.watch-after-push": (["push this branch, open the PR and let me know when CI is green",
                             "ship it as a PR and ping me when the checks pass", "is the watcher running?",
                             "add some random jitter to backoff(n) in src/retry.py, then open a pr for it",
                             "fix the flaky test in tests/test_io.py", "commit this and push", "lgtm, ship it",
                             "go", "push it"],
                            ["what does ci.yml do?", "push notifications for the app",
                             "what did the build agent change?", "how do git add and commit differ?"]),
    "p10.branch-first": (["switch to main and add a line to docs/RUNBOOK.md, then commit it",
                      "go back to master and commit the fix"],
                     ["switch to main and tell me what changed", "what is on main?"]),
    "p4.merge-pinned-to-head": (["Merge 1857", "merge #812 once it's green", "land it", "merge it please",
                              "merge the PR", "merge, go"],
                             ["merge sort is O(n log n)", "resolve the merge conflicts",
                              "merge main into this branch", "resolve the merge conflicts on this branch",
                              "merge the two configs so it works", "merge it into the release notes"]),
    "p10.worktree-removal-guard": (["that worktree for the lint branch is done, get rid of it",
                                "clean up the old worktrees", "claude rm the bg session"],
                               ["create a worktree for the fix", "list the worktrees"]),
    "ctx.live-peer-before-git-op": (["is anyone else working in this checkout right now?"],
                                ["who else is on the team?", "is anyone free for lunch?"]),
    "p9.heal-on-red": (["CI on #1903 went red, sort it out", "the checks are failing on my PR",
                                "build failed again", "please check PR #1192 why did it failed?", "#1857 failed"],
                               ["check the CI config", "red button styling",
                                "write a test that fails on empty input", "check the parser, it failed on me",
                                "build a red button for the form", "Build a workflow that retries failed payments",
                                "add a test to the PR that fails without the fix",
                                "the PR description is broken, fix the markdown"]),
    "convention.trash-not-rm": (["Can't you drop those scratch folders?", "clear out the tmp dirs under ~/scratch",
                      "delete the old clones under ~/scratch"],
                     ["drop the database index", "remove this function", "delete the old clones",
                      "remove the tmp variable from utils.py", "drop the scratch column from the users table",
                      "delete the worktree folder .worktrees/intent-ask"]),
    "convention.paseo-fleet-listing": (["the paseo app ui still shows a lot of sessions", "how many paseo agents are running?"],
                            ["paseo release notes", "list the sessions in the log"]),
    "p2.gate-destructive-git": (["force push the branch", "git reset --hard to origin"],
                             ["push the branch", "reset the counter"]),
    "p18.human-doc-in-specs": (["can you create a quick document explaining how to change the nameservers",
                            "write a report on the outage"],
                           ["document.getElementById returns null", "read the doc"]),
    "p15.snapshot": (["where do we stand?", "is everything pushed?", "what's the status of the arc?"],
                       ["stand up the service", "status code 500", "Whats the status of the paseo sessions?"]),
    "skill.kg": (["what do we know about lago replication?", "kg load ctx-core"],
                     ["what do you know about python?", "load the page"]),
    "p8.janitor-branches": (["prune the merged branches", "clean up stale branches"],
                         ["what branch am I on?", "branches of the tree"]),
    "p11.bugfix-test-lock": (["fix the bug in the parser", "reproduce the crash on login"],
                         ["fix the typo", "report a bug to them"]),
    "p12.persist": (["run this overnight", "keep at it for the next few hours"],
                             ["what time is it?", "an hour ago the build passed"]),
    "p3.ticket": (["file a Linear ticket for this", "BRO-2674 needs an update"],
                      ["read docs/handoffs/2026-09-29-bro-2710-retry.md", "linear algebra"]),
    "p6.capture-not-ask": (["remember this for next time", "add it to the knowledge graph"],
                        ["I don't remember", "file size is too big"]),
    "p10.cleanup-after-merge": (["now that it's merged, clean up", "after #812 merged, what's left?"],
                           ["merge it", "unmerged paths"]),
    "p20.cross-review": (["run a cross-review on this", "review the PR before merge"],
                          ["review my essay", "code review culture"]),
    "p1.bridge-prior-sessions": (["didn't we fix this before?", "last time we hit this we solved it"],
                              ["before you start, read the spec", "we fixed it"]),
    "p5.fanout": (["do these three in parallel", "fan out agents for the audit"],
                        ["parallel lines never meet", "one at a time please"]),
    "p7.freshness": (["error: unrecognized arguments: --background", "update the skills"],
                         ["update the readme", "skills matter"]),
    "p13.dream-replay": (["consolidate the memories into rules", "bookkeeping run now"],
                     ["consolidate the css", "promote the post"]),
    "p19.orchestrate": (["work on this autonomously until it's merged", "/goal all tests pass"],
                              ["autonomy is a value", "keep going"]),
    "p14.depchain": (["think deeply through the chain of dependencies", "refactor the router"],
                 ["think about it", "the chain broke"]),
    "p16.rule-of-three": (["I keep asking you for this every time", "third time I've said it"],
                                  ["this time is different", "time to go"]),
    "p17.lens-candidate": (["add a new lens for rust", "what did role-x select?"],
                       ["camera lens reviews", "the role of x"]),
    "p4.ship-not-ask": (["please create a proper keynote from the notes, use html",
                      "scaffold a new typescript package"],
                     ["what is a keynote?", "read the package.json"]),
    "p11.empirical-evidence": (["make sure it works end to end", "does it work?"],
                           ["make check runs before make test", "how does it work?"]),
    "skill.arc": (["I'm off until morning, finish it", "run the arc"],
                  ["the arc of history", "morning standup"]),
    "skill.autonomous": (["go", "ship it", "lets work /autonomous", "be autonomous"],
                         ["go to the settings page", "ship it to production later?"]),
    "skill.resume": (["resume", "continue", "pick up where you left off"],
                     ["continue with the next step after reading", "resume.pdf"]),
    "skill.handoff": (["write a handoff", "leave notes for the next agent"],
                      ["read docs/handoffs/2026-09-29.md", "hand off the keys"]),
    "skill.checkit": (["check this out https://x.com/a", "wdyt? https://arxiv.org/abs/2609.01",
                       "look into this ~/Downloads/paper.pdf"],
                      ["check this box", "checkout the branch", "look into this failing test",
                       "I found this bug", "wdyt?", "look into this flaky test in tests/test_x.py"]),
    "skill.dogfood": (["dogfood this", "click through the app and prove it"],
                      ["dog food brands", "the app crashed"]),
    "skill.unslop": (["this site looks vibecoded", "unslop this landing page"],
                     ["this site looks great", "slope of the line"]),
    "skill.legal-readiness": (["do a legal audit of the app", "legal readiness before launch"],
                              ["is it legal to park here?", "audit the logs"]),
    "skill.audit-harness-usage": (["what did my agents cost this week?", "token usage across harnesses"],
                                  ["token refresh fails", "usage of the word"]),
    "skill.disambiguate": (["disambiguate this AC", "tighten this spec"],
                           ["this is clearly wrong", "spec out the room"]),
    "skill.skillify": (["skillify it", "turn this into a skill"],
                       ["what skills do I have?", "skill issue"]),
}


def feature_state() -> "rr.State":
    s = rr.State(cwd=Path("/nonexistent"), ctx_loader=no_board)
    s._git = rr.GitState("ok", branch="feat/clean")
    return s


def test_every_entry_has_routing_examples():
    assert set(EXAMPLES) == set(BY_ID)


def _matches(reflex, prompt: str) -> bool:
    text = rr.normalize_prompt(prompt)
    return any(p.search(text) for c in reflex.clauses for p in c.patterns)


@pytest.mark.parametrize("rid", sorted(r for r in EXAMPLES if BY_ID[r].routed))
def test_prompt_routing(rid):
    positives, negatives = EXAMPLES[rid]
    for p in positives:
        assert rid in fired_ids(p, feature_state()), f"{rid} should fire on {p!r}"
    for p in negatives:
        assert rid not in fired_ids(p, feature_state()), f"{rid} should not fire on {p!r}"


@pytest.mark.parametrize("rid", sorted(r for r in EXAMPLES if not BY_ID[r].routed))
def test_a_listed_or_judgment_entry_matches_its_trigger_and_is_never_routed(rid):
    """Its trigger still matches what it was written for, so the gap is real and
    measurable, but the router never injects it."""
    positives, negatives = EXAMPLES[rid]
    for p in positives:
        assert _matches(BY_ID[rid], p), f"{rid}'s own trigger should match {p!r}"
        assert rid not in fired_ids(p, feature_state())
    for p in negatives:
        assert not _matches(BY_ID[rid], p), f"{rid}'s trigger should not match {p!r}"


def test_routed_entries_cover_the_owner_s_initial_cases():
    routed = {r.id for r in CAT.reflexes if r.routed}
    assert {"p9.watch-after-push", "p10.branch-first", "p9.heal-on-red",
            "convention.trash-not-rm", "convention.paseo-fleet-listing", "p4.merge-pinned-to-head"} <= routed
    # the worktree guard is listed: the ablation showed its line misread as automation
    assert BY_ID["p10.worktree-removal-guard"].status == "listed"


def test_a_listed_entry_records_why():
    raw = {e["id"]: e for e in yaml.safe_load(CATALOG.read_text(encoding="utf-8"))["reflexes"]}
    for r in CAT.reflexes:
        if r.status == "listed":
            why = str(raw[r.id].get("m3", "")) + str(raw[r.id].get("m2", ""))
            assert "recall" in why or "held-out" in why, f"{r.id}: listed without its measurement"


def test_change_work_route_is_an_imperative_not_a_question():
    cw = CAT.routes["change_work"]
    hit = lambda p: any(x.search(rr.normalize_prompt(p)) for x in cw)  # noqa: E731
    for p in ("fix the recieve typo in README.md and commit it", "can you add a --dry-run flag",
              "switch to main and add a line", "please create a proper keynote", "refactor router.py"):
        assert hit(p), p
    for p in ("what did the build agent change?", "how does the fix work?", "is the update live?",
              "delete the old clones", "how do git add and commit differ?",
              "whats the difference between create and update in the REST api?"):
        assert not hit(p), p


def test_requires_needs_every_pattern():
    rid = "skill.checkit"
    assert rid in fired_ids("check this out https://github.com/x/y", feature_state())
    assert rid not in fired_ids("check this out", feature_state())


def test_a_dot_inside_a_path_is_not_a_sentence_end():
    """Found on a held-out prompt: `[^.?!]` stopped at the dot of `.worktrees/`."""
    rid = "p10.worktree-removal-guard"
    assert rid in fired_ids("Remove the .worktrees/intent-ask worktree and your branch", feature_state(), CAT_ALL)
    assert rid in fired_ids("delete the worktree for v0.7.2 please", feature_state(), CAT_ALL)
    assert rid not in fired_ids("Remove it. The worktree list is long.", feature_state(), CAT_ALL)
    assert "convention.trash-not-rm" not in fired_ids("delete this. folders are fine", feature_state())


def test_curly_apostrophes_route_like_straight_ones():
    assert "convention.trash-not-rm" in fired_ids("Can\u2019t you drop those scratch folders?", feature_state())


def test_the_stage_3_seam_narrows_and_defaults_to_off(monkeypatch):
    seen = []

    class Recording:
        name = "recording"

        def narrow(self, prompt, candidates):
            seen.append([c.key for c in candidates])
            keep = {c.key for c in candidates if c.reflex.id == "skill.skillify"}
            return keep | {"p9.watch-after-push#0"}  # not offered: must be ignored

    monkeypatch.setitem(rr.NARROWERS, "recording", Recording)
    monkeypatch.setenv(rr.JEV_ENV, "recording")
    prompt = "skillify it, then push this branch and open the PR"
    assert [f.reflex.id for f in rr.route(prompt, feature_state(), CAT_ALL)] == ["skill.skillify"]
    assert "skill.skillify#0" in seen[0] and "p9.watch-after-push#3" in seen[0]
    monkeypatch.setenv(rr.JEV_ENV, "no-such-narrower")
    assert rr.get_narrower().name == "off"
    monkeypatch.delenv(rr.JEV_ENV)
    assert rr.get_narrower().name == "off"


def test_stage_3_sees_only_what_stages_1_and_2_kept():
    class Spy:
        name = "spy"
        keys: list[str] = []

        def narrow(self, prompt, candidates):
            Spy.keys = [c.key for c in candidates]
            return set()

    assert rr.route("fix it", feature_state(), CAT, Spy()) == []  # abstaining drops everything
    assert "p10.branch-first#1" not in Spy.keys  # prompt matched, but its gate on_default_branch is closed
    assert Spy.keys == ["p9.watch-after-push#1"]  # change_work, in a repo, carries the p9 rule
    Spy.keys = []
    rr.route("hmm, interesting", feature_state(), CAT, Spy())
    assert Spy.keys == []  # nothing matched, so stage 3 is never asked
    rr.route("switch to main and fix it, then commit", feature_state(), CAT, Spy())
    assert Spy.keys == ["p9.watch-after-push#1", "p10.branch-first#2"]  # feature_state's git is ok


# ------------------------------------------------------------------- budget

KITCHEN_SINK = ("push this branch and open the PR, merge 812, drop the scratch folders, the paseo "
                "sessions look stale, CI failed, get rid of the worktree, force push, where do we stand")


def test_output_stays_inside_the_line_and_char_budget():
    fired_all = rr.route(KITCHEN_SINK, feature_state(), CAT)
    assert len(fired_all) > CAT.max_lines  # the cap is what limits this block
    text, shown = rr.render(fired_all, CAT.max_lines, CAT.max_chars)
    assert text.startswith(rr.HEADER + "\n")
    assert len(text.splitlines()) - 1 == len(shown) <= CAT.max_lines
    assert len(text) <= CAT.max_chars
    assert len(text) / 4 <= 150  # ~150 tokens


def test_a_line_that_does_not_fit_is_dropped_whole():
    fired_all = rr.route(KITCHEN_SINK, feature_state(), CAT)
    text, shown = rr.render(fired_all, 3, len(rr.HEADER) + 1 + len(rr.render_line(fired_all[0])))
    assert shown == [fired_all[0]] and text.splitlines()[1] == rr.render_line(fired_all[0])


def test_nothing_fires_means_no_header_at_all():
    assert rr.run("what is 2 + 2?", Path("/"), catalog=CAT, state=feature_state())[0] == ""


def test_one_git_call_and_one_board_read_per_route(repo):
    calls = []

    def counting_run(argv, **kw):
        calls.append(argv)
        return subprocess.run(argv, **kw)

    boards = []
    s = rr.State(cwd=repo, run=counting_run, ctx_loader=lambda: boards.append(1))
    git(repo, "switch", "-q", "-c", "feat/y")
    rr.route(KITCHEN_SINK, s, CAT_ALL)
    assert len(calls) == 1 and calls[0][3:5] == ["status", "--porcelain=v2"]
    assert s.reads == {"git": "ok", "board": "no-ctx"} and len(boards) == 1


def test_the_board_is_not_read_unless_a_git_op_prompt_needs_it(repo):
    """Stage order: a clause's prompt is matched before its state is read."""
    boards = []
    s = rr.State(cwd=repo, ctx_loader=lambda: boards.append(1))
    rr.route("drop the scratch folders", s, CAT_ALL)
    assert boards == [] and "board" not in s.reads


def test_a_raising_predicate_is_false_logged_and_spares_the_rest(monkeypatch, repo):
    def boom(_s):
        raise ValueError("bad board row")
    monkeypatch.setitem(rr.STATE_PREDICATES, "live_peer_on_branch", boom)
    text, meta = rr.run("pull origin/main and drop the scratch folders", repo, catalog=CAT_ALL,
                        state=rr.State(cwd=repo, ctx_loader=no_board), count=False)
    assert "convention.trash-not-rm" in meta["selected"]
    assert meta["predicate_errors"] == {"live_peer_on_branch": "ValueError"}


@pytest.mark.parametrize("exc,status", [(subprocess.TimeoutExpired(["git"], 1), "timeout"),
                                        (ValueError("undecodable"), "error"), (OSError("no git"), "error")])
def test_a_git_failure_is_named_not_mistaken_for_no_repo(exc, status):
    def run(*_a, **_k):
        raise exc
    s = rr.State(cwd=Path("/tmp"), run=run)
    assert s.git.status == status and s.reads["git"] == status and not s.git.ok


def test_git_status_takes_no_optional_locks(repo):
    envs = []

    def spy(argv, **kw):
        envs.append(kw.get("env") or {})
        return subprocess.run(argv, **kw)

    rr.State(cwd=repo, run=spy).git  # noqa: B018 - the property is the call
    assert envs[0].get("GIT_OPTIONAL_LOCKS") == "0"


# ------------------------------------------------------------ repeat cap, signatures


def test_an_id_goes_out_at_most_twice_per_session(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "h"))
    st = lambda: rr.State(cwd=repo, ctx_loader=no_board)  # noqa: E731
    shown = [rr.run("Merge 1857", repo, "sess-1", catalog=CAT, state=st())[1]["selected"] for _ in range(3)]
    assert shown == [["p4.merge-pinned-to-head"], ["p4.merge-pinned-to-head"], []]
    assert rr.run("Merge 1857", repo, "sess-2", catalog=CAT, state=st())[1]["selected"]  # a new session
    third = rr.run("Merge 1857", repo, "sess-1", catalog=CAT, state=st())[1]
    assert third["cut"] == ["p4.merge-pinned-to-head"]


def test_the_offline_cli_and_unknown_sessions_do_not_count(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "h"))
    for _ in range(3):
        assert rr.run("Merge 1857", repo, "sess-s", catalog=CAT, count=False)[1]["selected"]
        assert rr.run("Merge 1857", repo, "unknown", catalog=CAT)[1]["selected"]
    assert not rr.sessions_dir(tmp_path / "h").exists() or not list(rr.sessions_dir(tmp_path / "h").glob("*.json"))


def test_the_pinned_p9_rule_is_never_capped_and_goes_first(repo, tmp_path, monkeypatch):
    """Spec I1: on every change-work prompt p9 is in the first slot, however often."""
    monkeypatch.setenv("HOME", str(tmp_path / "h"))
    prompts = ["implement the retry logic", "fix the failing test", "refactor the parser, then add docs"] * 2
    for p in prompts:
        meta = rr.run(p, repo, "sess-p", catalog=CAT, state=rr.State(cwd=repo, ctx_loader=no_board))[1]
        assert meta["selected"][0] == "p9.watch-after-push", (p, meta)


def test_the_cap_is_per_fact_so_a_new_fact_rearms_it(repo, tmp_path, monkeypatch):
    """branch-first with the state fact "`main` has N staged change(s)": capped at two
    per fact, and the digits do not make every prompt a new fact."""
    monkeypatch.setenv("HOME", str(tmp_path / "h"))
    (repo / "README.md").write_text("# changed\n", encoding="utf-8")
    git(repo, "add", "README.md")
    got = [rr.run("ok, what is next?", repo, "sess-f", catalog=CAT,
                  state=rr.State(cwd=repo, ctx_loader=no_board))[1]["selected"] for _ in range(3)]
    assert ["p10.branch-first" in g for g in got] == [True, True, False]
    commit(repo, "extra.txt")  # a different staged count is the same fact once digits drop
    (repo / "other.txt").write_text("x\n", encoding="utf-8")
    git(repo, "add", "other.txt")
    again = rr.run("ok, what is next?", repo, "sess-f", catalog=CAT, state=rr.State(cwd=repo, ctx_loader=no_board))
    assert "p10.branch-first" not in again[1]["selected"]


def test_shadow_counts_like_reflex_would(repo, tmp_path, usersite_env):
    home = tmp_path / "h"
    rows = [[r for r in run_hook("Merge 1857 please now", repo, home, mode="shadow")[1]
             if r.get("event") == "reflex"][-1] for _ in range(3)]
    assert [r["selected"] for r in rows] == [["p4.merge-pinned-to-head"]] * 2 + [[]]


def test_a_hostile_session_id_names_no_file(tmp_path):
    assert rr._session_file("../../etc/passwd", tmp_path) is None
    assert rr._session_file("", tmp_path) is None
    assert rr._session_file("a" * 200, tmp_path) is None


@pytest.mark.parametrize("command,sig,want", [
    ("p9 watch 12 --background", {"tool": "Bash", "argv_prefix": ["p9", "watch"]}, True),
    ("python3 ~/.claude/skills/p9/scripts/p9.py watch 12", {"tool": "Bash", "argv_prefix": ["p9", "watch"]}, True),
    ("FOO=1 uv run p9 watch 12", {"tool": "Bash", "argv_prefix": ["p9", "watch"]}, True),
    ("echo p9 watch", {"tool": "Bash", "argv_prefix": ["p9", "watch"]}, False),
    ("p9 status", {"tool": "Bash", "argv_prefix": ["p9", "watch"]}, False),
    ("gh pr merge 1 --squash --match-head-commit abc", {"tool": "Bash", "argv_prefix": ["gh", "pr", "merge"]}, True),
    ("cd /w && gh pr merge 1 --squash", {"tool": "Bash", "argv_prefix": ["gh", "pr", "merge"]}, True),
    ("git fetch; p9 watch 12", {"tool": "Bash", "argv_prefix": ["p9", "watch"]}, True),
])
def test_signatures_match_canonical_invocations(command, sig, want):
    assert rr.signature_matches(sig, "Bash", command=command) is want


def test_a_write_signature_covers_edit_paths():
    sig = BY_ID["p18.human-doc-in-specs"].signature[0]
    for tool in ("Write", "Edit", "MultiEdit"):
        assert rr.signature_matches(sig, tool, path="/w/docs/specs/2026-09-30-dns.html")
    assert not rr.signature_matches(sig, "Read", path="/w/docs/specs/2026-09-30-dns.html")
    assert not rr.signature_matches(sig, "Write", path="/w/docs/notes/dns.md")


def test_route_is_fast_in_process(repo):
    rr.route(NEUTRAL, rr.State(cwd=repo), CAT)  # warm the ctx import
    worst = 0.0
    for p in [KITCHEN_SINK, NEUTRAL, "Merge 1857"] * 5:
        t0 = time.monotonic()
        rr.route(p, rr.State(cwd=repo), CAT)
        worst = max(worst, time.monotonic() - t0)
    assert worst < 0.25, f"slowest route took {worst * 1000:.0f} ms"


# ---------------------------------------------------------- the hook, end to end


def run_hook(prompt, ws, home, *, mode="reflex", extra=None, payload=None):
    env = {**os.environ, "HOME": str(home), "ROLE_X_OUTPUT": mode, **(extra or {})}
    body = payload if payload is not None else json.dumps(
        {"prompt": prompt, "session_id": "s1", "cwd": str(ws)})
    p = subprocess.run(["bash", str(HOOK)], input=body, capture_output=True, text=True, env=env,
                       cwd=str(ws), timeout=30)
    events = home / ".config" / "broomva" / "role" / "events.jsonl"
    rows = [json.loads(x) for x in events.read_text().splitlines()] if events.exists() else []
    return p, rows


@pytest.fixture
def usersite_env(monkeypatch):
    # The hook runs python -I and re-adds the USER site for PyYAML; HOME moves in
    # these tests, so point the user base back at the real one.
    base = subprocess.run([sys.executable, "-c", "import site; print(site.getuserbase())"],
                          capture_output=True, text=True).stdout.strip()
    monkeypatch.setenv("PYTHONUSERBASE", base)
    monkeypatch.setenv("ROLE_X_PYTHON", sys.executable)


def test_hook_prints_the_block_and_logs_bytes_and_time(repo, tmp_path, usersite_env):
    t0 = time.monotonic()
    p, rows = run_hook("Merge 1857", repo, tmp_path / "h")
    wall = time.monotonic() - t0
    assert p.returncode == 0 and p.stdout.startswith("[bstack reflexes]\n- A merge is pinned")
    ev = rows[-1]
    assert ev["event"] == "reflex" and ev["selected"] == ["p4.merge-pinned-to-head"]
    assert ev["bytes"] == len(p.stdout.rstrip("\n").encode())
    assert ev["ms"] < 250 and wall < 5.0
    assert ev["prompt_digest"].startswith("sha256:") and "Merge" not in json.dumps(ev)


def test_hook_default_output_is_unchanged(repo, tmp_path, usersite_env):
    p, rows = run_hook("Merge 1857 please now", repo, tmp_path / "h", mode="")
    assert p.returncode == 0 and "[bstack reflexes]" not in p.stdout
    assert not [r for r in rows if r.get("event") == "reflex"]


def test_an_unknown_output_is_the_default(repo, tmp_path, usersite_env):
    p, rows = run_hook("Merge 1857 please now", repo, tmp_path / "h", mode="nonsense")
    assert "[bstack reflexes]" not in p.stdout and not [r for r in rows if r.get("event") == "reflex"]


def test_role_x_mode_is_an_alias_and_role_x_output_wins(repo, tmp_path, usersite_env):
    p, _ = run_hook("Merge 1857", repo, tmp_path / "h1", mode="", extra={"ROLE_X_MODE": "reflex"})
    assert p.stdout.startswith("[bstack reflexes]")
    p, _ = run_hook("Merge 1857 please now", repo, tmp_path / "h2", mode="legacy",
                    extra={"ROLE_X_MODE": "reflex"})
    assert "[bstack reflexes]" not in p.stdout


def test_shadow_logs_the_router_and_injects_only_the_legacy_block(repo, tmp_path, usersite_env):
    p, rows = run_hook("Merge 1857 please now", repo, tmp_path / "h", mode="shadow")
    assert "[bstack reflexes]" not in p.stdout
    shadow = [r for r in rows if r.get("event") == "reflex"]
    assert shadow and shadow[-1]["shadow"] is True and shadow[-1]["selected"] == ["p4.merge-pinned-to-head"]


@pytest.mark.skipif(REPO is None, reason="needs the broomva/skills monorepo")
def test_route_evals_scores_every_skill_with_an_eval_set():
    p = subprocess.run([sys.executable, str(ROLE_X_PY), "reflexes", "route", "--evals", "--json",
                        "--root", str(REPO)], capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout)
    assert {r["skill"] for r in out["ids"]} == set(_skills_with_evals())
    assert out["suite"]["should_route"] > 100 and out["suite"]["near_miss"] > 60
    # A floor, not a goal: lexical routing on the skills' own eval prompts (in-sample,
    # since the phrases came from the same descriptions), 0.32 recall / 0.06 false
    # fire when v1 shipped. A drop below this is a regression.
    assert out["suite"]["recall"] >= 0.25 and out["suite"]["false_fire"] <= 0.15


# ------------------------------------------------------------------- fail-open

BROKEN = {
    "missing catalog": None,
    "not yaml": "{{{",
    "bad regex": ("version: 1\nmax_lines: 3\nmax_chars: 600\nreflexes:\n"
                  "  - {id: a, line: 'x `y`', source: s, when: [{prompt: ['(']}]}\n"),
}


@pytest.mark.parametrize("case", sorted(BROKEN))
def test_a_broken_catalog_prints_nothing_and_exits_zero(repo, tmp_path, usersite_env, case):
    path = tmp_path / "c.yaml"
    if BROKEN[case] is not None:
        path.write_text(BROKEN[case], encoding="utf-8")
    p, rows = run_hook("Merge 1857", repo, tmp_path / "h", extra={rr.CATALOG_ENV: str(path)})
    assert p.returncode == 0 and p.stdout == ""
    assert rows[-1]["event"] == "reflex" and rows[-1]["error"] == "CatalogError"


def test_a_broken_router_module_prints_nothing(tmp_path):
    """role-x.py loads the router by path; a router that raises at import is silent."""
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "role-x.py").write_text(ROLE_X_PY.read_text(encoding="utf-8"), encoding="utf-8")
    (scripts / "reflex_router.py").write_text("raise RuntimeError('boom')\n", encoding="utf-8")
    home = tmp_path / "h"
    p = subprocess.run([sys.executable, str(scripts / "role-x.py"), "intake", "--prompt", "Merge 1857",
                        "--workspace", str(tmp_path)], capture_output=True, text=True,
                       env={**os.environ, "HOME": str(home), "ROLE_X_OUTPUT": "reflex"})
    assert p.returncode == 0 and p.stdout == ""
    ev = json.loads((home / ".config/broomva/role/events.jsonl").read_text().splitlines()[-1])
    assert ev["error"] == "RuntimeError"


def test_no_git_on_path_still_routes_the_prompt(repo, tmp_path):
    home = tmp_path / "h"
    p = subprocess.run([sys.executable, str(ROLE_X_PY), "intake", "--prompt", "Merge 1857",
                        "--workspace", str(repo)], capture_output=True, text=True, cwd=str(repo),
                       env={**os.environ, "HOME": str(home), "ROLE_X_OUTPUT": "reflex",
                            "PATH": str(tmp_path / "empty-bin")})
    ev = json.loads((home / ".config/broomva/role/events.jsonl").read_text().splitlines()[-1])
    assert p.returncode == 0 and "match-head-commit" in p.stdout and "error" not in ev


@pytest.mark.parametrize("output", ["legacy", "reflex"])
@pytest.mark.parametrize("payload", ["[1, 2]", "\"just a string\"", "{\"prompt\": 7}", ""])
def test_odd_payloads_never_fail_role_x_itself(repo, tmp_path, payload, output):
    """role-x.py's own exit code, not the hook wrapper's (which is always 0)."""
    p = subprocess.run([sys.executable, str(ROLE_X_PY), "intake", "--workspace", str(repo)], input=payload,
                       capture_output=True, text=True,
                       env={**os.environ, "HOME": str(tmp_path / "h"), "ROLE_X_OUTPUT": output})
    assert p.returncode == 0 and p.stdout == "", p.stderr


def test_reflex_events_do_not_count_as_lens_intakes(repo, tmp_path, usersite_env):
    home = tmp_path / "h"
    for _ in range(3):
        run_hook("Merge 1857", repo, home)
    events = home / ".config" / "broomva" / "role" / "events.jsonl"
    rx = load_module(ROLE_X_PY, "role_x_for_reflex_tests")
    assert rx._read_events_since(events, 3600) == []


# -------------------------------------------------------------- qbar output

META_WITH_ENTITIES = """---
name: _meta
status: active
extends: null
signals: {paths: [], prompt_keywords: [], branch_patterns: [], linear_labels: []}
context_loaders:
  files: ["AGENTS.md"]
  entities: ["research/entities/persona/toolchain-bun-biome.md"]
  skills: []
  glob_hints: []
default_mode: augment
quality_bar:
  - "Wait (P9): after a push, `p9 watch <pr> --background`; never sleep on CI"
prompt_improvement_patterns: []
mode_escalation: {rewrite_when: [], decompose_when: []}
out_of_scope: []
related_lenses: []
created: 2026-05-13
updated: 2026-05-13
---
body
"""


def test_qbar_output_keeps_the_bar_and_drops_everything_else(tmp_path, usersite_env):
    ws = tmp_path / "ws"
    (ws / "roles").mkdir(parents=True)
    (ws / "AGENTS.md").write_text("# a\n", encoding="utf-8")
    (ws / "roles" / "_meta.md").write_text(META_WITH_ENTITIES, encoding="utf-8")
    ent = ws / "research" / "entities" / "persona" / "toolchain-bun-biome.md"
    ent.parent.mkdir(parents=True)
    ent.write_text("---\ncore_claim: bun and biome\n---\n", encoding="utf-8")
    full, _ = run_hook("push this branch and open the PR", ws, tmp_path / "h1", mode="")
    qbar, rows = run_hook("push this branch and open the PR", ws, tmp_path / "h2", mode="qbar")
    assert "Context files" in full.stdout and "Knowledge-graph constraints" in full.stdout
    assert qbar.stdout.startswith("[role-x intake")
    assert "p9 watch <pr> --background" in qbar.stdout and "Agents: apply" in qbar.stdout
    for dropped in ("Context files", "Knowledge-graph constraints", "Task-relevant knowledge", "bun and biome"):
        assert dropped not in qbar.stdout
    assert rows[-1]["render"] == "qbar"


def _lens_workspace(tmp_path) -> Path:
    ws = tmp_path / "ws"
    (ws / "roles").mkdir(parents=True)
    (ws / "AGENTS.md").write_text("# a\n", encoding="utf-8")
    (ws / "roles" / "_meta.md").write_text(META_WITH_ENTITIES, encoding="utf-8")
    ent = ws / "research" / "entities" / "persona" / "toolchain-bun-biome.md"
    ent.parent.mkdir(parents=True)
    ent.write_text("---\ncore_claim: bun and biome\n---\n", encoding="utf-8")
    return ws


@pytest.mark.skipif(REPO is None, reason="needs the broomva/skills monorepo and its main branch")
def test_the_legacy_block_is_byte_for_byte_main_s(tmp_path):
    """Default output, pinned: this branch's role-x.py and main's print the same
    block for the same workspace and prompt, with the flag unset."""
    main_src = subprocess.run(["git", "-C", str(REPO), "show", "main:skills/orchestration/role-x/scripts/role-x.py"],
                              capture_output=True, text=True)
    if main_src.returncode != 0:
        pytest.skip("main is not available in this checkout")
    old = tmp_path / "main-scripts" / "role-x.py"
    old.parent.mkdir()
    old.write_text(main_src.stdout, encoding="utf-8")
    ws = _lens_workspace(tmp_path)
    outs = []
    for script in (old, ROLE_X_PY):
        env = {k: v for k, v in os.environ.items() if k not in ("ROLE_X_OUTPUT", "ROLE_X_MODE")}
        env["HOME"] = str(tmp_path / f"h-{script.parent.name}")
        p = subprocess.run([sys.executable, str(script), "intake", "--workspace", str(ws), "--prompt",
                            "push this branch and open the PR, then let me know"], capture_output=True, text=True,
                           env=env)
        assert p.returncode == 0, p.stderr
        outs.append(p.stdout)
    assert outs[0] and outs[0] == outs[1]


def test_the_legacy_block_matches_the_golden_taken_from_main(tmp_path):
    """Default output, pinned in CI too: fixtures/legacy-block.golden.txt is main's
    role-x.py output for this workspace and prompt (generated at 0618873's base)."""
    ws = _lens_workspace(tmp_path)
    env = {k: v for k, v in os.environ.items() if k not in ("ROLE_X_OUTPUT", "ROLE_X_MODE")}
    env["HOME"] = str(tmp_path / "h")
    p = subprocess.run([sys.executable, str(ROLE_X_PY), "intake", "--workspace", str(ws), "--prompt",
                        "push this branch and open the PR, then let me know"], capture_output=True, text=True,
                       env=env)
    assert p.returncode == 0, p.stderr
    assert p.stdout == (SKILL_DIR / "tests" / "fixtures" / "legacy-block.golden.txt").read_text(encoding="utf-8")


def test_an_unrecognised_output_value_is_recorded_not_silent(tmp_path, usersite_env):
    ws = _lens_workspace(tmp_path)
    p, rows = run_hook("push this branch and open the PR", ws, tmp_path / "h", mode="quality-bar")
    assert p.stdout.startswith("[role-x intake")  # legacy, as documented
    assert rows[-1]["output_ignored"] == "quality-bar"


@pytest.mark.skipif(REPO is None, reason="needs the broomva/skills monorepo")
def test_every_routed_entry_clears_the_sealed_held_out_m3_gate():
    """Spec §5.5 M3, enforced: an entry routes only at held-out recall >= 0.60 with
    <= 0.20 false fires, on the cases sealed at a272659 before any tuning."""
    heldout = SKILL_DIR / "evals" / "reflex-routing-heldout.json"
    p = subprocess.run([sys.executable, str(ROLE_X_PY), "reflexes", "route", "--heldout", "--json"],
                       capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr
    rows = {r["id"]: r for r in json.loads(p.stdout)["ids"]}
    cases = json.loads(heldout.read_text(encoding="utf-8"))["cases"]
    assert set(cases) <= set(BY_ID) | set(CAT.routes)
    for r in CAT.reflexes:
        if r.routed:
            assert r.id in rows, f"{r.id} is routed but has no sealed held-out cases"
            assert rows[r.id]["passes_m3"], f"{r.id} is routed but fails M3: {rows[r.id]}"
    assert rows["change_work"]["passes_m3"]


def test_the_sealed_held_out_file_is_the_one_that_was_sealed():
    import hashlib
    heldout = SKILL_DIR / "evals" / "reflex-routing-heldout.json"
    assert hashlib.sha256(heldout.read_bytes()).hexdigest() == (
        "3628de8859624ac6f7f6d3fc01211cb9524f64fcd547c3fc5fe54f86bb3089d9")


# ------------------------------------------------------------------ mutation

#: For each state predicate: a scenario that fires a reflex ONLY through that
#: predicate, so removing the predicate must make the scenario fail.
def _scn_just_pushed(repo, mod):
    pushed_feature(repo)
    return mod.State(cwd=repo, ctx_loader=no_board), NEUTRAL, "p9.watch-after-push"


def _scn_on_protected(repo, mod):
    return mod.State(cwd=repo, ctx_loader=no_board), "fix the typo in README.md", "p10.branch-first"


def _scn_staged(repo, mod):
    (repo / "README.md").write_text("# changed\n", encoding="utf-8")
    git(repo, "add", "README.md")
    return mod.State(cwd=repo, ctx_loader=no_board), NEUTRAL, "p10.branch-first"


def _scn_peer(repo, mod):
    git(repo, "switch", "-q", "-c", "feat/x")
    return (mod.State(cwd=repo, session_id="me", ctx_loader=lambda: fake_ctx([row("p1")])),
            "pull origin/main into it", "ctx.live-peer-before-git-op")


def _scn_in_repo(repo, mod):
    # on main, clean: only the change_work clause (gated by in_git_repo) can fire p9
    return mod.State(cwd=repo, ctx_loader=no_board), "refactor the parser", "p9.watch-after-push"


def _scn_unshipped(repo, mod):
    git(repo, "switch", "-q", "-c", "feat/y")
    commit(repo, "y.txt")  # no upstream: the commit exists nowhere else
    return mod.State(cwd=repo, ctx_loader=no_board), "go", "p9.watch-after-push"


SCENARIOS = {
    "in_git_repo": _scn_in_repo,
    "unshipped_work": _scn_unshipped,
    "branch_pushed_recently": _scn_just_pushed,
    "on_default_branch": _scn_on_protected,
    "staged_on_default_branch": _scn_staged,
    "live_peer_on_branch": _scn_peer,
}


def _scenario_fires(mod, catalog_path, repo, name) -> bool:
    state, prompt, rid = SCENARIOS[name](repo, mod)
    cat = all_routed(mod, mod.load_catalog(catalog_path))
    return rid in [f.reflex.id for f in mod.route(prompt, state, cat)]


def test_every_predicate_has_a_scenario():
    assert set(SCENARIOS) == set(rr.STATE_PREDICATES)


@needs_ctx
@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_scenario_fires_with_the_real_router(repo, name):
    assert _scenario_fires(rr, CATALOG, repo, name)


def _mutant(tmp_path, name, how):
    src = ROUTER_PY.read_text(encoding="utf-8")
    entry = f'    "{name}": _'
    assert src.count(entry) == 1, "the registry line moved: update this mutation"
    if how == "deleted":
        src = re.sub(rf'^    "{name}": _\w+,\n', "", src, count=1, flags=re.M)
    else:  # always false
        src = re.sub(rf'^(    "{name}": )_\w+,', r"\1lambda s: (False, ''),", src, count=1, flags=re.M)
    path = tmp_path / f"mutant_{name}_{how}.py"
    path.write_text(src, encoding="utf-8")
    return load_module(path, f"mutant_{name}_{how}")


@needs_ctx
@pytest.mark.parametrize("how", ["deleted", "always-false"])
@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_mutating_a_predicate_fails_its_scenario(repo, tmp_path, name, how):
    mod = _mutant(tmp_path, name, how)
    if how == "deleted":
        with pytest.raises(mod.CatalogError, match="unknown state predicate"):
            _scenario_fires(mod, CATALOG, repo, name)
    else:
        assert not _scenario_fires(mod, CATALOG, repo, name)

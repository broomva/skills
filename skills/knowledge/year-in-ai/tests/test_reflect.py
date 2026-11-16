"""The reflect layer: episodes, the digest quote gate, the outcome join and the reflection lint.

Every fixture here is synthetic. No real transcript text belongs in this repo.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(TESTS))

from test_read_failures import file_access_outside_helpers  # noqa: E402
from test_reader_contract import T0, iso, write_jsonl  # noqa: E402

from yia import ledger as LEDGER  # noqa: E402
from yia.ledger import sources as S  # noqa: E402
from yia.reflect import digest as D  # noqa: E402
from yia.reflect import episodes as EP  # noqa: E402
from yia.reflect import lint as LINT  # noqa: E402
from yia.reflect import outcomes as OUT  # noqa: E402
from yia.reflect import traces as TR  # noqa: E402

WINDOW = (T0 - 30 * 86400, T0 + 30 * 86400)
FIRST = "Build the login page for ABC-12 and open a pull request when the tests pass"
CORRECTION = "no, use the existing auth helper instead of writing a new one"
LAST = "ship it once the checks are green"
AGENT = "You are the fleet coordinator. Run the nightly sweep across every repository."


def _user(uuid, ts, text, entry="cli"):
    return {"type": "user", "uuid": uuid, "entrypoint": entry, "timestamp": iso(ts), "cwd": "/work/acme-app",
            "gitBranch": "feature/abc-12-login", "message": {"content": text}}


def _assistant(uuid, ts, blocks, entry="cli"):
    return {"type": "assistant", "uuid": uuid, "entrypoint": entry, "timestamp": iso(ts), "cwd": "/work/acme-app",
            "gitBranch": "feature/abc-12-login", "message": {"content": blocks}}


def build_stores(root: Path) -> Path:
    """A person's session (s1), an agent's session (s2) and a session outside the window (s3)."""
    projects = root / "projects"
    s1 = [
        _user("u1", T0, FIRST),
        _assistant("a1", T0 + 5, [{"type": "tool_use", "id": "t1", "name": "Skill",
                                   "input": {"skill": "autonomous"}},
                                  {"type": "tool_use", "id": "t2", "name": "Bash", "input": {"command": "npm test"}}]),
        _user("u1r", T0 + 6, [{"type": "tool_result", "tool_use_id": "t2", "is_error": True, "content": "1 failed"}]),
        _assistant("a2", T0 + 9, [{"type": "text", "text": "Opened https://github.com/acme/app/pull/7 for review."}]),
        _user("u2", T0 + 600, CORRECTION),
        _assistant("a3", T0 + 605, [{"type": "text", "text": "Switched to the existing helper."}]),
        _user("u3", T0 + 700, "[Request interrupted by user]"),
        _user("u4", T0 + 900, LAST),
        _assistant("a4", T0 + 905, [{"type": "text", "text": "Merged."}]),
    ]
    write_jsonl(projects / "-work-acme-app" / "s1.jsonl", s1)
    s2 = [_user("v1", T0 + 50, AGENT, entry="sdk-cli"),
          _assistant("v2", T0 + 55, [{"type": "text", "text": "Sweep done."}], entry="sdk-cli")]
    write_jsonl(projects / "-work-acme-app" / "s2.jsonl", s2)
    s3 = [_user("w1", T0 - 400 * 86400, "an old question from last year"),
          _assistant("w2", T0 - 400 * 86400 + 5, [{"type": "text", "text": "an old answer"}])]
    write_jsonl(projects / "-work-acme-app" / "s3.jsonl", s3)
    return projects


def build_episodes(tmp_path):
    projects = build_stores(tmp_path)
    readers = [S.read_claude_projects([projects], None)]
    c, sink, _reports = EP.collect({}, WINDOW, None, None, readers=readers)
    wanted = {r["sess"] for r in c.human_kept if c.in_window(r["ts"])}
    metas, _ = TR.session_meta({"claude_projects": [projects]}, wanted)
    return EP.build(c, sink, metas, -5.0), c


# ------------------------------------------------------------------ episodes


def test_an_episode_holds_the_persons_session_and_nothing_else(tmp_path):
    eps, _c = build_episodes(tmp_path)
    assert len(eps) == 1
    e = eps[0]
    assert e["id"] == "e-" + LEDGER.opaque("s1")[:8]
    assert [p["text"] for p in e["prompts"]] == [FIRST, CORRECTION, LAST]
    assert e["replies"][0]["text"].startswith("Opened https://github.com/acme/app/pull/7")
    assert e["repo"] == "acme-app" and e["branch"] == "feature/abc-12-login"
    assert e["tickets"] == ["ABC-12"] and e["prs"] == ["https://github.com/acme/app/pull/7"]
    assert e["skills"] == {"autonomous": 1}
    assert e["tool_errors"] == 1 and e["interrupts"] == 1


def test_who_wrote_a_prompt_comes_from_the_ledger_classification(tmp_path):
    eps, c = build_episodes(tmp_path)
    texts = [p["text"] for e in eps for p in e["prompts"]]
    assert AGENT not in texts  # sdk-cli is an agent author; the fold dropped it, so the episode does
    agent_rows = [r for r in c.prompts if r["author"] == "agent"]
    assert agent_rows and all(r["id"] not in c.human_ids for r in agent_rows)


def test_correction_markers_and_scores(tmp_path):
    eps, _ = build_episodes(tmp_path)
    e = eps[0]
    assert [c["i"] for c in e["corrections"]] == [1]
    assert e["prompts"][1]["correction"] and not e["prompts"][0]["correction"]
    assert e["score"]["corrections"] == 2  # one redirecting prompt and one interrupt
    assert "most-corrected" in e["sampled"] and "longest" in e["sampled"] and e["trace"]


def test_tracker_prefixes_are_letters_seen_often_or_in_a_branch():
    eps = [{"tickets": [f"XYZ-{n}" for n in range(5)] + [f"E1-{n}" for n in range(9)] + ["ONE-1"],
            "branch": None},
           {"tickets": ["ABC-12"], "branch": "feature/abc-12-login"}]
    assert EP.tracker_prefixes(eps) == {"XYZ", "ABC"}


def test_a_path_is_not_a_slash_command():
    assert EP._SLASH.match("/checkit https://example.com").group(1) == "/checkit"
    assert EP._SLASH.match("/arc") and not EP._SLASH.match("/Users/someone/file.md please read")


def test_a_first_prompt_is_never_a_correction():
    assert EP.is_correction("no, that is wrong") == "no,"
    assert EP.is_correction("Please build a dashboard; do not use a chart library") is None


def test_the_text_tap_never_reaches_a_row(tmp_path):
    projects = build_stores(tmp_path)
    plain = list(S.read_claude_projects([projects], None)[1])
    seen = []
    with LEDGER.text_tap(lambda row, text, own: seen.append(text)):
        tapped = list(S.read_claude_projects([projects], None)[1])
    assert [r["id"] for r in plain] == [r["id"] for r in tapped]
    assert FIRST in seen and not LEDGER._TAPS
    blob = json.dumps(tapped)
    assert "login page" not in blob and "auth helper" not in blob


def test_trace_and_episode_modules_read_files_only_through_the_reporting_helpers():
    for name in ("traces.py", "episodes.py"):
        assert file_access_outside_helpers((SCRIPTS / "yia" / "reflect" / name).read_text()) == [], name
    offenders = file_access_outside_helpers((SCRIPTS / "yia" / "reflect" / "outcomes.py").read_text())
    assert [o for o in offenders if not o.startswith("run:")] == []


# ------------------------------------------------------------------- digests


def _digest(e, **over):
    d = {"episode": e["id"], "hash": e["hash"], "goal": "Ship the login page", "topics": ["auth", "login"],
         "kind": "build", "steering": "corrective", "steering_note": "redirected to an existing helper",
         "obstacle": "a failing test", "resolution": "reused the helper", "ideas": ["reuse before writing"],
         "outcome": {"status": "shipped", "evidence": "https://github.com/acme/app/pull/7"},
         "quote": "use the existing auth helper instead of writing a new one"}
    d.update(over)
    return d


def test_a_verbatim_quote_passes(tmp_path):
    e = build_episodes(tmp_path)[0][0]
    assert D.validate(_digest(e), e) == []
    assert D.validate(_digest(e, quote="use the  existing auth\nhelper"), e) == []  # whitespace is not wording


@pytest.mark.parametrize("quote", ["use the existing auth module instead",  # paraphrase
                                   "Switched to the existing helper",  # the agent's words, not the user's
                                   "USE THE EXISTING AUTH HELPER"])  # not verbatim
def test_a_quote_not_in_the_users_prompts_is_rejected(tmp_path, quote):
    e = build_episodes(tmp_path)[0][0]
    assert "quote is not verbatim from the user's prompts in this episode" in D.validate(_digest(e, quote=quote), e)


def test_a_stale_or_malformed_digest_is_rejected(tmp_path):
    e = build_episodes(tmp_path)[0][0]
    assert any("stale" in m for m in D.validate(_digest(e, hash="0" * 16), e))
    assert any("kind" in m for m in D.validate(_digest(e, kind="vibes"), e))
    assert any("missing field" in m for m in D.validate({"episode": e["id"]}, e))


# ------------------------------------------------------------------ the join


def test_the_join_reports_absent_sources_and_continues(tmp_path):
    e = build_episodes(tmp_path)[0][0]
    e["harness_prs"] = {"https://github.com/acme/app/pull/7": {"state": "merged", "title": "Login (ABC-12)"}}
    gh, prs = OUT.github_prs(2026, runner=lambda cmd: (False, "gh not found"))
    git, more = OUT.git_prs([str(tmp_path / "gone")], 2026)
    linear, states = OUT.linear_states(None)
    kg, entities = OUT.kg_entities(str(tmp_path / "no-kg"))
    sources = {"github": gh, "git": git, "linear": linear, "kg": kg}
    result = OUT.join([e], sources, prs + more, states, entities)
    for name in sources:
        assert result["sources"][name]["available"] is False and result["sources"][name]["reason"]
    linked = result["episodes"][e["id"]]
    assert [p["url"] for p in linked["merged_prs"]] == ["https://github.com/acme/app/pull/7"]
    assert linked["merged_prs"][0]["via"] == ["harness"] and linked["kg"] == []


def test_the_join_links_by_mention_branch_ticket_and_kg(tmp_path):
    e = build_episodes(tmp_path)[0][0]
    e["cwd"] = "/work/app"  # the episode ran in acme/app (its git remote, stubbed below)
    prs = [{"url": "https://github.com/acme/app/pull/7", "title": "feat: login (ABC-12)", "merged_at": iso(T0 + 3600),
            "branch": "feature/abc-12-login", "repo": "acme/app"},
           {"url": "https://github.com/acme/app/pull/9", "title": "fix: ABC-12 follow-up",
            "merged_at": iso(T0 + 86400), "branch": "fix/other", "repo": "acme/app"},
           {"url": "https://github.com/acme/app/pull/99", "title": "ABC-12 long after",
            "merged_at": iso(T0 + 90 * 86400), "branch": "late", "repo": "acme/app"}]
    kg_dir = tmp_path / "entities" / "concept"
    kg_dir.mkdir(parents=True)
    (kg_dir / "login-flow.md").write_text("---\ncreated: \"2026-10-26\"\n---\nTracked in ABC-12.\n")
    kg, entities = OUT.kg_entities(str(tmp_path / "entities"))
    result = OUT.join([e], {"kg": kg}, prs, {}, entities,
                      repo_of=lambda cwd: "acme/app" if cwd == "/work/app" else None)["episodes"][e["id"]]
    vias = {p["url"].rsplit("/", 1)[1]: p["via"] for p in result["merged_prs"]}
    assert vias == {"7": ["mention", "branch", "ticket"], "9": ["ticket"]}
    assert result["kg"] == [{"slug": "login-flow", "type": "concept", "via": "ticket"}]


def test_only_session_links_count_as_the_episodes_outcome(tmp_path):
    from yia.reflect import reduce as RED
    e = build_episodes(tmp_path)[0][0]
    shared = {"episodes": {e["id"]: {"merged_prs": [{"url": "u9", "via": ["ticket"]}], "kg": []}}}
    own = {"episodes": {e["id"]: {"merged_prs": [{"url": "u7", "via": ["branch", "ticket"]}], "kg": []}}}
    a = RED.payload(2026, [e], {}, shared, {})["outcomes"]
    b = RED.payload(2026, [e], {}, own, {})["outcomes"]
    assert (a["episodes_with_merged_pr"], a["episodes_with_only_ticket_linked_pr"]) == (0, 1)
    assert (b["episodes_with_merged_pr"], b["merged_prs_linked"]) == (1, 1)


# ------------------------------------------------------------------ the lint

EP_ID = "e-1a2b3c4d"
EPISODES = {EP_ID: {"id": EP_ID, "prompts": [{"text": "make the ledger never hold a single word of text"}]},
            "e-99999999": {"id": "e-99999999", "prompts": [{"text": "ship the deck before the video"}]}}
DATA = {"year": 2026, "totals": {"episodes": 1125, "prompts": 8150, "authored_words": 216004},
        "kinds": [{"name": "build", "count": 412, "pct": 37}]}
GOOD = """---
title: test
---
# The year

## Monthly arcs

- March opened with 1,125 episodes of ledger work [e-1a2b3c4d].

## Themes and ideas

Privacy was a theme: "make the ledger never hold a single word of text" [e-1a2b3c4d].

> make the ledger never hold a single word of text [e-1a2b3c4d]

## How you worked with agents

Building was 37% of the work, about 216K words of prompts [e-1a2b3c4d, e-99999999].

## Challenges and outcomes

- In 2026-03 the ledger shipped. [e-1a2b3c4d]

## Insights for next year

Ship the deck first, as on 2026-03-02 [e-99999999].

## Data notes

Python `3.9` runs the scheduled harvest; 8,150 prompts were measured.
"""


def test_a_cited_reflection_passes():
    errors, stats = LINT.lint(GOOD, EPISODES, DATA)
    assert errors == []
    assert stats["quotes"] == 2 and stats["cited"] == stats["claims"] - 1


def test_an_uncited_claim_fails():
    bad = GOOD.replace("Ship the deck first, as on 2026-03-02 [e-99999999].", "Ship the deck first.")
    errors, _ = LINT.lint(bad, EPISODES, DATA)
    assert any("uncited claim" in e for e in errors)


def test_a_citation_that_does_not_resolve_fails():
    errors, _ = LINT.lint(GOOD.replace("[e-99999999].", "[e-deadbeef]."), EPISODES, DATA)
    assert any("e-deadbeef does not resolve" in e for e in errors)


@pytest.mark.parametrize("old,new", [
    ('"make the ledger never hold a single word of text"', '"make the ledger hold no text at all"'),
    ("> make the ledger never hold a single word of text", "> keep the ledger free of any text"),
    ('"make the ledger never hold a single word of text" [e-1a2b3c4d]',
     '"ship the deck before the video" [e-1a2b3c4d]'),  # verbatim, but from an episode it does not cite
])
def test_a_quote_that_is_not_verbatim_from_a_cited_prompt_fails(old, new):
    errors, _ = LINT.lint(GOOD.replace(old, new, 1), EPISODES, DATA)
    assert any("quote is not verbatim" in e for e in errors)


@pytest.mark.parametrize("old,new", [("1,125 episodes", "1,126 episodes"), ("37%", "38%"),
                                     ("216K words", "217K words"), ("8,150 prompts", "8,151 prompts")])
def test_a_number_not_in_the_payload_fails(old, new):
    errors, _ = LINT.lint(GOOD.replace(old, new), EPISODES, DATA)
    assert any("is not in the data payload" in e for e in errors)


def test_a_missing_chapter_fails():
    errors, _ = LINT.lint(GOOD.replace("## Insights for next year", "## Other"), EPISODES, DATA)
    assert "missing section: Insights for next year" in errors


# ---------------------------------------------------------------- end to end


def _cli(tmp_path, *args):
    env = dict(os.environ, HOME=str(tmp_path / "home"))
    return subprocess.run([sys.executable, str(SCRIPTS / "year_in_ai.py"), "reflect", *args, "--year", "2026",
                           "--dir", str(tmp_path / "reflect"), "--no-defaults", "--no-ledger"],
                          capture_output=True, text=True, env=env)


def test_the_pipeline_runs_privately_end_to_end(tmp_path):
    projects = build_stores(tmp_path)
    run = _cli(tmp_path, "episodes", "--root", f"claude_projects={projects}")
    assert run.returncode == 0, run.stderr
    out = tmp_path / "reflect" / "2026"
    assert stat.S_IMODE(out.stat().st_mode) == 0o700
    assert stat.S_IMODE((out / "episodes.jsonl").stat().st_mode) == 0o600
    batch = json.loads((out / "batches" / "batch-001.json").read_text())
    (e,) = batch["episodes"]
    assert [p["text"] for p in e["prompts"]] == [FIRST, CORRECTION, LAST] and e["trace_sample"]["events"]

    full = json.loads((out / "episodes.jsonl").read_text().splitlines()[0])
    (out / "digests").mkdir()
    (out / "digests" / f"{e['id']}.json").write_text(json.dumps(_digest(full, quote="open a pull request")))
    assert _cli(tmp_path, "check", "--batch", "1").returncode == 0
    (out / "digests" / f"{e['id']}.json").write_text(json.dumps(_digest(full, quote="open a merge request")))
    bad = _cli(tmp_path, "check", "--batch", "1")
    assert bad.returncode == 1 and "not verbatim" in bad.stdout

    (out / "digests" / f"{e['id']}.json").write_text(json.dumps(_digest(full, quote="open a pull request")))
    joined = _cli(tmp_path, "join", "--no-github", "--kg", str(tmp_path / "missing"))
    assert joined.returncode == 0 and "absent" in joined.stdout and "kg" in joined.stdout
    assert _cli(tmp_path, "reduce").returncode == 0
    data = json.loads((out / "data.json").read_text())
    assert data["totals"]["episodes"] == 1 and data["totals"]["episodes_digested"] == 1
    assert (out / "months" / "2026-10.md").is_file()

    eid = e["id"]
    (out / "reflection.md").write_text(GOOD.replace("e-1a2b3c4d", eid).replace("e-99999999", eid)
                                       .replace("make the ledger never hold a single word of text",
                                                "open a pull request when the tests pass")
                                       .replace("1,125 episodes", "1 episode").replace("37%", "100%")
                                       .replace(", about 216K words of prompts", "")
                                       .replace("8,150 prompts", "3 prompts"))
    lint = _cli(tmp_path, "lint")
    assert lint.returncode == 0, lint.stdout
    (out / "reflection.md").write_text((out / "reflection.md").read_text()
                                       .replace("## Data notes", "An unsupported claim.\n\n## Data notes"))
    assert _cli(tmp_path, "lint").returncode == 1

    shared = _cli(tmp_path, "share")
    assert shared.returncode == 0
    text = (out / "reflection.share.md").read_text()
    assert "open a pull request when the tests pass" not in text and "«quote removed»" in text


# --- P20 review of 5939467 (Codex)


def test_a_branch_name_in_another_repository_is_not_the_sessions_outcome(tmp_path):
    from yia.reflect import reduce as RED
    e = build_episodes(tmp_path)[0][0]
    e["cwd"], e["repo"] = "/work/repo-a", "repo-a"
    pr = {"url": "https://github.com/example/repo-b/pull/7", "title": "unrelated", "merged_at": iso(T0 + 3600),
          "branch": "feature/login", "repo": "example/repo-b"}
    e["branch"], e["tickets"] = "feature/login", []
    linked = OUT.join([e], {}, [pr], {}, [], repo_of=lambda cwd: "example/repo-a")["episodes"][e["id"]]
    assert linked["merged_prs"][0]["via"] == ["branch-name"]
    assert RED.STRONG_VIA.isdisjoint(linked["merged_prs"][0]["via"])


def test_share_removes_every_quoted_span_however_short():
    from yia.reflect import share as SH
    out = SH.redact('The user said "secret phrase" and \u201cAcme\u201d [e-12345678].\n')
    assert "secret phrase" not in out and "Acme" not in out and out.count(SH.QUOTE_REMOVED) == 2


@pytest.mark.parametrize("table", [
    "| 999 users were served without evidence | x |\n|---|---|\n",
    "| Company lied | Users harmed |\n|---|---|\n",
    "| --- | 999 users served |\n",
    "| Month | Episodes |\n|---|---|\n| 2026-03 | 12 |\n",
])
def test_any_table_fails_the_lint(table):
    from yia.reflect import lint as LINT
    _claims, _headings, errors = LINT.units("## Monthly arcs\n\n" + table)
    assert any("tables are not allowed" in err for err in errors)


def test_a_directory_named_like_the_repo_is_not_the_repo(tmp_path):
    e = build_episodes(tmp_path)[0][0]
    e["cwd"], e["repo"], e["branch"], e["tickets"] = "/work/app/other", "other", "feature/login", []
    pr = {"url": "https://github.com/example/app/pull/3", "title": "x", "merged_at": iso(T0 + 3600),
          "branch": "feature/login", "repo": "example/app"}
    linked = OUT.join([e], {}, [pr], {}, [], repo_of=lambda cwd: "example/other")["episodes"][e["id"]]
    assert linked["merged_prs"][0]["via"] == ["branch-name"]


def test_a_branch_name_link_is_not_counted_as_ticket_linked(tmp_path):
    from yia.reflect import reduce as RED
    e = build_episodes(tmp_path)[0][0]
    joined = {e["id"]: {"merged_prs": [{"url": "u", "via": ["branch-name"]}], "kg": []}}
    data = RED.payload(2026, [e], {}, {"episodes": joined, "sources": {}}, {})
    assert data["outcomes"]["episodes_with_only_ticket_linked_pr"] == 0
    assert data["outcomes"]["episodes_with_merged_pr"] == 0


def test_share_removes_single_quotes_code_and_unquoted_copied_runs():
    from yia.reflect import share as SH
    prompt = "please make the onboarding flow for the acme pilot work by friday"
    out = SH.redact("Single 'secret phrase', code `private prompt words`, and the user asked to make the "
                    "onboarding flow for the acme pilot work soon [e-12345678]. It isn't hard.\n", (), [prompt])
    for leaked in ("secret phrase", "private prompt words", "onboarding flow for the acme pilot"):
        assert leaked not in out, out
    assert "isn't hard" in out  # an apostrophe is not a quote


def test_a_null_digest_is_invalid_not_missing(tmp_path):
    from yia.reflect import digest as DG
    e = build_episodes(tmp_path)[0][0]
    out = tmp_path / "reflect"
    path = DG.digest_path(out, e["id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("null")
    errors, missing, _valid = DG.status(out, [e])
    assert errors[e["id"]] == ["digest is not a JSON object"] and missing == []


def test_a_digest_that_is_not_an_object_is_an_error_not_a_crash(tmp_path):
    from yia.reflect import digest as DG
    e = build_episodes(tmp_path)[0][0]
    out = tmp_path / "reflect"
    path = DG.digest_path(out, e["id"]) if hasattr(DG, "digest_path") else None
    assert path is not None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[]")
    errors, missing, valid = DG.status(out, [e])
    assert errors[e["id"]] == ["digest is not a JSON object"] and not valid


# --- CodeRabbit on 7e21863


def test_a_scaled_figure_needs_a_scaled_value():
    from yia.reflect import lint as LINT
    assert not LINT.number_supported(("2", "", "K"), [2])
    assert LINT.number_supported(("2", "", "K"), [2000])
    assert LINT.number_supported(("2", "", ""), [2])


def test_a_kg_entity_citing_the_same_pr_url_is_linked(tmp_path):
    e = build_episodes(tmp_path)[0][0]
    url = "https://github.com/acme/app/pull/42"
    e["prompts"].append({"ts": e["first"], "text": f"see {url}"})
    e["tickets"] = []
    entity = {"slug": "app-pr-42", "type": "decision", "created": None, "tickets": [], "urls": [url]}
    linked = OUT.join([e], {}, [], {}, [entity], repo_of=lambda cwd: None)["episodes"][e["id"]]
    assert any(k["slug"] == "app-pr-42" for k in linked["kg"])


def test_the_median_of_an_even_count_is_the_mean_of_the_middle_two():
    from yia.reflect import reduce as RED
    assert RED._median([1, 9]) == 5 and RED._median([1, 2, 9]) == 2 and RED._median([1, 2]) == 1.5


def test_stale_month_packets_are_removed(tmp_path):
    from yia.reflect import reduce as RED
    eps = build_episodes(tmp_path)[0]
    out = tmp_path / "reflect-out"
    (out / "months").mkdir(parents=True)
    (out / "months" / "2025-01.md").write_text("old")
    RED.write(out, 2026, eps, {}, {"episodes": {}, "sources": {}}, {})
    assert not (out / "months" / "2025-01.md").exists()
    assert {p.stem for p in (out / "months").glob("*.md")} == {e["month"] for e in eps}


@pytest.mark.parametrize("path", ["/workspace/acme/private", "/srv/data/x", "/mnt/disk/notes.md", "~/notes/a.md"])
def test_share_removes_paths_under_any_root(path):
    from yia.reflect import share as SH
    assert path not in SH.redact(f"Worked in {path} today [e-12345678].\n")


def test_share_keeps_a_lone_slash_command():
    from yia.reflect import share as SH
    assert "/checkit" in SH.redact("Ran /checkit often [e-12345678].\n")


def test_a_redact_term_with_punctuation_is_masked():
    from yia.reflect import share as SH
    out = SH.redact("Worked on Project X (confidential) today [e-12345678].\n", ["Project X (confidential)"])
    assert "confidential" not in out


# --- P20 round 3 (Codex, 7e21863)


def test_a_copied_run_split_across_lines_is_removed():
    from yia.reflect import share as SH
    prompt = "Please use the secret violet comet password now."
    out = SH.redact("Notes: please use the secret\nviolet comet password now [e-12345678].\n", (), [prompt])
    assert "violet comet" not in out and out.count("\n") == 2


def test_text_after_a_closed_comment_is_linted():
    from yia.reflect import lint as LINT
    claims, _headings, _errors = LINT.units("## Monthly arcs\n\n<!-- note --> The company lied.\n")
    assert [c["text"] for c in claims] == ["The company lied."]


@pytest.mark.parametrize("doc,expected", [
    ("Company lied | Users harmed\n--- | ---\nfalse | claims [e-1a2b3c4d]\n", "tables are not allowed"),
    ("<details>hidden claim [e-1a2b3c4d]</details>\n", "HTML are not allowed"),
    ("[^1]: a footnote claim [e-1a2b3c4d]\n", "footnotes are not allowed"),
    ("Term [e-1a2b3c4d]\n\n: a definition claim [e-1a2b3c4d]\n", "definition lists are not allowed"),
    ("<!-- unclosed\nThe company lied.\n", "unclosed HTML comment"),
])
def test_structures_that_hide_or_reshape_claims_are_errors(doc, expected):
    from yia.reflect import lint as LINT
    _claims, _headings, errors = LINT.units("## Monthly arcs\n\n" + doc)
    assert any(expected in err for err in errors), errors


@pytest.mark.parametrize("remote,slug", [
    ("https://github.com/example/app.git", "example/app"),
    ("git@github.com:example/app.git", "example/app"),
    ("ssh://git@github.com/example/app", "example/app"),
    ("https://evilgithub.com/example/app.git", None),
    ("https://github.com.evil.io/example/app.git", None),
])
def test_only_github_itself_is_a_github_remote(remote, slug):
    assert OUT.parse_remote(remote) == slug


def test_share_says_it_is_a_review_draft(tmp_path):
    import json, os, subprocess, sys
    root = tmp_path / "reflect" / "2026"
    root.mkdir(parents=True)
    (root / "episodes.jsonl").write_text(json.dumps({"id": "e-12345678", "prompts": [{"text": "hello there"}],
                                                     "replies": []}) + "\n")
    (root / "reflection.md").write_text("A line [e-12345678].\n")
    run = subprocess.run([sys.executable, str(SCRIPTS / "year_in_ai.py"), "reflect", "share", "--year", "2026",
                          "--dir", str(tmp_path / "reflect")], capture_output=True, text=True,
                         env=dict(os.environ, HOME=str(tmp_path / "home")))
    assert run.returncode == 0, run.stderr
    assert "REVIEW DRAFT" in run.stdout and "not share-safe" in run.stdout


# --- CodeRabbit follow-ups on e84061d


def test_month_cleanup_keeps_files_it_did_not_generate(tmp_path):
    from yia.reflect import reduce as RED
    eps = build_episodes(tmp_path)[0]
    out = tmp_path / "reflect-out"
    (out / "months").mkdir(parents=True)
    (out / "months" / "notes.md").write_text("mine")
    (out / "months" / "2025-01.md").write_text("old")
    RED.write(out, 2026, eps, {}, {"episodes": {}, "sources": {}}, {})
    assert (out / "months" / "notes.md").read_text() == "mine"
    assert not (out / "months" / "2025-01.md").exists()


def test_a_redact_term_is_masked_inside_other_words():
    from yia.reflect import share as SH
    assert "confidential" not in SH.redact("myProject X (confidential) today [e-12345678].\n",
                                            ["Project X (confidential)"])


def test_share_removes_a_path_whose_first_segment_has_punctuation():
    from yia.reflect import share as SH
    assert "secret" not in SH.redact("Read /data:private/secret today [e-12345678].\n")


def test_a_branch_name_link_is_not_described_as_sharing_a_ticket(tmp_path):
    from yia.reflect import reduce as RED
    e = build_episodes(tmp_path)[0][0]
    joined = {"merged_prs": [{"url": "https://github.com/x/y/pull/1", "via": ["branch-name"]},
                             {"url": "https://github.com/x/y/pull/2", "via": ["ticket"]}]}
    line = RED._line(e, _digest(e), joined)
    assert "merged PRs: none; 1 more merged PRs share a ticket" in line

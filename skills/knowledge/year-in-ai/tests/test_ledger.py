"""Tests for the harvest ledger, the attention fold and the archive.

Every store is built as a fixture in a temporary directory; nothing here reads
the operator's real history. Runs on Python 3.9+, because the scheduled harvest
runs under the system Python.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from yia.ledger import make_row, opaque, row_fields, text_hash, unwrap_command  # noqa: E402
from yia.ledger import archive as A  # noqa: E402
from yia.ledger import attention as T  # noqa: E402
from yia.ledger import sources as S  # noqa: E402
from yia.ledger import store as L  # noqa: E402

SECRET = "zebra-quartz-secret-phrase"
T0 = 1793000000.0  # 2026-10-26


def iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(ts))


# ----------------------------------------------------------------------- fixtures


def make_t3(path: Path) -> None:
    con = sqlite3.connect(path)
    con.execute("create table orchestration_v2_projection_threads (thread_id text, default_provider text, payload_json text)")
    con.execute("create table orchestration_v2_projection_messages (message_id text, thread_id text, run_id text, "
                "role text, streaming int, created_at text, payload_json text)")
    threads = [("top", "claudeAgent", {"lineage": {"relationshipToParent": None}}),
               ("child", "codex", {"lineage": {"relationshipToParent": "subagent"}})]
    for tid, prov, payload in threads:
        con.execute("insert into orchestration_v2_projection_threads values (?,?,?)", (tid, prov, json.dumps(payload)))
    msgs = [
        ("m1", "top", "r1", "user", T0, {"createdBy": "user", "creationSource": "web", "text": f"build the thing {SECRET}"}),
        ("m2", "top", "r1", "assistant", T0 + 10, {"createdBy": "agent", "text": "working"}),
        ("m3", "top", "r1", "assistant", T0 + 20, {"createdBy": "agent", "text": "done: here is the final answer " * 5}),
        ("m4", "top", "r2", "user", T0 + 100, {"createdBy": "agent", "text": "Delegated task finished"}),
        ("m5", "top", "r2", "assistant", T0 + 110, {"createdBy": "agent", "text": "noted the delegate result"}),
        ("m6", "child", "r3", "user", T0 + 200, {"createdBy": "user", "text": "subagent copy of a prompt"}),
    ]
    for mid, tid, run, role, ts, payload in msgs:
        con.execute("insert into orchestration_v2_projection_messages values (?,?,?,?,?,?,?)",
                    (mid, tid, run, role, 0, iso(ts), json.dumps(payload)))
    con.commit()
    con.close()


def write_jsonl(path: Path, records) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")


def make_claude(root: Path) -> None:
    cli = [
        {"type": "user", "uuid": "u1", "entrypoint": "cli", "timestamp": iso(T0),
         "message": {"content": "<command-message>autonomous</command-message>\n<command-name>/autonomous</command-name>\n"
                                "<command-args>ship the ledger</command-args>"}},
        {"type": "assistant", "uuid": "a1", "entrypoint": "cli", "timestamp": iso(T0 + 5),
         "message": {"content": [{"type": "text", "text": "Shipping."}, {"type": "tool_use", "name": "Bash"}]}},
        {"type": "user", "uuid": "t1", "entrypoint": "cli", "timestamp": iso(T0 + 6),
         "message": {"content": [{"type": "tool_result", "content": "ok"}]}},
        {"type": "assistant", "uuid": "a2", "entrypoint": "cli", "timestamp": iso(T0 + 9),
         "message": {"content": [{"type": "text", "text": "Shipped the ledger."}]}},
        {"type": "user", "uuid": "s1", "entrypoint": "cli", "isSidechain": True, "timestamp": iso(T0 + 10),
         "message": {"content": "subagent brief"}},
        {"type": "user", "uuid": "c1", "entrypoint": "cli", "timestamp": iso(T0 + 11),
         "message": {"content": "<command-name>/clear</command-name>"}},
    ]
    write_jsonl(root / "-proj" / "sess-cli.jsonl", cli)
    write_jsonl(root / "-proj" / "sess-p.jsonl", [
        {"type": "user", "uuid": "p1", "entrypoint": "sdk-cli", "timestamp": iso(T0 + 50),
         "message": {"content": "Read /x/runner.md and execute it to completion."}},
    ])
    write_jsonl(root / "-proj" / "sess-paseo.jsonl", [
        {"type": "user", "uuid": "q1", "entrypoint": "sdk-ts", "timestamp": iso(T0 + 60),
         "message": {"content": "orchestrator dispatch"}},
    ])


def make_codex(root: Path) -> None:
    def rollout(sid, originator, source, prompt, reply, ts):
        return [
            {"type": "session_meta", "timestamp": iso(ts), "payload": {"originator": originator, "source": source}},
            {"type": "event_msg", "timestamp": iso(ts + 1), "payload": {"type": "user_message", "message": prompt}},
            {"type": "event_msg", "timestamp": iso(ts + 2), "payload": {"type": "agent_message", "message": "thinking"}},
            {"type": "event_msg", "timestamp": iso(ts + 3), "payload": {"type": "task_complete", "last_agent_message": reply}},
        ]
    write_jsonl(root / "2026" / "10" / "rollout-a-0000000000000000000000000000000000aa.jsonl",
                rollout("aa", "Codex Desktop", "vscode", "refactor the parser please", "Parser refactored.", T0 + 300))
    write_jsonl(root / "2026" / "10" / "rollout-b-0000000000000000000000000000000000bb.jsonl",
                rollout("bb", "codex_exec", "exec", "review this diff", "LGTM", T0 + 400))
    sub = rollout("cc", "Codex Desktop", "vscode", "subagent", "x", T0 + 500)
    sub[0]["payload"]["source"] = {"subagent": {"thread_spawn": {}}}
    write_jsonl(root / "2026" / "10" / "rollout-c-0000000000000000000000000000000000cc.jsonl", sub)


def make_history(path: Path) -> None:
    write_jsonl(path, [
        {"display": "merge it", "timestamp": int((T0 + 600) * 1000), "project": "/p", "sessionId": "h1", "pastedContents": {}},
        {"display": "/usage", "timestamp": int((T0 + 610) * 1000), "project": "/p", "sessionId": "h1"},
        {"display": "probe", "timestamp": int((T0 + 620) * 1000), "project": "/Lib/CodexBar/Probe", "sessionId": "h2"},
        {"display": "look at this [Pasted text #1 +9 lines]", "timestamp": int((T0 + 630) * 1000), "project": "/p",
         "sessionId": "h1", "pastedContents": {"1": {"content": "LOG LINE\n" * 40}}},
    ])


def make_bridge(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "session-2026-10-26-abc.md").write_text(
        "---\ncreated: 2026-10-26\nsession_id: abc\n---\n\n"
        "> [!quote] **User** (10:15)\n> lets plan the recap\n\n"
        "> [!info] **Assistant**\n> Here is a plan.\n\n"
        "> [!quote] **User** (10:20)\n> [Fleet coordinator] resume the arc\n\n"
        "> [!info] **Assistant**\n> Resumed.\n", encoding="utf-8")


@pytest.fixture
def corpus(tmp_path):
    make_t3(tmp_path / "statev2.sqlite")
    make_claude(tmp_path / "claude")
    make_codex(tmp_path / "codex")
    make_history(tmp_path / "history.jsonl")
    make_bridge(tmp_path / "bridge")
    paseo = tmp_path / "paseo" / "ws"
    paseo.mkdir(parents=True)
    (paseo / "agent.json").write_text(json.dumps({"runtimeInfo": {"sessionId": "sess-paseo"}}))
    roots = {k: [] for k in L.DEFAULT_ROOTS}
    roots.update({
        "t3_db": [tmp_path / "statev2.sqlite"], "claude_projects": [tmp_path / "claude"],
        "codex_sessions": [tmp_path / "codex"], "claude_history": [tmp_path / "history.jsonl"],
        "bridged": [tmp_path / "bridge"], "paseo_agents": [tmp_path / "paseo"],
    })
    return tmp_path, roots


def harvest_rows(corpus_info):
    tmp, roots = corpus_info
    ledger = L.Ledger(str(tmp / "ledger"))
    entry = L.harvest(ledger, roots, since=None)
    return ledger, entry, list(ledger.rows())


# -------------------------------------------------------------------------- tests


def test_rows_never_hold_text(corpus):
    ledger, _entry, rows = harvest_rows(corpus)
    assert rows
    for row in rows:
        assert set(row) == set(row_fields())
    raw = "".join(p.read_text() for p in ledger.dir.glob("*.jsonl"))
    for phrase in (SECRET, "build the thing", "ship the ledger", "refactor the parser", "LOG LINE", "Parser refactored"):
        assert phrase not in raw


def test_t3_authors_come_from_created_by_and_subagents_are_skipped(corpus):
    _l, _e, rows = harvest_rows(corpus)
    t3 = [r for r in rows if r["src"] == "t3"]
    prompts = {r["author"] for r in t3 if r["kind"] == "prompt"}
    assert prompts == {"human", "agent"}
    assert not any(r["sess"] == opaque("child") for r in t3)
    replies = [r for r in t3 if r["kind"] == "reply"]
    human_turn = next(r for r in t3 if r["kind"] == "prompt" and r["author"] == "human")["id"]
    final = next(r for r in replies if r["turn"] == human_turn)
    assert final["words"] == len(("done: here is the final answer " * 5).split())


def test_claude_entrypoints_commands_and_paseo(corpus):
    _l, _e, rows = harvest_rows(corpus)
    claude = [r for r in rows if r["src"] == "claude_code" and r["kind"] == "prompt"]
    by_sess = {r["sess"]: r for r in claude}
    sid = {name: opaque(name) for name in ("sess-cli", "sess-p", "sess-paseo")}
    assert by_sess[sid["sess-cli"]]["author"] == "human"
    assert by_sess[sid["sess-cli"]]["words"] == 4  # "/autonomous ship the ledger"
    assert by_sess[sid["sess-p"]]["author"] == "agent"
    assert by_sess[sid["sess-paseo"]]["harness"] == "paseo" and by_sess[sid["sess-paseo"]]["author"] == "agent"
    assert len([r for r in claude if r["sess"] == sid["sess-cli"]]) == 1  # sidechain, tool result, bare /clear dropped
    reply = next(r for r in rows if r["src"] == "claude_code" and r["kind"] == "reply" and r["sess"] == sid["sess-cli"])
    assert reply["words"] == 3  # the last text, "Shipped the ledger."


def test_codex_originators(corpus):
    _l, _e, rows = harvest_rows(corpus)
    codex = {r["attr"].get("originator"): r for r in rows if r["src"] == "codex" and r["kind"] == "prompt"}
    assert codex["Codex Desktop"]["author"] == "human"
    assert codex["codex_exec"]["author"] == "agent"
    assert len(codex) == 2  # the subagent rollout is skipped


def test_history_skips_probes_and_separates_pasted_text(corpus):
    _l, _e, rows = harvest_rows(corpus)
    hist = [r for r in rows if r["src"] == "claude_history"]
    assert len(hist) == 2
    pasted = max(hist, key=lambda r: r["chars"])
    assert pasted["authored_chars"] == len("look at this")


def test_harvest_is_idempotent(corpus):
    tmp, roots = corpus
    ledger = L.Ledger(str(tmp / "ledger"))
    first = L.harvest(ledger, roots, since=None)
    second = L.harvest(ledger, roots, since=None)
    assert sum(first["added"].values()) > 0
    assert sum(second["added"].values()) == 0
    assert len((ledger.dir / "harvests.jsonl").read_text().splitlines()) == 2


def test_missing_stores_are_reported_not_raised(tmp_path):
    roots = {k: [] for k in L.DEFAULT_ROOTS}
    entry = L.harvest(L.Ledger(str(tmp_path / "ledger")), roots, since=None)
    assert all(not s["available"] and s["reason"] for s in entry["sources"])
    assert entry["added"] == {}


def test_fold_counts_only_human_prompts_and_their_replies(corpus):
    _l, _e, rows = harvest_rows(corpus)
    summary = T.fold(rows)
    # human: t3 web prompt, claude cli, codex desktop, 2 history prompts, bridge "plan the recap"
    assert summary["written"]["prompts"] == 6
    assert summary["dropped"]["agent author"] >= 3
    assert summary["dropped"]["automation marker"] == 1  # the [Fleet coordinator] bridge turn
    assert summary["agents_own"]["replies"] >= 1
    assert summary["read"]["reply_words_estimated"] > 0  # two history prompts have no stored reply


def test_fold_dedupes_one_prompt_seen_in_two_stores():
    a = make_row(src="t3", harness="t3", kind="prompt", ts=T0, text="ship it now please", session="x", author="human")
    b = make_row(src="bridged", harness="bridged", kind="prompt", ts=T0 + 60, text="Ship it  now please",
                 session="y", author="unknown")
    summary = T.fold([a, b])
    assert summary["written"]["prompts"] == 1
    assert summary["dropped"]["duplicate prompt"] == 1


def test_fold_drops_scripted_openings_across_sessions():
    rows = [make_row(src="claude_history", harness="claude-cli", kind="prompt", ts=T0 + i,
                     text=f"Run the ticket dispatcher with parameters now. RUN_ID={i}", session=f"s{i}",
                     author="human") for i in range(4)]
    rows.append(make_row(src="claude_history", harness="claude-cli", kind="prompt", ts=T0 + 99,
                         text="a genuinely different prompt that I typed by hand", session="z", author="human"))
    summary = T.fold(rows)
    assert summary["written"]["prompts"] == 1
    assert summary["dropped"]["repeated opening"] == 4


def test_exact_author_store_keeps_repeated_briefs():
    rows = [make_row(src="t3", harness="t3", kind="prompt", ts=T0 + i * 7200,
                     text="Same brief pasted into several threads on purpose, comfortably long enough to template.",
                     session=f"t{i}", author="human") for i in range(4)]
    # Four prompts typed in one store are four turns, and an exact-author store is never filtered as scripted.
    assert T.fold(rows)["written"]["prompts"] == 4


def test_text_only_sources_stop_once_exact_coverage_starts():
    r = make_row(src="bridged", harness="bridged", kind="prompt", ts=T0, text="hello there friend", session="b",
                 author="unknown")
    assert T.fold([r])["written"]["prompts"] == 1
    assert T.fold([r], text_only_until=T0 - 1)["written"]["prompts"] == 0


def test_read_band_orders_low_central_high(corpus):
    _l, _e, rows = harvest_rows(corpus)
    read = T.fold(rows)["read"]
    assert read["words_measured_only_low"] <= read["words_low"] <= read["words_central"] <= read["words_high"]
    basis = read["reply_words_measured"] + read["reply_words_estimated"]
    assert read["words_low"] == round(basis * 0.60) and read["words_high"] == round(basis * 0.70)


def test_unwrap_command():
    assert unwrap_command("<command-name>/mcp</command-name>") is None
    assert unwrap_command("plain text") == "plain text"


def test_archive_is_additive_and_updates_grown_files(tmp_path):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    write_jsonl(src / "p" / "a.jsonl", [{"x": 1}])
    write_jsonl(src / "p" / "b.jsonl", [{"x": 2}])
    first = A.copy_additive(src, dst, (".jsonl",))
    assert first["copied"] == 2
    (src / "p" / "b.jsonl").unlink()  # pruned at the source
    with (src / "p" / "a.jsonl").open("a") as handle:  # grew at the source
        handle.write(json.dumps({"x": 3}) + "\n")
    second = A.copy_additive(src, dst, (".jsonl",))
    assert second["copied"] == 1 and second["unchanged"] == 0
    assert (dst / "p" / "b.jsonl").exists()  # never deleted
    assert (dst / "p" / "a.jsonl").read_text() == (src / "p" / "a.jsonl").read_text()
    third = A.copy_additive(src, dst, (".jsonl",))
    assert third["copied"] == 0 and third["unchanged"] == 1
    assert not list(dst.rglob("*.yia-tmp"))


def test_archive_refuses_an_unmounted_root(tmp_path):
    with pytest.raises(FileNotFoundError):
        A.archive(tmp_path / "not-mounted")


@pytest.mark.skipif(not shutil.which("zstd"), reason="zstd not installed")
def test_codex_reads_compressed_rollouts(tmp_path):
    root = tmp_path / "codex"
    make_codex(root)
    for path in list(root.rglob("*.jsonl")):
        subprocess.run(["zstd", "-q", "--rm", str(path)], check=True)
    report, rows = S.read_codex_sessions([root], None)
    rows = list(rows)
    assert report.files == 3
    assert any(r["kind"] == "prompt" and r["author"] == "human" for r in rows)


def test_cli_harvest_and_attention_run_end_to_end(corpus, tmp_path):
    tmp, roots = corpus
    config = tmp / "config.json"
    config.write_text(json.dumps({"roots": {k: [str(p) for p in v] for k, v in roots.items()}}))
    env = dict(os.environ, HOME=str(tmp / "home"))  # no real stores reachable
    script = SCRIPTS / "year_in_ai.py"
    run = subprocess.run([sys.executable, str(script), "harvest", "--backfill", "--no-defaults", "--config",
                          str(config), "--ledger", str(tmp / "cli-ledger")], capture_output=True, text=True, env=env)
    assert run.returncode == 0, run.stderr
    out = tmp / "attention.json"
    run = subprocess.run([sys.executable, str(script), "attention", "--config", str(config), "--ledger",
                          str(tmp / "cli-ledger"), "--out", str(out)], capture_output=True, text=True, env=env)
    assert run.returncode == 0, run.stderr
    assert json.loads(out.read_text())["written"]["prompts"] == 6


# ------------------------------------------------------------ review round 1 regressions


def test_same_store_identical_prompts_are_distinct_turns():
    rows = [make_row(src="claude_history", harness="claude-cli", kind="prompt", ts=T0 + i * 60, text="yes",
                     session="s", author="human") for i in range(2)]
    assert T.fold(rows)["written"]["prompts"] == 2


def test_one_turn_in_two_stores_gets_one_reply():
    p1 = make_row(src="t3", harness="t3", kind="prompt", ts=T0, text="ship it now please", session="a", author="human")
    p2 = make_row(src="bridged", harness="bridged", kind="prompt", ts=T0 + 60, text="Ship it  now please",
                  session="b", author="unknown")
    r1 = make_row(src="t3", harness="t3", kind="reply", ts=T0 + 90, text="Shipped, merged and verified.", session="a",
                  author="human", turn=p1["id"])
    r2 = make_row(src="bridged", harness="bridged", kind="reply", ts=T0 + 90, text="Shipped (rendered differently).",
                  session="b", author="unknown", turn=p2["id"])
    summary = T.fold([p1, p2, r1, r2])
    assert summary["written"]["prompts"] == 1
    assert summary["by_month"][next(iter(summary["by_month"]))]["replies"] == 1
    assert summary["read"]["reply_words_measured"] == r1["words"]  # the canonical store's own reply


def test_two_turns_with_the_same_answer_keep_both_replies():
    rows = []
    for i, text in enumerate(("first question here", "second question here")):
        p = make_row(src="t3", harness="t3", kind="prompt", ts=T0 + i * 600, text=text, session="a", author="human")
        rows += [p, make_row(src="t3", harness="t3", kind="reply", ts=T0 + i * 600 + 5, text="Done.", session="a",
                             author="human", turn=p["id"])]
    summary = T.fold(rows)
    assert summary["written"]["prompts"] == 2
    assert summary["read"]["reply_words_measured"] == 2


def test_each_turn_is_claimed_once_per_store():
    # t3 saw two "yes" turns; the bridge saw three. Two of the bridge's merge into
    # t3's turns, one each; the third is a turn t3 never recorded.
    rows = [make_row(src="t3", harness="t3", kind="prompt", ts=T0 + i * 300, text="yes", session="t",
                     author="human") for i in range(2)]
    rows += [make_row(src="bridged", harness="bridged", kind="prompt", ts=T0 + i * 300, text="yes", session="b",
                      author="unknown") for i in range(3)]
    summary = T.fold(rows)
    assert summary["written"]["prompts"] == 3
    assert summary["dropped"]["duplicate prompt"] == 2


def test_a_reply_harvested_mid_turn_is_superseded(tmp_path):
    root = tmp_path / "claude"
    session = [
        {"type": "user", "uuid": "u1", "entrypoint": "cli", "timestamp": iso(T0), "message": {"content": "help me"}},
        {"type": "assistant", "uuid": "a1", "entrypoint": "cli", "timestamp": iso(T0 + 2),
         "message": {"content": [{"type": "text", "text": "working on it"}]}},
    ]
    write_jsonl(root / "-p" / "grow.jsonl", session)
    roots = {k: [] for k in L.DEFAULT_ROOTS}
    roots["claude_projects"] = [root]
    ledger = L.Ledger(str(tmp_path / "ledger"))
    L.harvest(ledger, roots, since=None)
    session.append({"type": "assistant", "uuid": "a2", "entrypoint": "cli", "timestamp": iso(T0 + 9),
                    "message": {"content": [{"type": "text", "text": "all finished now, merged and verified"}]}})
    write_jsonl(root / "-p" / "grow.jsonl", session)
    L.harvest(ledger, roots, since=None)
    rows = list(ledger.rows())
    assert len([r for r in rows if r["kind"] == "reply"]) == 2  # both revisions are kept on disk...
    summary = T.fold(rows)
    assert summary["read"]["reply_words_measured"] == 6  # ...and only the latest one is read
    assert summary["dropped"]["superseded reply revision"] == 1


def test_long_prompts_sharing_a_template_do_not_merge():
    prefix = "shared prefix " * 50
    assert text_hash(prefix + "one") != text_hash(prefix + "two")


def test_conductor_replies_pair_with_their_own_prompt(tmp_path):
    db = tmp_path / "conductor.db"
    con = sqlite3.connect(db)
    con.execute("create table session_messages (session_id text, role text, content text, created_at text, turn_id text)")
    def assistant(text):
        return json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}})
    for row in [("s", "user", "first ask", "2026-10-26 10:00:00", "t1"),
                ("s", "assistant", assistant("first answer here"), "2026-10-26 10:00:05", "t1"),
                ("s", "user", "second ask", "2026-10-26 10:01:00", "t2"),
                ("s", "assistant", assistant("second answer"), "2026-10-26 10:01:05", "t2")]:
        con.execute("insert into session_messages values (?,?,?,?,?)", row)
    con.commit()
    con.close()
    _report, rows = S.read_conductor(db, None)
    rows = list(rows)
    prompts = [r["id"] for r in rows if r["kind"] == "prompt"]
    replies = sorted((r for r in rows if r["kind"] == "reply"), key=lambda r: r["ts"])
    assert [prompts.index(r["turn"]) for r in replies] == [0, 1]
    assert [r["words"] for r in replies] == [3, 2]


def test_attribution_fields_cannot_carry_text():
    row = make_row(src="t3", harness="t3", kind="prompt", ts=T0, text="ordinary", session="s",
                   attr={"creation_source": f"{SECRET} as metadata", "project": SECRET, "created_by": "user"})
    assert row["attr"] == {"creation_source": "other", "created_by": "user"}
    assert SECRET not in json.dumps(row)
    assert row["sess"] == opaque("s") and row["sess"] != "s"


def test_unknown_providers_and_originators_become_other(tmp_path):
    from yia.ledger import harness_label
    assert harness_label("t3", f"{SECRET}", "provider") == "t3:other"
    assert harness_label("codex", "Codex Desktop", "originator") == "codex:Codex Desktop"
    assert harness_label("claude", None, "entrypoint") == "claude"


def test_codex_rollouts_are_streamed_not_loaded(tmp_path):
    # A reader that loads the file sees its contents at the first line; a
    # streaming reader also sees a line appended after it started.
    path = tmp_path / "rollout.jsonl"
    path.write_text(("{\"pad\": \"" + "x" * 1000 + "\"}\n") * 2000)
    lines = S._codex_lines(path)
    next(lines)
    with path.open("a") as handle:
        handle.write("APPENDED\n")
    assert list(lines)[-1].strip() == "APPENDED"


def test_archive_never_replaces_a_larger_copy_when_the_source_shrinks_mid_copy(tmp_path, monkeypatch):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    (src / "p").mkdir(parents=True)
    (dst / "p").mkdir(parents=True)
    (src / "p" / "a.jsonl").write_text("x" * 20)
    (dst / "p" / "a.jsonl").write_text("y" * 10)
    real_copy = A.shutil.copy2

    def shrink_then_copy(s, d, *args, **kwargs):
        Path(s).write_text("z")  # the live store truncates the file between stat and copy
        return real_copy(s, d, *args, **kwargs)

    monkeypatch.setattr(A.shutil, "copy2", shrink_then_copy)
    counts = A.copy_additive(src, dst, (".jsonl",))
    assert (dst / "p" / "a.jsonl").read_text() == "y" * 10
    assert counts["copied"] == 0
    assert not list(dst.rglob("*.yia-tmp"))


def test_archive_cleans_up_after_a_failed_copy(tmp_path, monkeypatch):
    src = tmp_path / "src"
    (src / "p").mkdir(parents=True)
    (src / "p" / "a.jsonl").write_text("data")
    real_copy = A.shutil.copy2

    def copy_then_fail(s, d, *args, **kwargs):
        real_copy(s, d, *args, **kwargs)
        raise OSError("disk full")

    monkeypatch.setattr(A.shutil, "copy2", copy_then_fail)
    counts = A.copy_additive(src, tmp_path / "dst", (".jsonl",))
    assert counts["errors"] == 1
    assert not list((tmp_path / "dst").rglob("*.yia-tmp"))


def test_year_selection_uses_the_local_calendar(tmp_path):
    from datetime import datetime, timezone
    ledger = L.Ledger(str(tmp_path / "ledger"))
    new_year_eve_local = datetime(2027, 1, 1, 2, 0, tzinfo=timezone.utc).timestamp()  # 21:00 on Dec 31 at UTC-5
    first_hours_local = datetime(2026, 1, 1, 3, 0, tzinfo=timezone.utc).timestamp()  # 22:00 on Dec 31 2025 at UTC-5
    ledger.write([
        make_row(src="t3", harness="t3", kind="prompt", ts=new_year_eve_local, text="late in the year", session="a",
                 author="human"),
        make_row(src="t3", harness="t3", kind="prompt", ts=first_hours_local, text="still last year", session="a",
                 author="human"),
    ])
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"utc_offset_hours": -5}))
    out = tmp_path / "a.json"
    run = subprocess.run([sys.executable, str(SCRIPTS / "year_in_ai.py"), "attention", "--year", "2026", "--config",
                          str(config), "--ledger", str(ledger.dir), "--out", str(out)], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    summary = json.loads(out.read_text())
    assert summary["written"]["prompts"] == 1
    assert list(summary["by_month"]) == ["2026-12"]  # the late-December prompt, not the 2025 one

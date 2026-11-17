import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest
import reel_loop as r

NOW = datetime(2026, 11, 17, tzinfo=timezone.utc)


def comment(cid="11", **kw):
    return {"id": cid, "text": "WORKSPACE!", "timestamp": (NOW - timedelta(days=1)).isoformat(),
            "from": {"id": "99", "username": "private_person"}, **kw}


@pytest.fixture
def setup(tmp_path):
    template = tmp_path / "template.txt"
    template.write_text("Here is the Act One playbook: https://example.org/playbook\n")
    tsha = hashlib.sha256(template.read_bytes()).hexdigest()
    card = {"account": "broomva.tech", "funnel": {"keyword": "workspace", "media_id": "22", "approval": {
        "by": "owner", "at": NOW.isoformat(), "template_sha256": tsha,
        "binding_sha256": r.funnel_binding("22", "workspace", "33", tsha)}}}
    calls = []
    pages = [{"data": [comment()]}]

    def http(method, url, **kw):
        calls.append((method, url, kw))
        assert url.startswith("https://graph.facebook.com/v27.0/")
        assert kw["headers"]["Authorization"] == "Bearer fake-secret"
        assert "fake-secret" not in url
        assert "fake-secret" not in json.dumps(kw.get("params", {}))
        assert "fake-secret" not in str(kw.get("body", ""))
        if method == "GET":
            assert kw["params"]["fields"] == "id,text,timestamp,from,hidden"
            return pages.pop(0)
        body = json.loads(kw["body"])
        assert body == {"recipient": {"comment_id": "11"}, "message": {"text": template.read_text()}}
        return {"message_id": "message-opaque", "recipient_id": "99"}

    def run(**kw):
        return r.funnel(card, template, ledger=tmp_path / "ledger.jsonl", ig_user_id="33",
                        token="fake-secret", now=lambda: NOW, http=kw.pop("http", http), **kw)
    return run, card, template, calls, pages, tmp_path / "ledger.jsonl"


@pytest.mark.parametrize("text,hit", [("WORKSPACE!", True), ("workspace", True), ("a workspace?", True),
                                      ("workspaces", False), ("myworkspace", False), ("workspace_1", False)])
def test_keywords(text, hit):
    assert r.keyword_hit(text, "workspace") is hit


@pytest.mark.parametrize("change", [
    {"text": "workspaces"}, {"text": "irrelevant"},
    {"timestamp": (NOW - timedelta(days=7)).isoformat()},
    {"timestamp": (NOW - timedelta(days=6.95)).isoformat()}, {"hidden": True},
    {"timestamp": (NOW - timedelta(days=8)).isoformat()},
    {"timestamp": (NOW + timedelta(seconds=1)).isoformat()},
    {"timestamp": "invalid"}, {"timestamp": "2026-11-16"},
    {"from": {"id": "33"}}, {"from": {"id": "99", "username": "Broomva.Tech"}},
    {"from": None}, {"id": "untrusted/id"}])
def test_skip_guards(setup, change):
    run, _, _, calls, pages, _ = setup
    pages[:] = [{"data": [comment(**change)]}]
    assert run(go_live=True)["replies"] == []
    assert [c[0] for c in calls] == ["GET"]


def test_dry_run_and_privacy(setup, capsys, monkeypatch):
    run, card, template, calls, pages, ledger = setup
    result = run()
    assert result["replies"] == [{"comment_id": "11", "age_seconds": 86400, "keyword_hit": True}]
    assert [c[0] for c in calls] == ["GET"]
    assert ledger.read_text() == ""
    cardfile = template.parent / "card.json"
    cardfile.write_text(json.dumps(card))
    monkeypatch.setenv("IG_ACCESS_TOKEN", "fake-secret")
    monkeypatch.setattr(r, "funnel", lambda *a, **kw: result)
    assert r.main(["funnel", str(cardfile), "--template", str(template), "--ig-user-id", "33"]) == 0
    output = capsys.readouterr()
    assert "private_person" not in output.out + output.err
    assert "WORKSPACE!" not in output.out + output.err
    assert "fake-secret" not in output.out + output.err


def test_idempotent_and_durable_reservation(setup):
    run, _, _, calls, pages, ledger = setup
    original = r._full_sync
    synced = []
    def fsync(fd):
        synced.append(ledger.stat().st_size if ledger.exists() else 0)   # ledger bytes at each sync
        return original(fd)
    # Inspect the on-disk reservation from inside the fake POST.
    def http(method, url, **kw):
        if method == "GET":
            return {"data": [comment(), comment()]}
        assert json.loads(ledger.read_text())["status"] == "attempting"
        assert any(size > 0 for size in synced)   # a sync ran after the reservation row was written
        calls.append((method, url, kw))
        return {"message_id": "ok"}
    from unittest.mock import patch
    with patch.object(r, "_full_sync", fsync):
        assert run(go_live=True, http=http)["replies"][0]["status"] == "sent"
        assert run(go_live=True, http=http)["replies"] == []
    assert len(calls) == 1
    assert [json.loads(x)["status"] for x in ledger.read_text().splitlines()] == ["attempting", "sent"]
    assert ledger.stat().st_mode & 0o777 == 0o600


def test_crash_reservation_never_retried(setup):
    run, _, _, calls, pages, ledger = setup
    def crash(method, url, **kw):
        if method == "GET":
            return {"data": [comment()]}
        raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        run(go_live=True, http=crash)
    assert json.loads(ledger.read_text())["status"] == "attempting"
    result = run(go_live=True)
    assert result["needs_human"] == ["11"]
    assert result["replies"] == []
    assert all(c[0] == "GET" for c in calls)


@pytest.mark.parametrize("response,status", [
    (r.PublishError("POST https://graph.facebook.com/v27.0/33/messages -> HTTP 403 (codes 10)"), "failed"),
    (r.PublishError("POST https://graph.facebook.com/v27.0/33/messages -> HTTP 503 (no codes)"), "uncertain"),
    (r.PublishError("POST https://graph.facebook.com/v27.0/33/messages failed: TimeoutError"), "uncertain"),
    (RuntimeError("private_person fake-secret"), "uncertain"),
    ({"error": {"message": "private_person"}}, "uncertain"), ({}, "uncertain")])
def test_unsuccessful_send_halts_and_is_never_retried(setup, response, status):
    run, _, _, calls, pages, ledger = setup
    posts = []
    def fail(method, url, **kw):
        if method == "GET":
            return {"data": [comment("11"), comment("12", **{"from": {"id": "98", "username": "another"}})]}
        posts.append(url)
        if isinstance(response, Exception):
            raise response
        return response
    first = run(go_live=True, http=fail)
    assert len(posts) == 1                      # the run stopped at the first unsuccessful send
    assert [x["status"] for x in first["replies"]] == [status]
    assert first["halted"]
    assert ("11" in first["needs_human"]) is (status == "uncertain")
    again = run(go_live=True, http=lambda m, u, **kw: {"data": [comment("11")]} if m == "GET" else posts.append(u))
    assert len(posts) == 1                      # never retried
    assert ("11" in again["needs_human"]) is (status == "uncertain")
    assert "private_person" not in ledger.read_text()
    assert "fake-secret" not in ledger.read_text()


def test_sha_mismatch_before_network(setup):
    run, _, template, calls, _, _ = setup
    template.write_bytes(template.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="sha256"):
        run(go_live=True)
    assert calls == []


def test_approval_required(setup):
    run, card, _, calls, _, _ = setup
    card["funnel"]["approval"] = None
    with pytest.raises(ValueError):
        run(go_live=True)
    assert not calls


def test_pagination_bounded_and_fixed_host(setup):
    run, _, _, calls, pages, _ = setup
    pages[:] = [{"data": [], "paging": {"next": "https://evil.test/?access_token=secret", "cursors": {"after": "cursor"}}},
                {"data": [comment()]}]
    assert len(run(max_pages=2)["replies"]) == 1
    assert calls[1][2]["params"]["after"] == "cursor"
    pages[:] = [{"data": [], "paging": {"next": "evil", "cursors": {"after": "again"}}}]
    assert run(max_pages=1)["truncated"] is True
    assert len(calls) == 3


def test_corrupt_ledger_blocks(setup):
    run, _, _, calls, _, ledger = setup
    ledger.write_text('{"comment_id":')
    with pytest.raises(ValueError):
        run(go_live=True)
    assert not calls


def test_in_repo_ledger_blocked(setup, tmp_path):
    _, card, template, _, _, _ = setup
    (tmp_path / ".git").mkdir()
    with pytest.raises(ValueError, match="outside"):
        r.funnel(card, template, ledger=tmp_path / "private.jsonl", ig_user_id="33", token="fake")


def test_concurrent_poller_blocked(setup):
    import fcntl
    run, _, _, calls, _, ledger = setup
    with ledger.open("w") as other:
        fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            run(go_live=True)
    assert not calls


def test_exact_template_bytes_despite_swap(setup):
    run, _, template, _, _, _ = setup
    approved = template.read_text()
    def swap(method, url, **kw):
        if method == "GET":
            template.write_text("unapproved replacement")
            return {"data": [comment()]}
        assert json.loads(kw["body"])["message"]["text"] == approved
        return {"message_id": "ok"}
    assert run(go_live=True, http=swap)["replies"][0]["status"] == "sent"


def test_cli_errors_never_echo_upstream(setup, monkeypatch, capsys):
    _, _, template, _, _, _ = setup
    def bad(*a, **kw):
        raise ValueError("private_person fake-secret WORKSPACE!")
    monkeypatch.setattr(r.json, "loads", bad)
    assert r.main(["funnel", str(template), "--template", str(template), "--ig-user-id", "33"]) == 2
    captured = capsys.readouterr()
    assert captured.err == "FUNNEL BLOCKED: ValueError\n"


def test_approval_binds_media_keyword_and_account(setup, tmp_path, capsys):
    run, card, template, calls, _, _ = setup
    for field, value in (("media_id", "23"), ("keyword", "playbook")):
        changed = json.loads(json.dumps(card))
        changed["funnel"][field] = value
        with pytest.raises(ValueError, match="does not cover"):
            r.funnel(changed, template, ledger=tmp_path / "l.jsonl", ig_user_id="33", token="t", now=lambda: NOW)
    with pytest.raises(ValueError, match="does not cover"):
        r.funnel(card, template, ledger=tmp_path / "l.jsonl", ig_user_id="34", token="t", now=lambda: NOW)
    assert calls == []
    cardfile = tmp_path / "card.json"
    cardfile.write_text(json.dumps(card))
    assert r.main(["funnel", str(cardfile), "--template", str(template), "--ig-user-id", "33", "--print-binding"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["binding_sha256"] == card["funnel"]["approval"]["binding_sha256"]
    assert calls == []


def test_account_handle_comes_from_the_card(setup, tmp_path):
    run, card, template, calls, pages, _ = setup
    missing = json.loads(json.dumps(card))
    del missing["account"]
    with pytest.raises(ValueError, match="account"):
        r.funnel(missing, template, ledger=tmp_path / "l.jsonl", ig_user_id="33", token="t", now=lambda: NOW)
    card["account"] = "@Other.Handle"
    pages[:] = [{"data": [comment("11", **{"from": {"id": "77", "username": "other.handle"}}),
                          comment("12", **{"from": {"id": "78", "username": "broomva.tech"}})]}]
    assert [x["comment_id"] for x in run()["replies"]] == ["12"]   # no hardcoded handle


def test_one_reply_per_commenter_per_post(setup):
    run, _, _, calls, pages, ledger = setup
    posts = []
    def http(method, url, **kw):
        if method == "GET":
            return {"data": [comment("11"), comment("12"), comment("13")]}
        posts.append(json.loads(kw["body"])["recipient"]["comment_id"])
        return {"message_id": "ok"}
    out = run(go_live=True, http=http)
    assert posts == ["11"]
    assert [x.get("status") for x in out["replies"]] == ["sent", "repeat_commenter", "repeat_commenter"]
    later = lambda m, u, **kw: {"data": [comment("14")]} if m == "GET" else posts.append("14")
    assert run(go_live=True, http=later)["replies"][0]["status"] == "repeat_commenter"
    assert posts == ["11"]
    assert '"99"' not in ledger.read_text()      # the commenter id is stored only as a keyed hash
    salt = ledger.with_name(ledger.name + ".salt")
    assert salt.stat().st_mode & 0o777 == 0o600


def test_well_formed_but_wrongly_typed_row_blocks(setup):
    run, _, _, calls, _, ledger = setup
    ledger.write_text(json.dumps({"comment_id": 11, "media_id": "22", "author": "a" * 64, "status": "sent"}) + "\n")
    with pytest.raises(ValueError, match="invalid funnel ledger"):
        run(go_live=True)
    assert calls == []


def test_missing_salt_blocks_a_used_ledger(setup):
    run, _, _, calls, _, ledger = setup
    assert run(go_live=True)["replies"][0]["status"] == "sent"
    ledger.with_name(ledger.name + ".salt").unlink()
    with pytest.raises(ValueError, match="salt"):
        run(go_live=True)
    assert [c[0] for c in calls] == ["GET", "POST"]


def test_ledger_without_trailing_newline_is_completed(setup):
    run, _, _, calls, pages, ledger = setup
    assert run(go_live=True)["replies"][0]["status"] == "sent"
    ledger.write_text(ledger.read_text().rstrip("\n"))
    pages[:] = [{"data": [comment("12", **{"from": {"id": "98", "username": "another"}})]}]
    def http(method, url, **kw):
        if method == "GET":
            return pages.pop(0)
        return {"message_id": "ok"}
    assert run(go_live=True, http=http)["replies"][0]["status"] == "sent"
    assert len([json.loads(x) for x in ledger.read_text().splitlines()]) == 4
    pages[:] = [{"data": [comment("11"), comment("12", **{"from": {"id": "98", "username": "another"}})]}]
    assert run(go_live=True, http=http)["replies"] == []   # both already consumed; nothing resent


def test_meta_offset_timestamp(setup):
    run, _, _, _, pages, _ = setup
    pages[:] = [{"data": [comment(timestamp=(NOW - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S+0000"))]}]
    assert run()["replies"][0]["age_seconds"] == 86400


def test_go_live_requires_explicit_ledger(setup, monkeypatch, capsys):
    run, card, template, calls, _, _ = setup
    cardfile = template.parent / "card.json"
    cardfile.write_text(json.dumps(card))
    monkeypatch.setenv("IG_ACCESS_TOKEN", "fake-secret")
    assert r.main(["funnel", str(cardfile), "--template", str(template), "--ig-user-id", "33", "--go-live"]) == 2
    assert capsys.readouterr().err == "FUNNEL BLOCKED: ValueError\n"
    assert calls == []

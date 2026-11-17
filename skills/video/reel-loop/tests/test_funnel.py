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
    card = {"funnel": {"keyword": "workspace", "media_id": "22", "approval": {
        "by": "owner", "at": NOW.isoformat(), "template_sha256": hashlib.sha256(template.read_bytes()).hexdigest()}}}
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
            assert kw["params"]["fields"] == "id,text,timestamp,from"
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
    original = r.os.fsync
    synced = []
    def fsync(fd):
        synced.append(fd)
        return original(fd)
    # Inspect the on-disk reservation from inside the fake POST.
    def http(method, url, **kw):
        if method == "GET":
            return {"data": [comment(), comment()]}
        assert json.loads(ledger.read_text())["status"] == "attempting"
        assert len(synced) >= 2
        calls.append((method, url, kw))
        return {"message_id": "ok"}
    from unittest.mock import patch
    with patch.object(r.os, "fsync", fsync):
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


@pytest.mark.parametrize("response", [RuntimeError("private_person fake-secret"), {"error": {"message": "private_person"}}, {}])
def test_failed_send_never_retried(setup, response):
    run, _, _, calls, pages, ledger = setup
    def fail(method, url, **kw):
        if method == "GET":
            return {"data": [comment()]}
        if isinstance(response, Exception):
            raise response
        return response
    assert run(go_live=True, http=fail)["replies"][0]["status"] == "failed"
    assert run(go_live=True)["replies"] == []
    assert "private_person" not in ledger.read_text()


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

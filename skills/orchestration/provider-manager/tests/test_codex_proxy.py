import base64
import json
import os
import select
import sys
import threading
from contextlib import contextmanager

import pytest

import pm_codex_proxy as proxy
import pm_store

pytestmark = pytest.mark.new_only


def home(path, email):
    path.mkdir()
    claim = base64.urlsafe_b64encode(json.dumps({"email": email}).encode()).decode().rstrip("=")
    (path / "auth.json").write_text(json.dumps({"tokens": {"id_token": "e30." + claim + ".fake"}}))
    return path


@pytest.fixture
def world(tmp_path, monkeypatch):
    selected = home(tmp_path / "selected", "selected@example.test")
    old = home(tmp_path / "old", "old@example.test")
    legacy = home(tmp_path / "legacy", "legacy@example.test")
    monkeypatch.setattr(proxy.pm_codex_homes, "root", lambda: tmp_path / "registry")
    monkeypatch.setattr(pm_store, "CODEX_AUTH_PATH", legacy / "auth.json")
    trace = tmp_path / "trace.jsonl"
    monkeypatch.setenv("PM_PROXY_TEST_TRACE", str(trace))
    peer = tmp_path / "peer.py"
    peer.write_text('''import json,os,sys
home=os.environ["CODEX_HOME"]
for line in sys.stdin:
    m=json.loads(line)
    with open(os.environ["PM_PROXY_TEST_TRACE"],"a") as out:
        out.write(json.dumps({"home":home,"method":m.get("method"),"id":m.get("id"),"args":sys.argv[1:]})+"\\n")
    method=m.get("method")
    if method=="model/list" and m.get("params",{}).get("gate"):
        print(json.dumps({"method":"test/discoveryWaiting"}),flush=True)
        with open(m["params"]["gate"]) as gate: gate.read()
    if method=="model/list" and m.get("params",{}).get("hang"):
        print(json.dumps({"method":"test/discoveryWaiting"}),flush=True)
        continue
    if method=="bad-json":
        print("not json",flush=True)
        continue
    if "id" not in m: continue
    if method=="fail":
        print(json.dumps({"id":m["id"],"error":{"code":123,"message":"expected"}}),flush=True)
        continue
    if method=="initialize" and os.path.basename(home)=="bad-init":
        print(json.dumps({"id":m["id"],"error":{"code":123,"message":"init failed"}}),flush=True)
        continue
    if method in ("thread/start","thread/resume","thread/fork"):
        tid=m.get("params",{}).get("threadId","new-"+os.path.basename(home))
        if method=="thread/fork": tid="fork-"+tid
        result={"thread":{"id":tid},"home":home}
    else: result={"home":home}
    print(json.dumps({"id":m["id"],"result":result}),flush=True)
''')
    return selected, old, legacy, peer, trace


@contextmanager
def running(world):
    selected, _, _, peer, _ = world
    ir, iw = os.pipe()
    or_, ow = os.pipe()
    input_stream = os.fdopen(ir, "rb", buffering=0)
    output_stream = os.fdopen(ow, "wb", buffering=0)
    client_write = os.fdopen(iw, "wb", buffering=0)
    client_read = os.fdopen(or_, "rb", buffering=0)
    instance = proxy.Proxy(sys.executable, [str(peer), "app-server"], selected,
                           {"email": "selected@example.test"}, input_stream, output_stream)
    result = []
    instance.finished = threading.Event()
    def start():
        try:
            result.append(instance.run())
        except Exception as exc:
            result.append(exc)
        finally:
            instance.finished.set()
    worker = threading.Thread(target=start, daemon=True)
    worker.start()
    def send(method, ident=None, params=None):
        msg = {"method": method}
        if ident is not None: msg["id"] = ident
        if params is not None: msg["params"] = params
        client_write.write((json.dumps(msg) + "\n").encode())
    def receive():
        assert select.select([client_read], [], [], 5)[0], "proxy did not answer"
        return json.loads(client_read.readline())
    try:
        send("initialize", 1, {"clientInfo": {"name": "test"}})
        assert receive()["id"] == 1
        send("initialized")
        yield instance, send, receive, result, client_write
    finally:
        client_write.close()
        worker.join(5)
        assert not worker.is_alive(), "proxy did not stop after input EOF"
        input_stream.close()
        output_stream.close()
        client_read.close()


def test_new_native_thread_records_selected_home(world):
    selected, _, _, _, _ = world
    with running(world) as (_, send, receive, _, _):
        send("thread/start", 2, {})
        assert receive()["result"]["home"] == str(selected)
        assert proxy.thread_home("new-selected")["home"] == str(selected)
    assert all(event["args"][-2:] == ["-c", 'cli_auth_credentials_store="file"']
               for event in map(json.loads, world[4].read_text().splitlines()))


@pytest.mark.parametrize("method", ["thread/resume", "thread/fork"])
def test_restart_replays_init_and_pins_mapped_source(world, method):
    _, old, _, _, trace = world
    proxy.remember_thread("old-thread", {"home": str(old), "email": "old@example.test"})
    with running(world) as (_, send, receive, _, _):
        send(method, 2, {"threadId": "old-thread"})
        response = receive()
        assert response["id"] == 2  # Internal replay response stays hidden.
        assert response["result"]["home"] == str(old)
        native = response["result"]["thread"]["id"]
        assert proxy.thread_home(native)["home"] == str(old)
    events = [json.loads(line) for line in trace.read_text().splitlines()]
    assert [e["method"] for e in events if e["home"] == str(old)] == ["initialize", "initialized", method]


def test_unmapped_thread_uses_legacy_home(world):
    _, _, legacy, _, _ = world
    (legacy / "config.toml").write_text('cli_auth_credentials_store="keyring"\n')
    with running(world) as (_, send, receive, _, _):
        send("thread/resume", 2, {"threadId": "pre-migration"})
        assert receive()["result"]["home"] == str(legacy)
    legacy_events = [json.loads(line) for line in world[4].read_text().splitlines()
                     if json.loads(line)["home"] == str(legacy)]
    assert legacy_events
    assert all(e["args"][-2:] == ["-c", 'cli_auth_credentials_store="file"'] for e in legacy_events)


def test_active_session_refuses_cross_account_resume(world):
    selected, old, _, _, _ = world
    proxy.remember_thread("old-thread", {"home": str(old), "email": "old@example.test"})
    with running(world) as (_, send, receive, _, _):
        send("thread/start", 2, {})
        receive()
        send("thread/resume", 3, {"threadId": "old-thread"})
        assert "error" in receive()
        send("account/read", 4)
        assert receive()["result"]["home"] == str(selected)


def test_error_response_and_parse_error_are_forwarded(world):
    with running(world) as (_, send, receive, _, stream):
        send("fail", 2)
        assert receive() == {"id": 2, "error": {"code": 123, "message": "expected"}}
        stream.write(b"not json\n")
        assert receive()["error"]["code"] == -32700


def test_invalid_child_protocol_stops_proxy(world):
    with running(world) as (instance, send, _, result, _):
        send("bad-json", 2)
        assert instance.finished.wait(5)
    assert isinstance(result[0], pm_store.StoreError)


def test_mapping_cannot_be_overwritten_or_redirected(world, tmp_path):
    selected, old, _, _, _ = world
    original = {"home": str(selected), "email": "selected@example.test"}
    proxy.remember_thread("same", original)
    with pytest.raises(pm_store.StoreError):
        proxy.remember_thread("same", {"home": str(old), "email": "old@example.test"})
    assert proxy.thread_home("same") == original
    alias = tmp_path / "alias"
    alias.symlink_to(old)
    with pytest.raises(pm_store.StoreError):
        proxy._identity(alias, "old@example.test")
    with pytest.raises(pm_store.StoreError):
        proxy._identity(old, "wrong@example.test")


def test_replay_initialization_failure_does_not_resume(world):
    selected, _, _, peer, trace = world
    bad = home(selected.parent / "bad-init", "bad@example.test")
    proxy.remember_thread("bad-thread", {"home": str(bad), "email": "bad@example.test"})
    with running(world) as (_, send, receive, _, _):
        send("thread/resume", 2, {"threadId": "bad-thread"})
        assert "error" in receive()
    events = [json.loads(line) for line in trace.read_text().splitlines()]
    assert not any(e["method"] == "thread/resume" for e in events)


@pytest.mark.parametrize("method", ["account/login/start", "account/logout"])
def test_pinned_grant_cannot_be_reauthorized_through_rpc(world, method):
    with running(world) as (_, send, receive, _, _):
        send(method, 2)
        assert "provider-manager" in receive()["error"]["message"]
        send("account/read", 3)
        assert receive()["id"] == 3
    assert not any(json.loads(line)["method"] == method for line in world[4].read_text().splitlines())


def test_resume_waits_for_discovery_then_restarts(world, tmp_path):
    _, old, _, _, _ = world
    proxy.remember_thread("old-thread", {"home": str(old), "email": "old@example.test"})
    gate = tmp_path / "release-discovery"
    os.mkfifo(gate)
    with running(world) as (instance, send, receive, _, _):
        waiting = threading.Event()
        receive_request = instance.receive
        def observe(request):
            receive_request(request)
            if instance.waiting is not None:
                waiting.set()
        instance.receive = observe
        send("model/list", 2, {"gate": str(gate)})
        assert receive()["method"] == "test/discoveryWaiting"
        send("thread/resume", 3, {"threadId": "old-thread"})
        assert waiting.wait(5)
        with gate.open("w") as release:
            release.write("ready")
        assert receive()["id"] == 2
        resumed = receive()
        assert resumed["id"] == 3
        assert resumed["result"]["home"] == str(old)
        assert instance.waiting is None


def test_hung_discovery_gives_bounded_resume_error(world, monkeypatch):
    _, old, _, _, _ = world
    proxy.remember_thread("old-thread", {"home": str(old), "email": "old@example.test"})
    monkeypatch.setattr(proxy, "DISCOVERY_DRAIN_SECONDS", 0.05)
    with running(world) as (_, send, receive, _, _):
        send("model/list", 2, {"hang": True})
        assert receive()["method"] == "test/discoveryWaiting"
        send("thread/resume", 3, {"threadId": "old-thread"})
        reply = receive()
        assert reply["id"] == 3
        assert "timeout" in reply["error"]["message"]

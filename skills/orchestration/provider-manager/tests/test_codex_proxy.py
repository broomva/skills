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
    monkeypatch.setattr(proxy.pm_codex_homes, "selected", lambda: {"home": str(selected), "email": "selected@example.test"})
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
    if method=="account/read" and m.get("params",{}).get("invalid"):
        print("not json",flush=True)
        continue
    if method is None and m.get("id")==7:
        print(json.dumps({"method":"test/approvalReceived","params":{"home":home,"id":m["id"],"result":m.get("result")}}),flush=True)
        continue
    if "id" not in m: continue
    if method=="model/list" and m.get("params",{}).get("fail"):
        print(json.dumps({"id":m["id"],"error":{"code":123,"message":"expected"}}),flush=True)
        continue
    if method=="initialize" and os.path.basename(home)=="hang-init": continue
    if method=="initialize" and os.path.basename(home)=="bad-init":
        print(json.dumps({"id":m["id"],"error":{"code":123,"message":"init failed"}}),flush=True)
        continue
    if method in ("thread/start","thread/resume","thread/fork"):
        tid=m.get("params",{}).get("threadId","new-"+os.path.basename(home))
        if method=="thread/fork": tid="fork-"+tid
        result={"thread":{"id":tid},"home":home}
    elif method=="turn/start":
        if m.get("params",{}).get("approval"):
            print(json.dumps({"id":7,"method":"item/commandExecution/requestApproval","params":{"threadId":m["params"]["threadId"]}}),flush=True)
        result={"home":home,"turn":{"id":"turn-"+os.path.basename(home)}}
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
        initialized = receive()
        assert initialized["id"] == 1 and "result" in initialized
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


def test_two_threads_in_shared_app_server_follow_selection_and_keep_turn_ownership(world, monkeypatch):
    selected, old, _, _, _ = world
    with running(world) as (_, send, receive, _, _):
        send("thread/start", 2, {})
        first = receive()["result"]["thread"]["id"]
        monkeypatch.setattr(proxy.pm_codex_homes, "selected", lambda: {"home": str(old), "email": "old@example.test"})
        send("thread/start", 3, {})
        second = receive()["result"]["thread"]["id"]
        assert first != second
        for native, expected in [(first, selected), (second, old), (first, selected)]:
            send("turn/start", 4, {"threadId": native})
            assert receive()["result"]["home"] == str(expected)
        send("account/read", 5)
        assert receive()["result"]["home"] == str(old)


def test_error_response_and_parse_error_are_forwarded(world):
    with running(world) as (_, send, receive, _, stream):
        send("model/list", 2, {"fail": True})
        assert receive() == {"id": 2, "error": {"code": 123, "message": "expected"}}
        stream.write(b"not json\n")
        assert receive()["error"]["code"] == -32700


def test_invalid_child_protocol_fails_only_its_home(world, monkeypatch):
    selected, old, _, _, _ = world
    with running(world) as (_, send, receive, _, _):
        send("account/read", 2, {"invalid": True})
        assert "invalid JSON" in receive()["error"]["message"]
        monkeypatch.setattr(proxy.pm_codex_homes, "selected", lambda: {"home": str(old), "email": "old@example.test"})
        send("account/read", 3)
        assert receive()["result"]["home"] == str(old)
        send("thread/read", 4, {"threadId": "unmapped-legacy"})
        assert receive()["result"]["home"] == str(world[2])


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


def test_pending_discovery_does_not_block_other_home_resume(world, tmp_path):
    _, old, _, _, _ = world
    proxy.remember_thread("old-thread", {"home": str(old), "email": "old@example.test"})
    gate = tmp_path / "release-discovery"
    os.mkfifo(gate)
    with running(world) as (_, send, receive, _, _):
        send("model/list", 2, {"gate": str(gate)})
        assert receive()["method"] == "test/discoveryWaiting"
        send("thread/resume", 3, {"threadId": "old-thread"})
        resumed = receive()
        assert resumed["id"] == 3
        assert resumed["result"]["home"] == str(old)
        with gate.open("w") as release:
            release.write("ready")
        assert receive()["id"] == 2


def test_initialization_timeout_is_bounded_and_does_not_reroute(world, monkeypatch):
    selected, _, _, _, _ = world
    hung = home(selected.parent / "hang-init", "hung@example.test")
    proxy.remember_thread("hung-thread", {"home": str(hung), "email": "hung@example.test"})
    with running(world) as (_, send, receive, _, _):
        monkeypatch.setattr(proxy, "INITIALIZE_TIMEOUT", 0.05)
        send("thread/resume", 3, {"threadId": "hung-thread"})
        reply = receive()
        assert reply["id"] == 3
        assert "timed out" in reply["error"]["message"]
        send("account/read", 4)
        assert receive()["result"]["home"] == str(selected)


def test_all_thread_identity_operations_route_fresh_proxy_to_owner(world):
    selected, old, _, _, _ = world
    proxy.remember_thread("old-thread", {"home": str(old), "email": "old@example.test"})
    with running(world) as (_, send, receive, _, _):
        for method in ("thread/read", "thread/archive", "thread/unarchive", "turn/interrupt",
                       "thread/goal/get", "mcpServer/tool/call", "feedback/upload", "app/list", "app/read",
                       "thread/rollback", "thread/backgroundTerminals/list", "thread/backgroundTerminals/terminate"):
            send(method, 2, {"threadId": "old-thread"})
            assert receive()["result"]["home"] == str(old)


def test_colliding_server_request_ids_route_responses_to_origin_child(world, monkeypatch):
    selected, old, _, _, _ = world
    # Both real peers intentionally use native server request ID 7.
    with running(world) as (_, send, receive, _, stream):
        send("thread/start", 2, {})
        first = receive()["result"]["thread"]["id"]
        monkeypatch.setattr(proxy.pm_codex_homes, "selected", lambda: {"home": str(old), "email": "old@example.test"})
        send("thread/start", 3, {})
        second = receive()["result"]["thread"]["id"]
        send("turn/start", 4, {"threadId": first, "approval": True})
        send("turn/start", 5, {"threadId": second, "approval": True})
        messages = [receive() for _ in range(4)]
        approvals = [m for m in messages if m.get("method") == "item/commandExecution/requestApproval"]
        assert len(approvals) == 2
        assert approvals[0]["id"] != approvals[1]["id"]
        expected = {first: str(selected), second: str(old)}
        for approval in reversed(approvals):
            thread_id = approval["params"]["threadId"]
            stream.write((json.dumps({"id": approval["id"], "result": {"decision": thread_id}}) + "\n").encode())
            notification = receive()
            assert notification["method"] == "test/approvalReceived"
            assert notification["params"] == {"home": expected[thread_id], "id": 7,
                                                "result": {"decision": thread_id}}


@pytest.mark.parametrize("method", ["config/value/write", "config/batchWrite", "command/exec", "new/unknown"])
def test_unsupported_global_writes_fail_closed(world, method):
    with running(world) as (_, send, receive, _, _):
        send(method, 2, {"threadId": "spoofed"})
        assert "Unsupported" in receive()["error"]["message"]
    assert not any(json.loads(line)["method"] == method for line in world[4].read_text().splitlines())


def test_paseo_startup_discovery_then_resume_uses_native_owner(world):
    selected, old, _, _, trace = world
    proxy.remember_thread("paseo-thread", {"home": str(old), "email": "old@example.test"})
    with running(world) as (_, send, receive, _, _):
        for method in ("config/read", "collaborationMode/list", "skills/list", "thread/loaded/list",
                       "getUserSavedConfig"):
            send(method, 2, {})
            assert receive()["result"]["home"] == str(selected)
        send("thread/resume", 3, {"threadId": "paseo-thread"})
        assert receive()["result"]["home"] == str(old)
        send("thread/read", 4, {"threadId": "paseo-thread"})
        assert receive()["result"]["home"] == str(old)
    methods = [json.loads(line)["method"] for line in trace.read_text().splitlines()]
    assert methods[:7] == ["initialize", "initialized", "config/read", "collaborationMode/list",
                           "skills/list", "thread/loaded/list", "getUserSavedConfig"]


def test_account_display_notifications_follow_selection_but_thread_events_all_flow(world):
    import io
    selected, old, _, _, _ = world
    output = io.BytesIO()
    instance = proxy.Proxy(sys.executable, [], selected, {"email": "selected@example.test"},
                           io.BytesIO(), output)
    old_child = {"account": proxy._identity(old), "failed": False}
    chosen_child = {"account": proxy._identity(selected), "failed": False}
    instance.response(old_child, {"method": "account/updated", "params": {"fixture": "old"}})
    instance.response(chosen_child, {"method": "account/updated", "params": {"fixture": "chosen"}})
    instance.response(old_child, {"method": "item/completed", "params": {"threadId": "old-thread"}})
    messages = [json.loads(line) for line in output.getvalue().splitlines()]
    assert len(messages) == 2
    assert messages[0]["params"]["fixture"] == "chosen"
    assert messages[1]["params"]["threadId"] == "old-thread"
